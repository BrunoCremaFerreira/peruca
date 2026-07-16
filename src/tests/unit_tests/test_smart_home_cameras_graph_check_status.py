"""
SmartHomeCamerasGraph._handle_check_status Unit Tests

These tests are written BEFORE the implementation exists (TDD).
They will be skipped (not error) until SmartHomeCamerasGraph is importable.

Key design constraints verified:
  1. _handle_check_status calls smart_home_service.camera_get_state(entity_id).
  2. Returns output_check_status as a non-empty string describing the camera state.
  3. Handles all known HA camera states: "idle", "recording", "streaming", "unavailable".
  4. Handles gracefully the case where no entity_id is found.
  5. Returns {} when output_check_status payload is None/empty.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from application.graphs.smart_home_cameras_graph import SmartHomeCamerasGraph
    from domain.entities import SmartHomeCamera

    _GRAPH_AVAILABLE = True
except ImportError:
    SmartHomeCamerasGraph = None  # type: ignore[assignment,misc]
    SmartHomeCamera = None  # type: ignore[assignment,misc]
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
    smart_home_service.camera_get_state is an AsyncMock because the handler
    calls asyncio.run(service.camera_get_state(...)).
    """
    llm_chat = MagicMock()
    smart_home_service = MagicMock()
    smart_home_service.camera_get_state = AsyncMock()
    smart_home_service.camera_get_snapshot = AsyncMock()
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


def _make_camera(
    entity_id: str = "camera.cozinha",
    state: str = "idle",
    friendly_name: str = "Camera Cozinha",
    is_available: bool = True,
) -> "SmartHomeCamera":
    """Build a SmartHomeCamera entity for use in mocked service responses."""
    return SmartHomeCamera(
        entity_id=entity_id,
        state=state,
        friendly_name=friendly_name,
        is_available=is_available,
    )


# ===========================================================================
# TestHandleCheckStatus
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestHandleCheckStatus:
    def test_handle_check_status__entity_found__calls_service_get_state(self):
        """
        When _find_entity_ids resolves to a valid entity_id,
        smart_home_service.camera_get_state must be called exactly once.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.cozinha"])
        graph.smart_home_service.camera_get_state.return_value = _make_camera()
        state = _state(
            output_check_status="cozinha",
            available_entities={"cozinha": "camera.cozinha"},
        )

        graph._handle_check_status(state)

        (
            graph.smart_home_service.camera_get_state.assert_called_once(),
            ("Expected camera_get_state to be called exactly once"),
        )

    def test_handle_check_status__entity_found__returns_non_empty_string(self):
        """
        The output_check_status value must be a non-empty string.
        It must describe the camera state in a human-readable way.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.cozinha"])
        graph.smart_home_service.camera_get_state.return_value = _make_camera(
            state="idle"
        )
        state = _state(
            output_check_status="cozinha",
            available_entities={"cozinha": "camera.cozinha"},
        )

        result = graph._handle_check_status(state)

        output = result.get("output_check_status")
        assert output is not None, "Expected output_check_status to be populated"
        assert isinstance(output, str), (
            f"Expected output_check_status to be a str, got {type(output)}"
        )
        assert len(output) > 0, "Expected non-empty output_check_status string"

    def test_handle_check_status__state_idle__output_contains_state_info(self):
        """
        When the camera state is 'idle', the output string must contain
        information about the state (e.g. 'idle' or a description of it).
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.cozinha"])
        graph.smart_home_service.camera_get_state.return_value = _make_camera(
            state="idle"
        )
        state = _state(
            output_check_status="cozinha",
            available_entities={"cozinha": "camera.cozinha"},
        )

        result = graph._handle_check_status(state)

        output = result.get("output_check_status", "")
        assert output, "Expected non-empty output_check_status for state='idle'"

    def test_handle_check_status__state_recording__output_contains_state_info(self):
        """
        When the camera state is 'recording', the output string must reflect
        that state in a meaningful way.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.cozinha"])
        graph.smart_home_service.camera_get_state.return_value = _make_camera(
            state="recording"
        )
        state = _state(
            output_check_status="cozinha",
            available_entities={"cozinha": "camera.cozinha"},
        )

        result = graph._handle_check_status(state)

        output = result.get("output_check_status", "")
        assert output, "Expected non-empty output_check_status for state='recording'"

    def test_handle_check_status__state_streaming__output_contains_state_info(self):
        """
        When the camera state is 'streaming', the output string must reflect
        that state in a meaningful way.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.cozinha"])
        graph.smart_home_service.camera_get_state.return_value = _make_camera(
            state="streaming"
        )
        state = _state(
            output_check_status="cozinha",
            available_entities={"cozinha": "camera.cozinha"},
        )

        result = graph._handle_check_status(state)

        output = result.get("output_check_status", "")
        assert output, "Expected non-empty output_check_status for state='streaming'"

    def test_handle_check_status__state_unavailable__output_contains_state_info(self):
        """
        When the camera state is 'unavailable', the output must still be a
        non-empty string informing the user that the device is unavailable.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.cozinha"])
        graph.smart_home_service.camera_get_state.return_value = _make_camera(
            state="unavailable",
            is_available=False,
        )
        state = _state(
            output_check_status="cozinha",
            available_entities={"cozinha": "camera.cozinha"},
        )

        result = graph._handle_check_status(state)

        output = result.get("output_check_status", "")
        assert output, "Expected non-empty output_check_status for state='unavailable'"

    def test_handle_check_status__entity_not_found__returns_dispositivo_nao_encontrado(
        self,
    ):
        """
        When _find_entity_ids returns [], the handler must return a message in
        output_check_status indicating the device was not found.
        It must not raise an exception.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=[])
        state = _state(
            output_check_status="camera inexistente",
            available_entities={},
        )

        result = graph._handle_check_status(state)

        assert "output_check_status" in result, (
            "Expected 'output_check_status' key in result when entity not found"
        )
        assert result["output_check_status"], (
            "Expected a non-empty message when entity is not found"
        )

    def test_handle_check_status__empty_payload__returns_empty_dict(self):
        """
        When output_check_status is None or empty in state, the handler
        must return {} without calling the service.
        """
        graph = _make_graph()
        state = _state(output_check_status=None)

        result = graph._handle_check_status(state)

        assert result == {}, f"Expected empty dict for None payload, got: {result}"
        graph.smart_home_service.camera_get_state.assert_not_called()

    def test_handle_check_status__output_key_is_output_check_status(self):
        """
        The returned dict must use the key 'output_check_status', not any other key.
        Guards against copy-paste errors from other handlers.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.cozinha"])
        graph.smart_home_service.camera_get_state.return_value = _make_camera()
        state = _state(
            output_check_status="cozinha",
            available_entities={"cozinha": "camera.cozinha"},
        )

        result = graph._handle_check_status(state)

        assert "output_check_status" in result, (
            f"Expected key 'output_check_status' in result, got keys: {list(result.keys())}"
        )
        assert "output_show_snapshot" not in result, (
            "check_status handler must not write to 'output_show_snapshot'"
        )

    def test_handle_check_status__does_not_call_get_snapshot(self):
        """
        _handle_check_status must only call camera_get_state, never camera_get_snapshot.
        Using the wrong service method would fetch binary image data unnecessarily.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.cozinha"])
        graph.smart_home_service.camera_get_state.return_value = _make_camera()
        state = _state(
            output_check_status="cozinha",
            available_entities={"cozinha": "camera.cozinha"},
        )

        graph._handle_check_status(state)

        (
            graph.smart_home_service.camera_get_snapshot.assert_not_called(),
            ("check_status handler must not call camera_get_snapshot"),
        )


# ===========================================================================
# TestHandleCheckStatusPtBrStates (F5 — closed pt-BR state map)
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestHandleCheckStatusPtBrStates:
    @pytest.mark.parametrize(
        "ha_state,expected_pt_br",
        [
            ("idle", "em espera"),
            ("recording", "gravando"),
            ("streaming", "transmitindo ao vivo"),
            ("unavailable", "indisponível"),
        ],
    )
    def test_handle_check_status__known_states__mapped_to_pt_br(
        self, ha_state, expected_pt_br
    ):
        """
        F5: the four known HA camera states must be presented in pt-BR while
        the friendly_name is preserved — e.g. 'Camera Sala: gravando'.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.sala"])
        graph.smart_home_service.camera_get_state.return_value = _make_camera(
            entity_id="camera.sala",
            state=ha_state,
            friendly_name="Camera Sala",
        )
        state = _state(
            output_check_status="sala",
            available_entities={"sala": "camera.sala"},
        )

        result = graph._handle_check_status(state)

        output = result.get("output_check_status", "")
        assert output == f"Camera Sala: {expected_pt_br}", (
            f"Expected 'Camera Sala: {expected_pt_br}' for HA state "
            f"{ha_state!r}, got: {output!r}"
        )

    def test_handle_check_status__unknown_state__falls_back_to_raw_state(self):
        """
        F5: a state outside the closed map (e.g. 'buffering') must fall back
        to the raw state — never crash and never invent a translation.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.sala"])
        graph.smart_home_service.camera_get_state.return_value = _make_camera(
            entity_id="camera.sala",
            state="buffering",
            friendly_name="Camera Sala",
        )
        state = _state(
            output_check_status="sala",
            available_entities={"sala": "camera.sala"},
        )

        result = graph._handle_check_status(state)

        output = result.get("output_check_status", "")
        assert output == "Camera Sala: buffering", (
            f"Expected fallback to the raw state for an unmapped value, "
            f"got: {output!r}"
        )

    def test_handle_check_status__uppercase_known_state__still_mapped(self):
        """
        F5: the map lookup must be case-insensitive (state.lower()) — an
        uppercase 'IDLE' from HA must still map to 'em espera'.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["camera.sala"])
        graph.smart_home_service.camera_get_state.return_value = _make_camera(
            entity_id="camera.sala",
            state="IDLE",
            friendly_name="Camera Sala",
        )
        state = _state(
            output_check_status="sala",
            available_entities={"sala": "camera.sala"},
        )

        result = graph._handle_check_status(state)

        output = result.get("output_check_status", "")
        assert output == "Camera Sala: em espera", (
            f"Expected case-insensitive mapping for 'IDLE', got: {output!r}"
        )


# ===========================================================================
# TestHandleCheckStatusMultiCamera (F4 — iterate ALL resolved entity_ids)
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestHandleCheckStatusMultiCamera:
    def test_handle_check_status__two_cameras__two_status_lines(self):
        """
        F4: when _find_entity_ids resolves TWO cameras, the handler must query
        BOTH states and join one status line per camera — today only
        entity_ids[0] is reported and the second camera is silently ignored.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(
            return_value=["camera.sala", "camera.garagem"]
        )
        graph.smart_home_service.camera_get_state.side_effect = [
            _make_camera(
                entity_id="camera.sala",
                state="idle",
                friendly_name="Camera Sala",
            ),
            _make_camera(
                entity_id="camera.garagem",
                state="recording",
                friendly_name="Camera Garagem",
            ),
        ]
        state = _state(
            output_check_status="sala|garagem",
            available_entities={
                "sala": "camera.sala",
                "garagem": "camera.garagem",
            },
        )

        result = graph._handle_check_status(state)

        output = result.get("output_check_status", "")
        lines = [line for line in output.splitlines() if line.strip()]
        assert len(lines) == 2, (
            f"Expected 2 status lines (one per camera), got {len(lines)}: "
            f"{output!r}"
        )
        assert lines[0] == "Camera Sala: em espera", (
            f"Expected first line 'Camera Sala: em espera', got: {lines[0]!r}"
        )
        assert lines[1] == "Camera Garagem: gravando", (
            f"Expected second line 'Camera Garagem: gravando', got: {lines[1]!r}"
        )
        assert graph.smart_home_service.camera_get_state.call_count == 2, (
            "Expected camera_get_state to be called once per resolved camera"
        )
