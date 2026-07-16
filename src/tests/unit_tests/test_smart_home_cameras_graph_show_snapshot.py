"""
SmartHomeCamerasGraph._handle_show_snapshot Unit Tests

These tests are written BEFORE the implementation exists (TDD).
They will be skipped (not error) until SmartHomeCamerasGraph is importable.

Key design constraints verified:
  1. _handle_show_snapshot calls _find_entity_ids to resolve the camera alias.
  2. Calls smart_home_service.camera_get_snapshot(entity_id).
  3. Returns output_show_snapshot that starts with "data:image/jpeg;base64,".
  4. The base64-encoded content decodes back to the original image_bytes.
  5. Handles gracefully the case where no entity_id is found.
  6. Returns {} when output_show_snapshot payload is None/empty.
"""

import asyncio
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from application.graphs.smart_home_cameras_graph import SmartHomeCamerasGraph
    from domain.entities import SmartHomeCameraSnapshot

    _GRAPH_AVAILABLE = True
except ImportError:
    SmartHomeCamerasGraph = None  # type: ignore[assignment,misc]
    SmartHomeCameraSnapshot = None  # type: ignore[assignment,misc]
    _GRAPH_AVAILABLE = False

_SKIP_IF_NOT_IMPLEMENTED = pytest.mark.skipif(
    not _GRAPH_AVAILABLE,
    reason="SmartHomeCamerasGraph not implemented yet",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph() -> "SmartHomeCamerasGraph":
    """
    Build a SmartHomeCamerasGraph with all external dependencies mocked.
    smart_home_service.camera_get_snapshot is an AsyncMock because the handler
    calls asyncio.run(service.camera_get_snapshot(...)).
    """
    llm_chat = MagicMock()
    smart_home_service = MagicMock()
    smart_home_service.camera_get_snapshot = AsyncMock()
    smart_home_service.camera_get_state = AsyncMock()
    alias_repo = MagicMock()
    alias_repo.get_all.return_value = []

    with patch.object(SmartHomeCamerasGraph, "load_prompt", return_value="{input}"):
        graph = SmartHomeCamerasGraph(
            llm_chat=llm_chat,
            smart_home_service=smart_home_service,
            smart_home_entity_alias_repository=alias_repo,
        )

    return graph


def _state(**kwargs) -> dict:
    """Build a minimal graph state dict with sensible None defaults."""
    defaults = {
        "input": "",
        "intent": [],
        "output_show_snapshot": None,
        "output_check_status": None,
        "output_not_recognized": None,
        "available_entities": {},
        "output": None,
    }
    defaults.update(kwargs)
    return defaults


def _make_snapshot(
    entity_id: str = "camera.cozinha",
    image_bytes: bytes = b"fake_jpeg",
    content_type: str = "image/jpeg",
) -> "SmartHomeCameraSnapshot":
    """Build a SmartHomeCameraSnapshot for use in mocked service responses."""
    return SmartHomeCameraSnapshot(
        entity_id=entity_id,
        image_bytes=image_bytes,
        content_type=content_type,
    )


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


# ===========================================================================
# TestHandleShowSnapshot
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestHandleShowSnapshot:
    def test_handle_show_snapshot__entity_found__calls_service_get_snapshot(self):
        """
        When _find_entity_ids resolves to a valid entity_id,
        smart_home_service.camera_get_snapshot must be called exactly once.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.cozinha"])
        graph.smart_home_service.camera_get_snapshot.return_value = _make_snapshot()
        state = _state(
            output_show_snapshot="cozinha",
            available_entities={"cozinha": "camera.cozinha"},
        )

        graph._handle_show_snapshot(state)

        (
            graph.smart_home_service.camera_get_snapshot.assert_called_once(),
            ("Expected camera_get_snapshot to be called exactly once"),
        )

    def test_handle_show_snapshot__entity_found__output_starts_with_data_uri(self):
        """
        The output_show_snapshot value must start with 'data:image/jpeg;base64,'
        so the consumer can render it directly as an HTML/base64 data URI.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.cozinha"])
        graph.smart_home_service.camera_get_snapshot.return_value = _make_snapshot(
            image_bytes=b"\xff\xd8\xff"
        )
        state = _state(
            output_show_snapshot="cozinha",
            available_entities={"cozinha": "camera.cozinha"},
        )

        result = graph._handle_show_snapshot(state)

        assert result.get("output_show_snapshot", "").startswith(
            "data:image/jpeg;base64,"
        ), (
            f"Expected output to start with 'data:image/jpeg;base64,', "
            f"got: {result.get('output_show_snapshot', '')[:60]!r}"
        )

    def test_handle_show_snapshot__entity_found__base64_encodes_image_bytes_correctly(
        self,
    ):
        """
        The base64 content after the data URI prefix must decode back to the
        original image_bytes from the snapshot. Tests encoding correctness.
        """
        raw_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.cozinha"])
        graph.smart_home_service.camera_get_snapshot.return_value = _make_snapshot(
            image_bytes=raw_bytes
        )
        state = _state(
            output_show_snapshot="cozinha",
            available_entities={"cozinha": "camera.cozinha"},
        )

        result = graph._handle_show_snapshot(state)

        output = result.get("output_show_snapshot", "")
        prefix = "data:image/jpeg;base64,"
        assert output.startswith(prefix), f"Missing data URI prefix in: {output[:80]!r}"

        b64_part = output[len(prefix) :]
        decoded = base64.b64decode(b64_part)
        assert decoded == raw_bytes, (
            f"Expected decoded bytes to match original image_bytes. "
            f"Got decoded={decoded!r}, expected={raw_bytes!r}"
        )

    def test_handle_show_snapshot__entity_not_found__returns_dispositivo_nao_encontrado(
        self,
    ):
        """
        When _find_entity_ids returns [], the handler must return a Portuguese
        'not found' message in output_show_snapshot instead of raising an error.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=[])
        state = _state(
            output_show_snapshot="camera inexistente",
            available_entities={},
        )

        result = graph._handle_show_snapshot(state)

        assert "output_show_snapshot" in result, (
            "Expected 'output_show_snapshot' key in result when entity not found"
        )
        assert result["output_show_snapshot"], (
            "Expected a non-empty message when entity is not found"
        )

    def test_handle_show_snapshot__empty_payload__returns_empty_dict(self):
        """
        When output_show_snapshot is None or empty in state, the handler
        must return {} without calling the service.
        """
        graph = _make_graph()
        state = _state(output_show_snapshot=None)

        result = graph._handle_show_snapshot(state)

        assert result == {}, f"Expected empty dict for None payload, got: {result}"
        graph.smart_home_service.camera_get_snapshot.assert_not_called()

    def test_handle_show_snapshot__entity_found__calls_find_entity_ids_with_payload(
        self,
    ):
        """
        _find_entity_ids must be called with the location string from
        output_show_snapshot so aliases are resolved correctly.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.cozinha"])
        graph.smart_home_service.camera_get_snapshot.return_value = _make_snapshot()
        available = {"cozinha": "camera.cozinha"}
        state = _state(
            output_show_snapshot="cozinha",
            available_entities=available,
        )

        graph._handle_show_snapshot(state)

        assert graph._find_entity_ids.called, (
            "Expected _find_entity_ids to be called for entity resolution"
        )
        call_args = graph._find_entity_ids.call_args
        # First positional arg must be the location/alias from output_show_snapshot
        location_arg = call_args[0][0] if call_args[0] else None
        assert location_arg == "cozinha" or "cozinha" in str(call_args), (
            f"Expected _find_entity_ids called with 'cozinha', got call_args={call_args!r}"
        )

    def test_handle_show_snapshot__entity_found__output_key_is_output_show_snapshot(
        self,
    ):
        """
        The returned dict must use the key 'output_show_snapshot', not any other key.
        Guards against copy-paste errors from other handlers.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.cozinha"])
        graph.smart_home_service.camera_get_snapshot.return_value = _make_snapshot()
        state = _state(
            output_show_snapshot="cozinha",
            available_entities={"cozinha": "camera.cozinha"},
        )

        result = graph._handle_show_snapshot(state)

        assert "output_show_snapshot" in result, (
            f"Expected key 'output_show_snapshot' in result, got keys: {list(result.keys())}"
        )
        assert "output_check_status" not in result, (
            "show_snapshot handler must not write to 'output_check_status'"
        )


# ===========================================================================
# TestHandleShowSnapshotContentType (F3 — dynamic MIME in the data URI)
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestHandleShowSnapshotContentType:
    def test_handle_show_snapshot__png_snapshot__data_uri_prefix_is_image_png(self):
        """
        F3: when the snapshot carries content_type='image/png', the data URI
        must declare image/png — never a hardcoded image/jpeg.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.sala"])
        graph.smart_home_service.camera_get_snapshot.return_value = _make_snapshot(
            entity_id="camera.sala",
            image_bytes=_PNG_MAGIC + b"fake_png_body",
            content_type="image/png",
        )
        state = _state(
            output_show_snapshot="sala",
            available_entities={"sala": "camera.sala"},
        )

        result = graph._handle_show_snapshot(state)

        output = result.get("output_show_snapshot", "")
        assert output.startswith("data:image/png;base64,"), (
            f"Expected data URI to start with 'data:image/png;base64,' for a "
            f"PNG snapshot, got: {output[:60]!r}"
        )

    def test_handle_show_snapshot__png_snapshot__base64_decodes_to_original_png_bytes(
        self,
    ):
        """
        F3 roundtrip: the base64 payload after the FIRST comma must decode back
        to the exact original PNG bytes (real magic bytes included).
        """
        raw_bytes = _PNG_MAGIC + b"\x00\x00\x00\rIHDRfake_png_payload"
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.sala"])
        graph.smart_home_service.camera_get_snapshot.return_value = _make_snapshot(
            entity_id="camera.sala",
            image_bytes=raw_bytes,
            content_type="image/png",
        )
        state = _state(
            output_show_snapshot="sala",
            available_entities={"sala": "camera.sala"},
        )

        result = graph._handle_show_snapshot(state)

        output = result.get("output_show_snapshot", "")
        assert "," in output, f"Expected a data URI with a comma, got: {output[:60]!r}"
        b64_part = output.split(",", 1)[1]
        decoded = base64.b64decode(b64_part)
        assert decoded == raw_bytes, (
            f"Expected decoded bytes to match the original PNG bytes. "
            f"Got decoded[:16]={decoded[:16]!r}, expected[:16]={raw_bytes[:16]!r}"
        )
        assert decoded.startswith(_PNG_MAGIC), (
            "Decoded payload lost the PNG magic bytes"
        )

    def test_handle_show_snapshot__snapshot_with_default_content_type__uri_uses_jpeg(
        self,
    ):
        """
        F3 backward compatibility: a snapshot constructed without an explicit
        content_type (entity default 'image/jpeg') must keep producing a
        'data:image/jpeg;base64,' URI.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.cozinha"])
        graph.smart_home_service.camera_get_snapshot.return_value = (
            SmartHomeCameraSnapshot(
                entity_id="camera.cozinha",
                image_bytes=b"\xff\xd8\xff\xe0fake_jpeg",
            )
        )
        state = _state(
            output_show_snapshot="cozinha",
            available_entities={"cozinha": "camera.cozinha"},
        )

        result = graph._handle_show_snapshot(state)

        output = result.get("output_show_snapshot", "")
        assert output.startswith("data:image/jpeg;base64,"), (
            f"Expected default-content-type snapshot to produce a jpeg URI, "
            f"got: {output[:60]!r}"
        )


# ===========================================================================
# TestHandleShowSnapshotMultiCamera (F4/F7 — iterate ALL resolved entity_ids)
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestHandleShowSnapshotMultiCamera:
    def test_handle_show_snapshot__two_cameras__two_data_uri_lines(self):
        """
        F4: when _find_entity_ids resolves TWO cameras, the handler must fetch
        BOTH snapshots and emit one data URI per line (2 lines total) —
        today only entity_ids[0] is used and the second camera is dropped.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(
            return_value=["camera.sala", "camera.garagem"]
        )
        snap_sala = _make_snapshot(
            entity_id="camera.sala", image_bytes=b"sala_bytes"
        )
        snap_garagem = _make_snapshot(
            entity_id="camera.garagem", image_bytes=b"garagem_bytes"
        )
        graph.smart_home_service.camera_get_snapshot.side_effect = [
            snap_sala,
            snap_garagem,
        ]
        state = _state(
            output_show_snapshot="sala|garagem",
            available_entities={
                "sala": "camera.sala",
                "garagem": "camera.garagem",
            },
        )

        result = graph._handle_show_snapshot(state)

        output = result.get("output_show_snapshot", "")
        uri_lines = [
            line
            for line in output.splitlines()
            if line.startswith("data:image/")
        ]
        assert len(uri_lines) == 2, (
            f"Expected 2 data URI lines (one per camera), got {len(uri_lines)}: "
            f"{output[:120]!r}"
        )
        assert graph.smart_home_service.camera_get_snapshot.call_count == 2, (
            "Expected camera_get_snapshot to be called once per resolved camera"
        )
        decoded = [
            base64.b64decode(line.split(",", 1)[1]) for line in uri_lines
        ]
        assert decoded == [b"sala_bytes", b"garagem_bytes"], (
            f"Expected both cameras' bytes in order, got {decoded!r}"
        )

    def test_handle_show_snapshot__more_than_cap__truncated_to_cap(self):
        """
        F4 cap: with more resolved cameras than _MAX_SNAPSHOTS_PER_REQUEST (3),
        only the first 3 snapshots may be fetched and emitted — N multi-MB
        URIs must not multiply the HTTP response unbounded.
        """
        graph = _make_graph()
        entity_ids = [
            "camera.sala",
            "camera.garagem",
            "camera.cozinha",
            "camera.portao",
        ]
        graph._find_entity_ids = MagicMock(return_value=entity_ids)
        graph.smart_home_service.camera_get_snapshot.side_effect = [
            _make_snapshot(entity_id=eid, image_bytes=eid.encode())
            for eid in entity_ids
        ]
        state = _state(
            output_show_snapshot="sala|garagem|cozinha|portao",
            available_entities={
                "sala": "camera.sala",
                "garagem": "camera.garagem",
                "cozinha": "camera.cozinha",
                "portao": "camera.portao",
            },
        )

        result = graph._handle_show_snapshot(state)

        output = result.get("output_show_snapshot", "")
        uri_lines = [
            line
            for line in output.splitlines()
            if line.startswith("data:image/")
        ]
        assert len(uri_lines) == 3, (
            f"Expected the output truncated to the cap of 3 data URI lines, "
            f"got {len(uri_lines)}"
        )
        assert graph.smart_home_service.camera_get_snapshot.call_count == 3, (
            "Snapshots beyond the cap must not even be fetched "
            f"(got {graph.smart_home_service.camera_get_snapshot.call_count} calls)"
        )

    def test_handle_show_snapshot__generic_request_with_available_entities__asks_to_specify(
        self,
    ):
        """
        F7: a generic request ("mostre todas as câmeras") reaches the handler
        with an empty/None payload. With cameras available, the handler must
        answer asking the user to specify which camera — NOT the misleading
        'Dispositivo não encontrado.' and NOT an empty {}.
        """
        graph = _make_graph()
        state = _state(
            output_show_snapshot=None,
            intent=["show_snapshot"],
            available_entities={
                "sala": "camera.sala",
                "garagem": "camera.garagem",
            },
        )

        result = graph._handle_show_snapshot(state)

        output = result.get("output_show_snapshot")
        assert output, (
            f"Expected a non-empty 'ask to specify' message for a generic "
            f"request with available cameras, got: {result!r}"
        )
        assert output != "Dispositivo não encontrado.", (
            "Generic request must not be answered with 'Dispositivo não "
            "encontrado.' when cameras exist"
        )
        assert not output.startswith("data:image/"), (
            "Generic request must not silently pick a camera and return a URI"
        )
        assert "qual" in output.lower() or "especifi" in output.lower(), (
            f"Expected the reply to ask the user to specify a camera, "
            f"got: {output!r}"
        )
        graph.smart_home_service.camera_get_snapshot.assert_not_called()
