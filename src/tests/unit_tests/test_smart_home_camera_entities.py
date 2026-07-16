"""
SmartHomeCamera and SmartHomeCameraSnapshot Entity Unit Tests

These tests are written BEFORE the implementation exists (TDD).
Unlike other test files in this project, this one does NOT use try/except ImportError
because it tests pure domain entities — if the import fails the test must FAIL (RED),
not skip.

Key design constraints verified:
  1. SmartHomeCamera requires entity_id and state; friendly_name and is_available are optional.
  2. SmartHomeCameraSnapshot requires entity_id and image_bytes; content_type defaults to
     "image/jpeg".
  3. Both are plain dataclasses — no framework imports.
"""

import pytest

from domain.entities import SmartHomeCamera, SmartHomeCameraSnapshot


# ===========================================================================
# TestSmartHomeCameraEntity
# ===========================================================================


class TestSmartHomeCameraEntity:
    def test_smart_home_camera__create_with_required_fields_only__succeeds(self):
        """
        SmartHomeCamera must be constructable with only entity_id and state.
        Optional fields (friendly_name, is_available) must default to None.
        """
        camera = SmartHomeCamera(entity_id="camera.cozinha", state="idle")

        assert camera.entity_id == "camera.cozinha", (
            f"Expected entity_id='camera.cozinha', got {camera.entity_id!r}"
        )
        assert camera.state == "idle", f"Expected state='idle', got {camera.state!r}"

    def test_smart_home_camera__optional_friendly_name_defaults_to_none(self):
        """When friendly_name is not supplied it must default to None."""
        camera = SmartHomeCamera(entity_id="camera.sala", state="idle")

        assert camera.friendly_name is None, (
            f"Expected friendly_name=None by default, got {camera.friendly_name!r}"
        )

    def test_smart_home_camera__optional_is_available_defaults_to_none(self):
        """When is_available is not supplied it must default to None."""
        camera = SmartHomeCamera(entity_id="camera.sala", state="idle")

        assert camera.is_available is None, (
            f"Expected is_available=None by default, got {camera.is_available!r}"
        )

    def test_smart_home_camera__create_with_all_fields__all_values_set(self):
        """
        SmartHomeCamera must accept all four fields and store them correctly.
        """
        camera = SmartHomeCamera(
            entity_id="camera.portao",
            state="recording",
            friendly_name="Portao Principal",
            is_available=True,
        )

        assert camera.entity_id == "camera.portao", (
            f"Expected entity_id='camera.portao', got {camera.entity_id!r}"
        )
        assert camera.state == "recording", (
            f"Expected state='recording', got {camera.state!r}"
        )
        assert camera.friendly_name == "Portao Principal", (
            f"Expected friendly_name='Portao Principal', got {camera.friendly_name!r}"
        )
        assert camera.is_available is True, (
            f"Expected is_available=True, got {camera.is_available!r}"
        )

    def test_smart_home_camera__state_idle__stored_correctly(self):
        """State value 'idle' must be stored as-is."""
        camera = SmartHomeCamera(entity_id="camera.cozinha", state="idle")

        assert camera.state == "idle"

    def test_smart_home_camera__state_recording__stored_correctly(self):
        """State value 'recording' must be stored as-is."""
        camera = SmartHomeCamera(entity_id="camera.cozinha", state="recording")

        assert camera.state == "recording"

    def test_smart_home_camera__state_streaming__stored_correctly(self):
        """State value 'streaming' must be stored as-is."""
        camera = SmartHomeCamera(entity_id="camera.cozinha", state="streaming")

        assert camera.state == "streaming"

    def test_smart_home_camera__state_unavailable__stored_correctly(self):
        """State value 'unavailable' must be stored as-is."""
        camera = SmartHomeCamera(entity_id="camera.cozinha", state="unavailable")

        assert camera.state == "unavailable"

    def test_smart_home_camera__is_available_false__stored_correctly(self):
        """is_available=False must not be confused with None."""
        camera = SmartHomeCamera(
            entity_id="camera.garagem",
            state="unavailable",
            is_available=False,
        )

        assert camera.is_available is False, (
            f"Expected is_available=False, got {camera.is_available!r}"
        )


# ===========================================================================
# TestSmartHomeCameraSnapshotEntity
# ===========================================================================


class TestSmartHomeCameraSnapshotEntity:
    def test_smart_home_camera_snapshot__create_with_required_fields_only__succeeds(
        self,
    ):
        """
        SmartHomeCameraSnapshot must be constructable with entity_id and image_bytes.
        content_type must default to 'image/jpeg'.
        """
        snapshot = SmartHomeCameraSnapshot(
            entity_id="camera.cozinha",
            image_bytes=b"\xff\xd8\xff",
        )

        assert snapshot.entity_id == "camera.cozinha", (
            f"Expected entity_id='camera.cozinha', got {snapshot.entity_id!r}"
        )
        assert snapshot.image_bytes == b"\xff\xd8\xff", (
            f"Expected correct image_bytes, got {snapshot.image_bytes!r}"
        )

    def test_smart_home_camera_snapshot__content_type_defaults_to_image_jpeg(self):
        """content_type must default to 'image/jpeg' when not supplied."""
        snapshot = SmartHomeCameraSnapshot(
            entity_id="camera.sala",
            image_bytes=b"fake_jpeg_data",
        )

        assert snapshot.content_type == "image/jpeg", (
            f"Expected content_type='image/jpeg', got {snapshot.content_type!r}"
        )

    def test_smart_home_camera_snapshot__create_with_all_fields__all_values_set(self):
        """SmartHomeCameraSnapshot must accept a custom content_type."""
        snapshot = SmartHomeCameraSnapshot(
            entity_id="camera.portao",
            image_bytes=b"fake_png_data",
            content_type="image/png",
        )

        assert snapshot.entity_id == "camera.portao"
        assert snapshot.image_bytes == b"fake_png_data"
        assert snapshot.content_type == "image/png"

    def test_smart_home_camera_snapshot__image_bytes_accepts_bytes(self):
        """image_bytes must store a bytes object exactly as provided."""
        raw = bytes(range(256))
        snapshot = SmartHomeCameraSnapshot(
            entity_id="camera.cozinha",
            image_bytes=raw,
        )

        assert snapshot.image_bytes is raw, (
            "Expected image_bytes to be the exact bytes object passed in"
        )

    def test_smart_home_camera_snapshot__image_bytes_can_be_empty(self):
        """image_bytes=b'' (empty) must be accepted without error."""
        snapshot = SmartHomeCameraSnapshot(
            entity_id="camera.cozinha",
            image_bytes=b"",
        )

        assert snapshot.image_bytes == b"", (
            f"Expected image_bytes=b'', got {snapshot.image_bytes!r}"
        )

    def test_smart_home_camera_snapshot__constructed_without_content_type__defaults_to_image_jpeg(
        self,
    ):
        """
        F3 backward-compatibility lock: every constructor call that predates the
        content_type wiring (entity_id + image_bytes only) must keep producing
        a snapshot whose content_type is exactly 'image/jpeg'.
        """
        snapshot = SmartHomeCameraSnapshot(
            entity_id="camera.cozinha",
            image_bytes=b"\xff\xd8\xff\xe0legacy_call",
        )

        assert snapshot.content_type == "image/jpeg", (
            f"Expected default content_type='image/jpeg' for legacy "
            f"constructor calls, got {snapshot.content_type!r}"
        )

    def test_smart_home_camera_snapshot__default_content_type_not_none(self):
        """content_type default must never be None — it must be a non-empty string."""
        snapshot = SmartHomeCameraSnapshot(
            entity_id="camera.cozinha",
            image_bytes=b"data",
        )

        assert snapshot.content_type is not None
        assert len(snapshot.content_type) > 0, (
            f"Expected a non-empty content_type, got {snapshot.content_type!r}"
        )
