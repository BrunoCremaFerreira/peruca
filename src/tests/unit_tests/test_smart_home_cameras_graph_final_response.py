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
