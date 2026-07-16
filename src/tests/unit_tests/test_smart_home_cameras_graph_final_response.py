"""
SmartHomeCamerasGraph._handle_final_response Unit Tests

TDD — written BEFORE the fix. Today _handle_final_response returns
{"output": ""} when there is no snapshot, status, nor not_recognized signal.
An empty output violates the non-empty output contract of the chat pipeline.

Intended fix: never return an empty string — when `parts` is empty, return a
friendly, non-empty message (e.g. "Dispositivo não encontrado." or similar).
"""

from unittest.mock import MagicMock, patch

from application.graphs.smart_home_cameras_graph import SmartHomeCamerasGraph


def _make_graph() -> SmartHomeCamerasGraph:
    llm_chat = MagicMock()
    smart_home_service = MagicMock()
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


class TestHandleFinalResponseNonEmpty:
    def test_handle_final_response__no_outputs__returns_non_empty_string(self):
        """
        With no snapshot / status / not_recognized signals, output must still
        be a non-empty, human-readable string — never "".
        """
        graph = _make_graph()
        state = _state()

        result = graph._handle_final_response(state)

        output = result.get("output")
        assert isinstance(output, str), f"Expected str output, got: {type(output)}"
        assert output.strip() != "", (
            f"output must never be empty; got: {output!r}"
        )

    def test_handle_final_response__snapshot_present__returns_snapshot(self):
        """Regression: a present snapshot must still be surfaced in output."""
        graph = _make_graph()
        state = _state(output_show_snapshot="data:image/jpeg;base64,AAAA")

        result = graph._handle_final_response(state)

        assert result["output"] == "data:image/jpeg;base64,AAAA"


class TestHandleFinalResponseNotRecognizedCoexistence:
    """
    TDD — written BEFORE the fix (RED). On a compound message ("mostra a
    câmera da sala e apaga a luz da sala") the classify node emits
    ["show_snapshot", "not_recognized"]: the snapshot succeeds AND the
    non-camera half triggers not_recognized. Today _handle_final_response
    short-circuits on output_not_recognized and DISCARDS the successful
    snapshot — proven live by the merge-bypass integration test.

    Intended fix (deterministic, in code): the not_recognized message is
    returned ONLY when no other output exists. When show_snapshot and/or
    check_status outputs coexist with output_not_recognized, the successful
    outputs win and the not_recognized message is silently dropped — the
    non-camera part of the request is answered by the other MainGraph
    subgraphs, never by the cameras graph.
    """

    NOT_RECOGNIZED_MESSAGE = "Não consegui identificar qual câmera você quer consultar."

    def test_final_response__not_recognized_with_snapshot_output__returns_snapshot_uri(
        self,
    ):
        """A successful snapshot must survive a coexisting not_recognized."""
        graph = _make_graph()
        state = _state(
            output_show_snapshot="data:image/png;base64,AAAA",
            output_not_recognized=self.NOT_RECOGNIZED_MESSAGE,
        )

        result = graph._handle_final_response(state)

        assert "data:image/png;base64,AAAA" in result["output"], (
            f"Snapshot URI must be surfaced, got: {result['output']!r}"
        )
        assert self.NOT_RECOGNIZED_MESSAGE not in result["output"], (
            "not_recognized message must be dropped when a snapshot exists, "
            f"got: {result['output']!r}"
        )

    def test_final_response__not_recognized_with_check_status_output__returns_status(
        self,
    ):
        """A successful status line must survive a coexisting not_recognized."""
        graph = _make_graph()
        state = _state(
            output_check_status="Camera Sala: em espera",
            output_not_recognized=self.NOT_RECOGNIZED_MESSAGE,
        )

        result = graph._handle_final_response(state)

        assert "Camera Sala: em espera" in result["output"], (
            f"Status line must be surfaced, got: {result['output']!r}"
        )
        assert self.NOT_RECOGNIZED_MESSAGE not in result["output"], (
            "not_recognized message must be dropped when a status exists, "
            f"got: {result['output']!r}"
        )

    def test_final_response__not_recognized_with_snapshot_and_status__returns_both_joined(
        self,
    ):
        """Snapshot + status coexisting with not_recognized: both returned."""
        graph = _make_graph()
        state = _state(
            output_show_snapshot="data:image/png;base64,AAAA",
            output_check_status="Camera Sala: em espera",
            output_not_recognized=self.NOT_RECOGNIZED_MESSAGE,
        )

        result = graph._handle_final_response(state)

        assert result["output"] == (
            "data:image/png;base64,AAAA\nCamera Sala: em espera"
        ), (
            "Expected snapshot and status joined by a newline, "
            f"got: {result['output']!r}"
        )

    def test_final_response__only_not_recognized__still_returns_not_recognized_message(
        self,
    ):
        """Regression: not_recognized alone keeps its current message."""
        graph = _make_graph()
        state = _state(output_not_recognized=self.NOT_RECOGNIZED_MESSAGE)

        result = graph._handle_final_response(state)

        assert result["output"] == self.NOT_RECOGNIZED_MESSAGE
