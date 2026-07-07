#!/usr/bin/env python3
"""Idempotent bootstrap for the integration-test Home Assistant instance.

Turns a freshly-started (or already-configured) HA container into a ready
backend for the Peruca integration suite:

  1. Waits for the HA API to answer.
  2. Obtains an access token — completing onboarding on a fresh instance, or
     logging in with the owner credentials on subsequent runs.
  3. Mints a long-lived access token (only when .env.test has none) and writes
     it into docker/test-backends/.env.test (git-ignored — no secret in git).
  4. Ensures the test areas exist and that every helper/template entity is
     assigned to its area, given aliases and exposed to the conversation
     assistant.

Running it twice is a no-op: existing token is reused, existing areas/aliases
are not duplicated.

Dependencies (aiohttp, websockets) already ship with the project venv, so run
it from inside that venv (run-integration-tests.sh does this for you).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import aiohttp
import websockets

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_TEST = SCRIPT_DIR / ".env.test"
ENV_EXAMPLE = SCRIPT_DIR / ".env.test.example"

CLIENT_NAME = "peruca-integration-tests"
LANGUAGE = "pt"

# local_file camera (created via a config-entry flow; YAML platform setup for
# cameras is no longer supported by Home Assistant).
CAMERA_NAME = "Camera Sala"
CAMERA_FILE = "/config/test_camera.png"

# Test areas (display name) and the entities that belong to each, with the
# aliases the classifier prompts may use. Entities absent from the registry
# (e.g. a demo entity without a unique_id) are skipped with a warning.
AREAS = ["Sala", "Quarto", "Cozinha"]

ENTITIES: dict[str, tuple[str, list[str]]] = {
    "light.sala": ("Sala", ["luz da sala", "abajur da sala"]),
    "light.quarto": ("Quarto", ["luz do quarto", "abajur do quarto"]),
    "light.cozinha": ("Cozinha", ["luz da cozinha", "luzes da cozinha"]),
    "sensor.temperatura_sala": ("Sala", ["temperatura da sala"]),
    "sensor.umidade_quarto": ("Quarto", ["umidade do quarto"]),
    "climate.clima_sala": ("Sala", ["ar condicionado da sala", "clima da sala"]),
    "camera.camera_sala": ("Sala", ["câmera da sala"]),
}


# ---------------------------------------------------------------------------
# .env.test helpers
# ---------------------------------------------------------------------------
def load_env() -> dict[str, str]:
    """Load .env.test, seeding it from the example template on first run."""
    if not ENV_TEST.exists():
        ENV_TEST.write_text(ENV_EXAMPLE.read_text(), encoding="utf-8")
        print(f"==> Created {ENV_TEST.name} from template")

    env: dict[str, str] = {}
    for line in ENV_TEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def write_token(token: str) -> None:
    """Persist HOME_ASSISTANT_TOKEN into .env.test, replacing any prior value."""
    lines = ENV_TEST.read_text(encoding="utf-8").splitlines()
    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith("HOME_ASSISTANT_TOKEN="):
            lines[i] = f"HOME_ASSISTANT_TOKEN={token}"
            replaced = True
            break
    if not replaced:
        lines.append(f"HOME_ASSISTANT_TOKEN={token}")
    ENV_TEST.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"==> Wrote HOME_ASSISTANT_TOKEN to {ENV_TEST.name}")


# ---------------------------------------------------------------------------
# REST — onboarding / login / token exchange
# ---------------------------------------------------------------------------
async def wait_for_api(session: aiohttp.ClientSession, base_url: str, timeout: int = 180) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            async with session.get(f"{base_url}/manifest.json", timeout=5) as resp:
                if resp.status == 200:
                    print("==> Home Assistant API is up")
                    return
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass
        await asyncio.sleep(3)
    raise RuntimeError(f"Home Assistant did not become ready within {timeout}s")


async def _exchange_code(session: aiohttp.ClientSession, base_url: str, client_id: str, code: str) -> str:
    data = {"grant_type": "authorization_code", "code": code, "client_id": client_id}
    async with session.post(f"{base_url}/auth/token", data=data) as resp:
        resp.raise_for_status()
        return (await resp.json())["access_token"]


async def _onboard(session: aiohttp.ClientSession, base_url: str, client_id: str, user: str, pwd: str) -> str | None:
    """Create the owner on a fresh instance. Returns an auth_code, or None if
    the instance is already onboarded."""
    payload = {
        "client_id": client_id,
        "name": "Peruca Test",
        "username": user,
        "password": pwd,
        "language": LANGUAGE,
    }
    async with session.post(f"{base_url}/api/onboarding/users", json=payload) as resp:
        if resp.status == 200:
            print("==> Completed onboarding (owner created)")
            return (await resp.json())["auth_code"]
        # 403/40x => already onboarded; fall back to the login flow.
        print(f"==> Onboarding not needed (HTTP {resp.status}); will log in")
        return None


async def _login(session: aiohttp.ClientSession, base_url: str, client_id: str, user: str, pwd: str) -> str:
    """Log in with owner credentials, returning an auth_code."""
    flow_req = {"client_id": client_id, "handler": ["homeassistant", None], "redirect_uri": client_id}
    async with session.post(f"{base_url}/auth/login_flow", json=flow_req) as resp:
        resp.raise_for_status()
        flow_id = (await resp.json())["flow_id"]

    step = {"client_id": client_id, "username": user, "password": pwd}
    async with session.post(f"{base_url}/auth/login_flow/{flow_id}", json=step) as resp:
        resp.raise_for_status()
        result = await resp.json()

    if result.get("type") != "create_entry":
        raise RuntimeError(f"Login failed: {result}")
    print("==> Logged in with owner credentials")
    return result["result"]


async def _finish_onboarding(session: aiohttp.ClientSession, base_url: str, client_id: str, access_token: str) -> None:
    """Best-effort completion of the remaining onboarding steps. Failures are
    non-fatal: the API/WebSocket already work once the owner exists."""
    headers = {"Authorization": f"Bearer {access_token}"}
    for path, body in (
        ("/api/onboarding/core_config", {}),
        ("/api/onboarding/analytics", {}),
        ("/api/onboarding/integration", {"client_id": client_id, "redirect_uri": client_id}),
    ):
        try:
            async with session.post(f"{base_url}{path}", json=body, headers=headers) as resp:
                await resp.read()
        except aiohttp.ClientError:
            pass


async def ensure_local_file_camera(session: aiohttp.ClientSession, base_url: str, token: str) -> None:
    """Create the local_file camera via its config-entry flow (idempotent).

    Cameras can no longer be set up through a YAML platform, so this drives the
    same config flow the UI would. Non-fatal: a failure just leaves the camera
    battery to exercise the graceful "no cameras" path.
    """
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with session.get(f"{base_url}/api/config/config_entries/entry", headers=headers) as resp:
            entries = await resp.json()
        if any(e.get("domain") == "local_file" for e in entries):
            print("   = camera already configured")
            return

        async with session.post(
            f"{base_url}/api/config/config_entries/flow",
            json={"handler": "local_file"},
            headers=headers,
        ) as resp:
            flow = await resp.json()
        flow_id = flow.get("flow_id")
        if not flow_id:
            print(f"   ! camera flow init failed: {flow}")
            return

        async with session.post(
            f"{base_url}/api/config/config_entries/flow/{flow_id}",
            json={"file_path": CAMERA_FILE, "name": CAMERA_NAME},
            headers=headers,
        ) as resp:
            result = await resp.json()
        if result.get("type") == "create_entry":
            print("   + camera config entry created")
        else:
            print(f"   ! camera flow did not complete: {result}")
    except aiohttp.ClientError as exc:
        print(f"   ! camera setup skipped ({exc})")


async def get_access_token(session: aiohttp.ClientSession, base_url: str, client_id: str, user: str, pwd: str) -> str:
    code = await _onboard(session, base_url, client_id, user, pwd)
    if code is not None:
        access_token = await _exchange_code(session, base_url, client_id, code)
        await _finish_onboarding(session, base_url, client_id, access_token)
        return access_token
    code = await _login(session, base_url, client_id, user, pwd)
    return await _exchange_code(session, base_url, client_id, code)


# ---------------------------------------------------------------------------
# WebSocket — token minting + registry configuration
# ---------------------------------------------------------------------------
class HaWebSocket:
    """Minimal authenticated HA WebSocket client with request/response matching."""

    def __init__(self, base_url: str, token: str):
        self._ws_url = base_url.replace("https", "wss").replace("http", "ws").rstrip("/") + "/api/websocket"
        self._token = token
        self._id = 0
        self._ws: websockets.WebSocketClientProtocol | None = None

    async def __aenter__(self) -> "HaWebSocket":
        self._ws = await websockets.connect(self._ws_url, max_size=None)
        auth_required = json.loads(await self._ws.recv())
        if auth_required.get("type") != "auth_required":
            raise RuntimeError(f"Unexpected first frame: {auth_required}")
        await self._ws.send(json.dumps({"type": "auth", "access_token": self._token}))
        result = json.loads(await self._ws.recv())
        if result.get("type") != "auth_ok":
            raise RuntimeError(f"WebSocket auth failed: {result}")
        return self

    async def __aexit__(self, *exc) -> None:
        if self._ws is not None:
            await self._ws.close()

    async def send(self, message: dict) -> dict:
        self._id += 1
        message_id = self._id
        message["id"] = message_id
        await self._ws.send(json.dumps(message))
        while True:
            resp = json.loads(await self._ws.recv())
            if resp.get("id") == message_id:
                return resp


async def token_is_valid(base_url: str, token: str) -> bool:
    if not token:
        return False
    try:
        async with HaWebSocket(base_url, token):
            return True
    except Exception:
        return False


async def mint_long_lived_token(ws: HaWebSocket) -> str:
    resp = await ws.send(
        {"type": "auth/long_lived_access_token", "client_name": CLIENT_NAME, "lifespan": 3650}
    )
    if not resp.get("success"):
        raise RuntimeError(f"Failed to mint long-lived token: {resp}")
    print("==> Minted long-lived access token")
    return resp["result"]


async def ensure_areas(ws: HaWebSocket) -> dict[str, str]:
    resp = await ws.send({"type": "config/area_registry/list"})
    name_to_id = {a["name"]: a["area_id"] for a in resp.get("result", [])}
    for name in AREAS:
        if name in name_to_id:
            continue
        created = await ws.send({"type": "config/area_registry/create", "name": name})
        if created.get("success"):
            name_to_id[name] = created["result"]["area_id"]
            print(f"   + area created: {name}")
    return name_to_id


async def wait_for_entities(ws: HaWebSocket, wanted: set[str], timeout: int = 40) -> set[str]:
    """Poll the entity registry until all wanted entities appear (or timeout)."""
    deadline = time.monotonic() + timeout
    present: set[str] = set()
    while time.monotonic() < deadline:
        resp = await ws.send({"type": "config/entity_registry/list"})
        present = {e["entity_id"] for e in resp.get("result", [])}
        if wanted.issubset(present):
            return present
        await asyncio.sleep(2)
    return present


async def configure_entities(ws: HaWebSocket, name_to_id: dict[str, str]) -> None:
    present = await wait_for_entities(ws, set(ENTITIES))
    for entity_id, (area_name, aliases) in ENTITIES.items():
        if entity_id not in present:
            print(f"   ! skipped (not in registry): {entity_id}")
            continue
        area_id = name_to_id.get(area_name)

        # Area + aliases.
        await ws.send(
            {
                "type": "config/entity_registry/update",
                "entity_id": entity_id,
                "area_id": area_id,
                "aliases": aliases,
            }
        )
        # Exposure — write the entity-registry option the config repository reads
        # (options.conversation.should_expose). NOTE: the modern
        # `homeassistant/expose_entity` command RESETS aliases to None, so it is
        # deliberately NOT used here; this options update preserves aliases.
        await ws.send(
            {
                "type": "config/entity_registry/update",
                "entity_id": entity_id,
                "options_domain": "conversation",
                "options": {"should_expose": True},
            }
        )
        print(f"   * configured: {entity_id} -> {area_name} (exposed)")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
async def main() -> int:
    env = load_env()
    base_url = env.get("HOME_ASSISTANT_URL", "http://localhost:8123").rstrip("/")
    client_id = base_url + "/"
    username = env.get("HA_BOOTSTRAP_USERNAME", "peruca")
    password = env.get("HA_BOOTSTRAP_PASSWORD", "peruca-test-password")
    existing_token = env.get("HOME_ASSISTANT_TOKEN", "")

    async with aiohttp.ClientSession() as session:
        await wait_for_api(session, base_url)

        # Reuse a still-valid token; only mint when necessary.
        if await token_is_valid(base_url, existing_token):
            print("==> Reusing existing long-lived token from .env.test")
            token = existing_token
        else:
            access_token = await get_access_token(session, base_url, client_id, username, password)
            async with HaWebSocket(base_url, access_token) as ws:
                token = await mint_long_lived_token(ws)
            write_token(token)

        # Camera has no YAML platform — create it via its config-entry flow.
        await ensure_local_file_camera(session, base_url, token)

    # Configure areas + entities with the durable token.
    async with HaWebSocket(base_url, token) as ws:
        print("==> Ensuring areas and entity exposure...")
        name_to_id = await ensure_areas(ws)
        await configure_entities(ws, name_to_id)

    print("==> Home Assistant is ready for the integration tests")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
