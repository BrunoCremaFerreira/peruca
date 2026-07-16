"""
LlmAppService Integration Tests - Smart Home Cameras LIVE end-to-end battery.

Unlike test_llm_app_service_chat__smart_home_cameras_graph.py (which documents
the graceful degradation when no camera aliases exist), this battery exercises
the REAL path against a live Home Assistant: WebSocket alias discovery seeds
the SQLite alias table, the REST repository fetches a real PNG snapshot, and
the chat response carries a decodable data URI end to end — including the
line-level merge bypass when a camera intent is combined with another intent.

Requirements (each missing piece skips gracefully, never errors):
  1. Home Assistant reachable (``home_assistant_available`` fixture);
  2. a valid HOME_ASSISTANT_TOKEN (minted by docker/test-backends/bootstrap_ha.py);
  3. at least one ``camera.*`` entity with aliases exposed to the assistant
     (validated post-seed through the same SQLite alias repository the graph
     reads — a separate REST probe would be redundant).

The stack expected by these tests is docker/test-backends (local_file camera
``camera.camera_sala`` aliased "câmera da sala", serving a PNG) plus a live
Ollama at LLM_PROVIDER_URL.
"""

import asyncio
import base64
import os

import pytest

from application.appservices.view_models import ChatRequest
from application.graphs.smart_home_cameras_graph import _CAMERA_STATE_PT
from infra.ioc import (
    get_smart_home_app_service,
    get_smart_home_entity_alias_repository,
)


pytestmark = pytest.mark.integration


PNG_DATA_URI_PREFIX = "data:image/png;base64,"
PNG_MAGIC_BYTES = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def seeded_camera_aliases(home_assistant_available, integration_db_path):
    """Seed the SQLite alias table from the live Home Assistant (per test).

    Function-scoped on purpose: ``integration_db_path`` recreates the database
    for every test, so a module-scoped seed would be wiped before the second
    test runs. The extra WebSocket roundtrip per test is negligible next to
    the gemma4 latency.

    The IoC caches repositories in ``_repo_cache`` keyed by connection string,
    so ``get_smart_home_app_service()`` here and the graph built by
    ``get_llm_app_service()`` share the SAME alias repository instance — the
    post-seed validation below therefore reads through the exact path the
    graph uses at classify time.
    """
    if not os.environ.get("HOME_ASSISTANT_TOKEN", ""):
        pytest.skip(
            "HOME_ASSISTANT_TOKEN vazio — rode docker/test-backends/bootstrap_ha.py"
        )

    # Repo pattern: no pytest-asyncio; the WebSocket close() already happens
    # in the finally block of SmartHomeService.update_entity_aliases().
    asyncio.get_event_loop().run_until_complete(
        get_smart_home_app_service().update_entity_aliases()
    )

    camera_aliases = get_smart_home_entity_alias_repository().get_all(
        entity_id_starts_with="camera."
    )
    if not camera_aliases:
        pytest.skip("câmera/aliases ausentes no HA — rode bootstrap_ha.py")

    return camera_aliases


def _decode_png_data_uri_line(line: str) -> bytes:
    """Decode one ``data:image/png;base64,...`` line into raw bytes (strict)."""
    encoded = line[len(PNG_DATA_URI_PREFIX):].strip()
    return base64.b64decode(encoded, validate=True)


# ======================================================
# Snapshot — real PNG data URI end to end
# ======================================================


def test_chat__show_snapshot_camera_sala__returns_decodable_png_data_uri(
    seeded_camera_aliases, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id,
        message="Mostre a câmera da sala",
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — routed to the cameras graph
    assert intents is not None and "smart_home_security_cams" in intents, (
        f"Expected 'smart_home_security_cams' in intents, got: {intents}"
    )

    # Assert — the output carries a line starting with the PNG data URI prefix
    # (post-F3 the MIME comes from the real HA response, which serves a PNG).
    assert isinstance(output, str)
    uri_lines = [
        line for line in output.splitlines() if line.startswith(PNG_DATA_URI_PREFIX)
    ]
    assert uri_lines, (
        f"Expected a line starting with {PNG_DATA_URI_PREFIX!r} in output, "
        f"got: {output[:200]!r}..."
    )

    # Assert — strict base64 decodes back to a real, non-empty PNG
    decoded = _decode_png_data_uri_line(uri_lines[0])
    assert len(decoded) > 0, "Decoded snapshot is empty"
    assert decoded.startswith(PNG_MAGIC_BYTES), (
        f"Decoded bytes do not start with the PNG magic, got: {decoded[:8]!r}"
    )


# ======================================================
# Status — friendly name + pt-BR mapped state
# ======================================================


def test_chat__check_status_camera_sala__returns_friendly_name_and_mapped_state(
    seeded_camera_aliases, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id,
        message="A câmera da sala está ativa?",
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    output = response.get("output")

    # Assert — the real friendly name reported by Home Assistant is present
    assert isinstance(output, str)
    assert "Camera Sala" in output, (
        f"Expected friendly name 'Camera Sala' in output, got: {output!r}"
    )

    # Assert — the state is one of the closed pt-BR values (post-F5). The real
    # state of the local_file camera may vary (idle/recording/streaming/...),
    # so the assertion targets the closed set instead of pinning "em espera" —
    # this still catches raw English states leaking through.
    assert any(state_pt in output for state_pt in _CAMERA_STATE_PT.values()), (
        f"Expected one of the pt-BR states {sorted(_CAMERA_STATE_PT.values())} "
        f"in output, got: {output!r}"
    )


# ======================================================
# Multi-intent — merge bypass keeps the data URI intact
# ======================================================


def test_chat__snapshot_and_light_off__uri_intact_after_merge_bypass(
    seeded_camera_aliases, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id,
        message="mostra a câmera da sala e apaga a luz da sala",
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Flakiness mitigation (mandatory per plan §6): the SUT here is the merge
    # bypass, not the classifier (which has its own battery). If gemma4 emits a
    # single intent for this phrasing, the merge path is never entered — skip
    # instead of inheriting the classifier's variance in an expensive test.
    if intents is None or len(intents) < 2:
        pytest.skip(
            f"Classifier emitted a single intent ({intents}); "
            "the merge bypass under test was not exercised"
        )

    assert isinstance(output, str)

    # Assert — exactly one data URI occurrence: the bypass must neither drop
    # the URI (LLM merge would truncate/corrupt megabytes of base64) nor
    # duplicate it when concatenating bypass + merged text.
    assert output.count(PNG_DATA_URI_PREFIX) == 1, (
        f"Expected exactly 1 occurrence of {PNG_DATA_URI_PREFIX!r}, "
        f"found {output.count(PNG_DATA_URI_PREFIX)}"
    )

    # Assert — the URI survived the merge byte-intact: strict base64 decodes
    # back to a real PNG.
    uri_lines = [
        line for line in output.splitlines() if line.startswith(PNG_DATA_URI_PREFIX)
    ]
    assert len(uri_lines) == 1, (
        f"Expected exactly 1 data-URI line, got {len(uri_lines)}"
    )
    decoded = _decode_png_data_uri_line(uri_lines[0])
    assert decoded.startswith(PNG_MAGIC_BYTES), (
        f"Decoded bytes do not start with the PNG magic, got: {decoded[:8]!r}"
    )

    # Assert — the merged conversational text (light action response) is still
    # present outside the URI line: the bypass must not swallow the other
    # intent's output.
    conversational_text = "\n".join(
        line
        for line in output.splitlines()
        if not line.startswith(PNG_DATA_URI_PREFIX)
    ).strip()
    assert conversational_text, (
        "Expected non-empty conversational text outside the data-URI line, "
        "but only the URI was returned"
    )
