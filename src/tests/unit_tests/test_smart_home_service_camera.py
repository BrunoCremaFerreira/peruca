"""
SmartHomeService camera method unit tests.

These tests are written BEFORE the implementation exists (TDD).
They will be skipped (not error) until SmartHomeCameraRepository and the new
SmartHomeService camera methods are importable.

Key design constraints verified:
  1. camera_get_state delegates entirely to smart_home_camera_repository.get_state().
  2. camera_get_snapshot delegates entirely to smart_home_camera_repository.get_snapshot().
  3. The SmartHomeService constructor remains backward-compatible when
     smart_home_camera_repository is not supplied (None).
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from domain.services.smart_home_service import SmartHomeService

try:
    from domain.entities import SmartHomeCamera, SmartHomeCameraSnapshot
    from domain.interfaces.smart_home_repository import SmartHomeCameraRepository
    _CAMERA_AVAILABLE = True
except ImportError:
    SmartHomeCamera = None  # type: ignore[assignment,misc]
    SmartHomeCameraSnapshot = None  # type: ignore[assignment,misc]
    SmartHomeCameraRepository = None  # type: ignore[assignment,misc]
    _CAMERA_AVAILABLE = False

_SKIP_IF_NOT_IMPLEMENTED = pytest.mark.skipif(
    not _CAMERA_AVAILABLE,
    reason="SmartHomeCamera / SmartHomeCameraRepository not implemented yet",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(camera_repo=None):
    """
    Build a SmartHomeService with controllable mocked repositories.

    Follows the same pattern as test_smart_home_service.py::_make_service().

    Returns: (service, light_repo, config_repo, alias_repo, climate_repo, camera_repo)
    """
    light_repo = AsyncMock()
    config_repo = AsyncMock()
    alias_repo = MagicMock()
    climate_repo = AsyncMock()
    config_repo.get_all_exposed_entities_ids.return_value = []

    if camera_repo is None:
        camera_repo = AsyncMock()

    service = SmartHomeService(
        smart_home_light_repository=light_repo,
        smart_home_configuration_repository=config_repo,
        smart_home_entity_alias_repository=alias_repo,
        smart_home_climate_repository=climate_repo,
        smart_home_camera_repository=camera_repo,
    )
    return service, light_repo, config_repo, alias_repo, climate_repo, camera_repo


def _sample_camera() -> "SmartHomeCamera":
    """Returns a pre-built SmartHomeCamera entity."""
    return SmartHomeCamera(
        entity_id="camera.cozinha",
        state="idle",
        friendly_name="Camera Cozinha",
        is_available=True,
    )


def _sample_snapshot() -> "SmartHomeCameraSnapshot":
    """Returns a pre-built SmartHomeCameraSnapshot entity."""
    return SmartHomeCameraSnapshot(
        entity_id="camera.cozinha",
        image_bytes=b"\xff\xd8\xff\xe0fake_jpeg",
        content_type="image/jpeg",
    )


# ===========================================================================
# TestSmartHomeServiceCameraGetState
# ===========================================================================

@_SKIP_IF_NOT_IMPLEMENTED
class TestSmartHomeServiceCameraGetState:

    def test_camera_get_state__delegates_to_camera_repository(self):
        """
        camera_get_state must call smart_home_camera_repository.get_state()
        exactly once with the provided entity_id.
        """
        service, _, _, _, _, camera_repo = _make_service()
        camera_repo.get_state.return_value = _sample_camera()

        asyncio.get_event_loop().run_until_complete(
            service.camera_get_state(entity_id="camera.cozinha")
        )

        camera_repo.get_state.assert_awaited_once(), (
            "Expected camera_repo.get_state to be awaited exactly once"
        )

    def test_camera_get_state__passes_entity_id_to_repository(self):
        """The entity_id argument must be forwarded to the repository unchanged."""
        service, _, _, _, _, camera_repo = _make_service()
        camera_repo.get_state.return_value = _sample_camera()

        asyncio.get_event_loop().run_until_complete(
            service.camera_get_state(entity_id="camera.portao")
        )

        call_args = camera_repo.get_state.call_args
        passed_entity_id = call_args[0][0] if call_args[0] else call_args[1].get("entity_id")
        assert passed_entity_id == "camera.portao", (
            f"Expected entity_id='camera.portao' forwarded to repo, got: {passed_entity_id!r}"
        )

    def test_camera_get_state__returns_entity_from_repository(self):
        """The SmartHomeCamera returned by the repository must be returned to the caller."""
        service, _, _, _, _, camera_repo = _make_service()
        expected = _sample_camera()
        camera_repo.get_state.return_value = expected

        result = asyncio.get_event_loop().run_until_complete(
            service.camera_get_state(entity_id="camera.cozinha")
        )

        assert result is expected, (
            f"Expected the exact entity returned by repository, got {result!r}"
        )

    def test_camera_get_state__returns_smart_home_camera_instance(self):
        """The return type must be SmartHomeCamera."""
        service, _, _, _, _, camera_repo = _make_service()
        camera_repo.get_state.return_value = _sample_camera()

        result = asyncio.get_event_loop().run_until_complete(
            service.camera_get_state(entity_id="camera.cozinha")
        )

        assert isinstance(result, SmartHomeCamera), (
            f"Expected SmartHomeCamera instance, got {type(result)}"
        )


# ===========================================================================
# TestSmartHomeServiceCameraGetSnapshot
# ===========================================================================

@_SKIP_IF_NOT_IMPLEMENTED
class TestSmartHomeServiceCameraGetSnapshot:

    def test_camera_get_snapshot__delegates_to_camera_repository(self):
        """
        camera_get_snapshot must call smart_home_camera_repository.get_snapshot()
        exactly once with the provided entity_id.
        """
        service, _, _, _, _, camera_repo = _make_service()
        camera_repo.get_snapshot.return_value = _sample_snapshot()

        asyncio.get_event_loop().run_until_complete(
            service.camera_get_snapshot(entity_id="camera.cozinha")
        )

        camera_repo.get_snapshot.assert_awaited_once(), (
            "Expected camera_repo.get_snapshot to be awaited exactly once"
        )

    def test_camera_get_snapshot__passes_entity_id_to_repository(self):
        """The entity_id argument must be forwarded to the repository unchanged."""
        service, _, _, _, _, camera_repo = _make_service()
        camera_repo.get_snapshot.return_value = _sample_snapshot()

        asyncio.get_event_loop().run_until_complete(
            service.camera_get_snapshot(entity_id="camera.sala")
        )

        call_args = camera_repo.get_snapshot.call_args
        passed_entity_id = call_args[0][0] if call_args[0] else call_args[1].get("entity_id")
        assert passed_entity_id == "camera.sala", (
            f"Expected entity_id='camera.sala' forwarded to repo, got: {passed_entity_id!r}"
        )

    def test_camera_get_snapshot__returns_entity_from_repository(self):
        """The SmartHomeCameraSnapshot returned by the repository must be returned to the caller."""
        service, _, _, _, _, camera_repo = _make_service()
        expected = _sample_snapshot()
        camera_repo.get_snapshot.return_value = expected

        result = asyncio.get_event_loop().run_until_complete(
            service.camera_get_snapshot(entity_id="camera.cozinha")
        )

        assert result is expected, (
            f"Expected the exact snapshot returned by repository, got {result!r}"
        )

    def test_camera_get_snapshot__returns_smart_home_camera_snapshot_instance(self):
        """The return type must be SmartHomeCameraSnapshot."""
        service, _, _, _, _, camera_repo = _make_service()
        camera_repo.get_snapshot.return_value = _sample_snapshot()

        result = asyncio.get_event_loop().run_until_complete(
            service.camera_get_snapshot(entity_id="camera.cozinha")
        )

        assert isinstance(result, SmartHomeCameraSnapshot), (
            f"Expected SmartHomeCameraSnapshot instance, got {type(result)}"
        )


# ===========================================================================
# TestSmartHomeServiceCameraBackwardCompat
# ===========================================================================

@_SKIP_IF_NOT_IMPLEMENTED
class TestSmartHomeServiceCameraBackwardCompat:

    def test_service_constructed_without_camera_repository__does_not_raise(self):
        """
        SmartHomeService must remain constructable without smart_home_camera_repository
        to preserve backward compatibility with existing call sites (IoC, tests, etc.)
        that do not supply this argument.
        """
        light_repo = AsyncMock()
        config_repo = AsyncMock()
        alias_repo = MagicMock()
        climate_repo = AsyncMock()
        config_repo.get_all_exposed_entities_ids.return_value = []

        # Must not raise TypeError or any other exception
        try:
            service = SmartHomeService(
                smart_home_light_repository=light_repo,
                smart_home_configuration_repository=config_repo,
                smart_home_entity_alias_repository=alias_repo,
                smart_home_climate_repository=climate_repo,
            )
        except TypeError as exc:
            pytest.fail(
                f"SmartHomeService constructor raised TypeError when camera repo is omitted: {exc}"
            )

    def test_service_constructed_with_none_camera_repository__does_not_raise(self):
        """
        Explicitly passing smart_home_camera_repository=None must also be accepted
        without error.
        """
        light_repo = AsyncMock()
        config_repo = AsyncMock()
        alias_repo = MagicMock()
        climate_repo = AsyncMock()
        config_repo.get_all_exposed_entities_ids.return_value = []

        try:
            service = SmartHomeService(
                smart_home_light_repository=light_repo,
                smart_home_configuration_repository=config_repo,
                smart_home_entity_alias_repository=alias_repo,
                smart_home_climate_repository=climate_repo,
                smart_home_camera_repository=None,
            )
        except TypeError as exc:
            pytest.fail(
                f"SmartHomeService constructor raised TypeError for camera_repo=None: {exc}"
            )
