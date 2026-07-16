"""
HomeAssistantSmartHomeCameraRepository Unit Tests

These tests are written BEFORE the implementation exists (TDD).
They will be skipped (not error) until the repository class is importable.

Key design constraints verified:
  1. get_state: calls GET /api/states/{entity_id} and maps the HA response
     to a SmartHomeCamera entity with entity_id, state, friendly_name, is_available.
  2. get_snapshot: calls GET /api/camera_proxy/{entity_id} and returns a
     SmartHomeCameraSnapshot with the raw image_bytes.
  3. Both methods raise aiohttp.ClientResponseError on 4xx/5xx responses.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    import aiohttp
    from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_camera_repository import (
        HomeAssistantSmartHomeCameraRepository,
    )
    from domain.entities import SmartHomeCamera, SmartHomeCameraSnapshot

    _REPO_AVAILABLE = True
except ImportError:
    HomeAssistantSmartHomeCameraRepository = None  # type: ignore[assignment,misc]
    SmartHomeCamera = None  # type: ignore[assignment,misc]
    SmartHomeCameraSnapshot = None  # type: ignore[assignment,misc]
    _REPO_AVAILABLE = False

_SKIP_IF_NOT_IMPLEMENTED = pytest.mark.skipif(
    not _REPO_AVAILABLE,
    reason="HomeAssistantSmartHomeCameraRepository not implemented yet",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo() -> "HomeAssistantSmartHomeCameraRepository":
    """Build the repository with test credentials."""
    return HomeAssistantSmartHomeCameraRepository(
        base_url="http://localhost:8123",
        token="test-token",
    )


def _make_ha_camera_state_response(
    entity_id: str = "camera.cozinha",
    state: str = "idle",
    friendly_name: str = "Camera Cozinha",
) -> dict:
    """Simulate a typical HA /api/states response for a camera entity."""
    return {
        "entity_id": entity_id,
        "state": state,
        "attributes": {
            "friendly_name": friendly_name,
        },
    }


def _mock_aiohttp_session_json(json_response):
    """
    Returns a mock aiohttp.ClientSession that yields a response whose
    .json() coroutine returns json_response.
    Follows the same pattern as test_home_assistant_smart_home_sensor_repository.py.
    """
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=json_response)
    mock_resp.status = 200

    mock_cm_resp = AsyncMock()
    mock_cm_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_cm_resp)

    mock_cm_session = AsyncMock()
    mock_cm_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm_session.__aexit__ = AsyncMock(return_value=False)

    return mock_cm_session, mock_session


def _mock_aiohttp_session_bytes(image_bytes: bytes, content_type: str = "image/jpeg"):
    """
    Returns a mock aiohttp.ClientSession that yields a response whose
    .read() coroutine returns image_bytes (binary snapshot content).

    content_type mirrors aiohttp's response.content_type semantics: it is
    ALWAYS a str — when the Content-Type header is absent, aiohttp reports
    "application/octet-stream", never None.
    """
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.read = AsyncMock(return_value=image_bytes)
    mock_resp.status = 200
    mock_resp.content_type = content_type

    mock_cm_resp = AsyncMock()
    mock_cm_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_cm_resp)

    mock_cm_session = AsyncMock()
    mock_cm_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm_session.__aexit__ = AsyncMock(return_value=False)

    return mock_cm_session, mock_session


def _mock_aiohttp_error_session(status_code: int = 404):
    """Returns a mock aiohttp session that raises ClientResponseError on raise_for_status."""
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock(
        side_effect=aiohttp.ClientResponseError(
            MagicMock(), MagicMock(), status=status_code
        )
    )
    mock_resp.status = status_code

    mock_cm_resp = AsyncMock()
    mock_cm_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_cm_resp)

    mock_cm_session = AsyncMock()
    mock_cm_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm_session.__aexit__ = AsyncMock(return_value=False)

    return mock_cm_session, mock_session


# ===========================================================================
# TestHomeAssistantSmartHomeCameraRepositoryGetState
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestHomeAssistantSmartHomeCameraRepositoryGetState:
    def test_get_state__returns_smart_home_camera(self):
        """
        get_state must return a SmartHomeCamera instance populated from the HA response.
        """
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session_json(
            _make_ha_camera_state_response(
                entity_id="camera.cozinha",
                state="idle",
                friendly_name="Camera Cozinha",
            )
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state("camera.cozinha")
            )

        assert isinstance(result, SmartHomeCamera), (
            f"Expected SmartHomeCamera, got {type(result)}: {result!r}"
        )

    def test_get_state__entity_id_mapped_correctly(self):
        """entity_id in the returned SmartHomeCamera must match the requested entity_id."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session_json(
            _make_ha_camera_state_response(entity_id="camera.cozinha")
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state("camera.cozinha")
            )

        assert result.entity_id == "camera.cozinha", (
            f"Expected entity_id='camera.cozinha', got {result.entity_id!r}"
        )

    def test_get_state__state_mapped_from_ha_response(self):
        """The 'state' field in the HA response must be mapped to SmartHomeCamera.state."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session_json(
            _make_ha_camera_state_response(state="recording")
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state("camera.cozinha")
            )

        assert result.state == "recording", (
            f"Expected state='recording', got {result.state!r}"
        )

    def test_get_state__friendly_name_mapped_from_attributes(self):
        """friendly_name must be populated from attributes.friendly_name in the HA response."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session_json(
            _make_ha_camera_state_response(friendly_name="Camera da Cozinha")
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state("camera.cozinha")
            )

        assert result.friendly_name == "Camera da Cozinha", (
            f"Expected friendly_name='Camera da Cozinha', got {result.friendly_name!r}"
        )

    def test_get_state__is_available_true_when_state_is_not_unavailable(self):
        """When HA state is not 'unavailable', is_available must be True."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session_json(
            _make_ha_camera_state_response(state="idle")
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state("camera.cozinha")
            )

        assert result.is_available is True, (
            f"Expected is_available=True when state='idle', got {result.is_available!r}"
        )

    def test_get_state__is_available_false_when_state_is_unavailable(self):
        """When HA state is 'unavailable', is_available must be False."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session_json(
            _make_ha_camera_state_response(state="unavailable")
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state("camera.cozinha")
            )

        assert result.is_available is False, (
            f"Expected is_available=False when state='unavailable', got {result.is_available!r}"
        )

    def test_get_state__url_calls_api_states_endpoint(self):
        """
        The URL sent to session.get must use /api/states/{entity_id}.
        Guards against using the wrong HA endpoint.
        """
        repo = _make_repo()
        entity_id = "camera.cozinha"
        _, mock_session = _mock_aiohttp_session_json(
            _make_ha_camera_state_response(entity_id=entity_id)
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            asyncio.get_event_loop().run_until_complete(repo.get_state(entity_id))

        called_url = mock_session.get.call_args[0][0]
        assert "api/states" in called_url, (
            f"Expected '/api/states' in URL, got: {called_url!r}"
        )
        assert entity_id in called_url, (
            f"Expected entity_id={entity_id!r} in URL, got: {called_url!r}"
        )
        assert called_url.startswith("http://localhost:8123"), (
            f"Expected URL to start with base_url, got: {called_url!r}"
        )

    def test_get_state__ha_returns_404__propagates_exception(self):
        """A 4xx response from HA must propagate as aiohttp.ClientResponseError."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_error_session(status_code=404)

        with patch.object(repo, "_get_session", return_value=mock_session):
            with pytest.raises(aiohttp.ClientResponseError):
                asyncio.get_event_loop().run_until_complete(
                    repo.get_state("camera.nonexistent")
                )

    def test_get_state__ha_returns_500__propagates_exception(self):
        """A 5xx response from HA must propagate as aiohttp.ClientResponseError."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_error_session(status_code=500)

        with patch.object(repo, "_get_session", return_value=mock_session):
            with pytest.raises(aiohttp.ClientResponseError):
                asyncio.get_event_loop().run_until_complete(
                    repo.get_state("camera.cozinha")
                )


# ===========================================================================
# TestHomeAssistantSmartHomeCameraRepositoryGetSnapshot
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestHomeAssistantSmartHomeCameraRepositoryGetSnapshot:
    def test_get_snapshot__returns_smart_home_camera_snapshot(self):
        """
        get_snapshot must return a SmartHomeCameraSnapshot populated with
        the raw bytes returned by the HA camera_proxy endpoint.
        """
        repo = _make_repo()
        fake_jpeg = b"\xff\xd8\xff\xe0\x00fake_jpeg_content"
        _, mock_session = _mock_aiohttp_session_bytes(fake_jpeg)

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_snapshot("camera.cozinha")
            )

        assert isinstance(result, SmartHomeCameraSnapshot), (
            f"Expected SmartHomeCameraSnapshot, got {type(result)}: {result!r}"
        )

    def test_get_snapshot__entity_id_mapped_correctly(self):
        """entity_id in the returned SmartHomeCameraSnapshot must match the requested entity."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session_bytes(b"fake_image")

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_snapshot("camera.cozinha")
            )

        assert result.entity_id == "camera.cozinha", (
            f"Expected entity_id='camera.cozinha', got {result.entity_id!r}"
        )

    def test_get_snapshot__image_bytes_populated_from_response(self):
        """image_bytes in the snapshot must contain the exact bytes from the HA response."""
        repo = _make_repo()
        expected_bytes = b"\xff\xd8\xff\xe0real_jpeg_data_here"
        _, mock_session = _mock_aiohttp_session_bytes(expected_bytes)

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_snapshot("camera.cozinha")
            )

        assert result.image_bytes == expected_bytes, (
            f"Expected image_bytes to match HA response, got {result.image_bytes!r}"
        )

    def test_get_snapshot__url_calls_camera_proxy_endpoint(self):
        """
        The URL sent to session.get must use /api/camera_proxy/{entity_id}.
        Guards against using /api/states or other wrong endpoints.
        """
        repo = _make_repo()
        entity_id = "camera.cozinha"
        _, mock_session = _mock_aiohttp_session_bytes(b"fake_image")

        with patch.object(repo, "_get_session", return_value=mock_session):
            asyncio.get_event_loop().run_until_complete(repo.get_snapshot(entity_id))

        called_url = mock_session.get.call_args[0][0]
        assert "camera_proxy" in called_url, (
            f"Expected 'camera_proxy' in URL, got: {called_url!r}"
        )
        assert entity_id in called_url, (
            f"Expected entity_id={entity_id!r} in URL, got: {called_url!r}"
        )
        assert called_url.startswith("http://localhost:8123"), (
            f"Expected URL to start with base_url, got: {called_url!r}"
        )

    def test_get_snapshot__url_does_not_use_api_states_path(self):
        """
        Regression guard: get_snapshot must NOT call /api/states — it must call
        /api/camera_proxy. Using the wrong endpoint would return JSON, not bytes.
        """
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session_bytes(b"img")

        with patch.object(repo, "_get_session", return_value=mock_session):
            asyncio.get_event_loop().run_until_complete(
                repo.get_snapshot("camera.cozinha")
            )

        called_url = mock_session.get.call_args[0][0]
        assert "api/states" not in called_url, (
            f"get_snapshot must NOT call /api/states, got URL: {called_url!r}"
        )

    def test_get_snapshot__png_content_type_header__snapshot_content_type_is_image_png(
        self,
    ):
        """
        F3: when HA answers with Content-Type: image/png, the repository must
        propagate it to SmartHomeCameraSnapshot.content_type so the graph can
        build a correct data URI (instead of hardcoding image/jpeg).
        """
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session_bytes(
            b"\x89PNG\r\n\x1a\nfake_png", content_type="image/png"
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_snapshot("camera.cozinha")
            )

        assert result.content_type == "image/png", (
            f"Expected content_type='image/png' from the response header, "
            f"got {result.content_type!r}"
        )

    def test_get_snapshot__jpeg_content_type_header__snapshot_content_type_is_image_jpeg(
        self,
    ):
        """F3: Content-Type: image/jpeg must be captured as-is."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session_bytes(
            b"\xff\xd8\xff\xe0fake_jpeg", content_type="image/jpeg"
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_snapshot("camera.cozinha")
            )

        assert result.content_type == "image/jpeg", (
            f"Expected content_type='image/jpeg', got {result.content_type!r}"
        )

    def test_get_snapshot__octet_stream_content_type__defaults_to_image_jpeg(self):
        """
        F3 guard: a missing Content-Type header surfaces as
        'application/octet-stream' in aiohttp (never None). Non-image values
        must NOT leak into the entity — fall back to the 'image/jpeg' default
        so the data URI is always valid.
        """
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session_bytes(
            b"raw_bytes", content_type="application/octet-stream"
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_snapshot("camera.cozinha")
            )

        assert result.content_type == "image/jpeg", (
            f"Expected fallback content_type='image/jpeg' for "
            f"'application/octet-stream', got {result.content_type!r}"
        )

    def test_get_snapshot__non_image_content_type__defaults_to_image_jpeg(self):
        """
        F3 guard: any Content-Type outside image/* (e.g. text/html from a
        misconfigured proxy) must fall back to 'image/jpeg' — an invalid data
        URI must never be produced downstream.
        """
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session_bytes(
            b"<html>oops</html>", content_type="text/html"
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_snapshot("camera.cozinha")
            )

        assert result.content_type == "image/jpeg", (
            f"Expected fallback content_type='image/jpeg' for 'text/html', "
            f"got {result.content_type!r}"
        )

    def test_get_snapshot__ha_returns_404__propagates_exception(self):
        """A 4xx response must propagate as aiohttp.ClientResponseError."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_error_session(status_code=404)

        with patch.object(repo, "_get_session", return_value=mock_session):
            with pytest.raises(aiohttp.ClientResponseError):
                asyncio.get_event_loop().run_until_complete(
                    repo.get_snapshot("camera.nonexistent")
                )

    def test_get_snapshot__ha_returns_500__propagates_exception(self):
        """A 5xx response must propagate as aiohttp.ClientResponseError."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_error_session(status_code=500)

        with patch.object(repo, "_get_session", return_value=mock_session):
            with pytest.raises(aiohttp.ClientResponseError):
                asyncio.get_event_loop().run_until_complete(
                    repo.get_snapshot("camera.cozinha")
                )


# ===========================================================================
# TestSessionReuse — aiohttp.ClientSession must be created at most once
# ===========================================================================
#
# Contract (Milestone 2B-2): the adapter reuses a single aiohttp.ClientSession
# across calls via _get_session(). Calling a method twice must instantiate
# aiohttp.ClientSession AT MOST ONCE.
#
# RED today: every method opens `async with aiohttp.ClientSession() as session`,
# so two calls instantiate the session twice (call_count == 2).


def _make_reusable_session_bytes(image_bytes: bytes):
    """
    Build a single session mock that works regardless of whether production
    uses it as a context manager (`async with aiohttp.ClientSession() as s`)
    or directly via _get_session() (`s = self._get_session()`).

    The session enters itself (`__aenter__` returns the same object), so the
    `.get` call — which returns the response context manager whose .read()
    yields the image bytes — is always reachable. Only the instantiation count
    is asserted by the caller.
    """
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.read = AsyncMock(return_value=image_bytes)
    mock_resp.status = 200
    mock_resp.content_type = "image/jpeg"

    mock_cm_resp = AsyncMock()
    mock_cm_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_cm_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


@_SKIP_IF_NOT_IMPLEMENTED
class TestSessionReuse:
    def test_get_snapshot__called_twice__client_session_instantiated_once(self):
        repo = _make_repo()
        mock_session = _make_reusable_session_bytes(b"fake_image")

        with patch(
            "aiohttp.ClientSession", return_value=mock_session
        ) as client_session_cls:
            asyncio.get_event_loop().run_until_complete(
                repo.get_snapshot("camera.cozinha")
            )
            asyncio.get_event_loop().run_until_complete(
                repo.get_snapshot("camera.cozinha")
            )

        assert client_session_cls.call_count == 1, (
            f"Expected aiohttp.ClientSession to be instantiated once across two "
            f"calls (session reuse), got {client_session_cls.call_count}"
        )
