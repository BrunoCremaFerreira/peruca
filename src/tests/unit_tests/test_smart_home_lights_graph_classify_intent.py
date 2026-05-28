from unittest.mock import MagicMock, patch
import pytest

from application.graphs.smart_home_lights_graph import SmartHomeLightsGraph


"""
SmartHomeLightsGraph._classify_intent Unit Tests

Covers one concrete bug:
  Line 57: `parsed = eval(cleaned) if isinstance(cleaned, str) else cleaned`
  eval() fails on valid JSON that contains 'null', 'true', or 'false' because
  those are JSON literals, not Python identifiers — Python raises NameError.
  The fix is to use json.loads() (or ast.literal_eval) instead of eval().
"""


def _make_graph() -> SmartHomeLightsGraph:
    """
    Build a SmartHomeLightsGraph with all external dependencies mocked so
    that the unit under test (_classify_intent) runs in full isolation.

    - llm_chat: mocked — its return value is controlled per test
    - smart_home_service: mocked AsyncMock (not exercised by _classify_intent)
    - smart_home_entity_alias_repository: mocked — returns empty alias list
    - load_prompt: patched to return a minimal template that accepts {input}
    """
    llm_chat = MagicMock()
    smart_home_service = MagicMock()
    alias_repo = MagicMock()
    alias_repo.get_all.return_value = []

    with patch.object(SmartHomeLightsGraph, "load_prompt", return_value="{input}"):
        graph = SmartHomeLightsGraph(
            llm_chat=llm_chat,
            smart_home_service=smart_home_service,
            smart_home_entity_alias_repository=alias_repo,
        )

    return graph


def _configure_cleaned_output(graph: SmartHomeLightsGraph, cleaned_str: str) -> None:
    """
    Bypass the LLM call entirely: patch _remove_thinking_tag so that
    _classify_intent receives cleaned_str as the already-cleaned LLM output.
    This makes the test focus exclusively on the eval() vs json.loads() bug.
    """
    graph._remove_thinking_tag = MagicMock(return_value=cleaned_str)


# ===========================================================================
# Bug — eval() raises NameError on JSON 'null'
# ===========================================================================


class TestClassifyIntentJsonParsing:
    def test_classify_intent__llm_returns_json_with_null__parses_without_error(self):
        """
        Bug: eval('{"intents": ["turn_on"], "turn_off": null}') raises
        NameError: name 'null' is not defined.
        After the fix (json.loads / ast.literal_eval), the result must contain
        the intents list without raising any exception.
        """
        graph = _make_graph()
        json_with_null = (
            '{"intents": ["turn_on"], "turn_off": null, "turn_on": "luz da sala"}'
        )
        _configure_cleaned_output(graph, json_with_null)

        # Must not raise NameError
        result = graph._classify_intent({"input": "acenda a luz da sala"})

        assert "turn_on" in result["intent"], (
            f"Expected 'turn_on' in intent list, got: {result['intent']}"
        )

    def test_classify_intent__llm_returns_json_with_true_false__parses_without_error(
        self,
    ):
        """
        Bug: eval('{"intents": ["turn_on"], "active": true}') raises
        NameError: name 'true' is not defined.
        After the fix (json.loads / ast.literal_eval), the result must contain
        the intents list without raising any exception.
        """
        graph = _make_graph()
        json_with_bool = '{"intents": ["turn_on"], "active": true, "confirmed": false}'
        _configure_cleaned_output(graph, json_with_bool)

        # Must not raise NameError
        result = graph._classify_intent({"input": "acenda a luz da sala"})

        assert "turn_on" in result["intent"], (
            f"Expected 'turn_on' in intent list, got: {result['intent']}"
        )


# ===========================================================================
# TestClassifyIntentArea — TDD for the area-based intents (5 new intents)
# ===========================================================================
#
# New intents introduced by the area feature:
#   - turn_on_by_area      (state field: output_turn_on_by_area)
#   - turn_off_by_area     (state field: output_turn_off_by_area)
#   - turn_on_all          (state field: output_turn_on_all)
#   - turn_off_all         (state field: output_turn_off_all)
#   - list_lights_status   (state field: output_list_lights_status)
#
# The classify_intent node must:
#   - Read parsed JSON fields with the same names as the intents (lower snake).
#   - Surface them as state["output_<intent>"] keys.
#   - When the LLM returns area_names as a list with more than one element,
#     preserve it as a list (the handler iterates).
#   - When the LLM returns intent='not_recognized', the area outputs must be None.


class TestClassifyIntentArea:
    def test_classify__turn_on_by_area__sets_intent_and_output(self):
        """
        LLM returns {'intents': ['turn_on_by_area'], 'turn_on_by_area': 'Cozinha'}.
        State must carry the intent and output_turn_on_by_area='Cozinha'.
        """
        graph = _make_graph()
        json_payload = (
            '{"intents": ["turn_on_by_area"], "turn_on_by_area": "Cozinha"}'
        )
        _configure_cleaned_output(graph, json_payload)

        result = graph._classify_intent({"input": "acenda as luzes da cozinha"})

        assert "turn_on_by_area" in result["intent"], (
            f"Expected 'turn_on_by_area' in intent list, got {result['intent']!r}"
        )
        assert result.get("output_turn_on_by_area") == "Cozinha", (
            f"Expected output_turn_on_by_area='Cozinha', got {result!r}"
        )

    def test_classify__turn_off_by_area__sets_intent_and_output(self):
        graph = _make_graph()
        json_payload = (
            '{"intents": ["turn_off_by_area"], "turn_off_by_area": "Sala"}'
        )
        _configure_cleaned_output(graph, json_payload)

        result = graph._classify_intent({"input": "apague as luzes da sala"})

        assert "turn_off_by_area" in result["intent"]
        assert result.get("output_turn_off_by_area") == "Sala"

    def test_classify__turn_on_all__sets_intent_and_truthy_flag(self):
        """
        For the 'all house' intents the LLM payload may set the field to a
        truthy value (string or True). The graph must surface that the intent
        was selected; the exact value is consumed by the handler.
        """
        graph = _make_graph()
        json_payload = '{"intents": ["turn_on_all"], "turn_on_all": true}'
        _configure_cleaned_output(graph, json_payload)

        result = graph._classify_intent(
            {"input": "ligue todas as luzes da casa"}
        )

        assert "turn_on_all" in result["intent"], (
            f"Expected 'turn_on_all' in intent list, got {result['intent']!r}"
        )
        assert result.get("output_turn_on_all"), (
            f"Expected truthy output_turn_on_all, got {result!r}"
        )

    def test_classify__turn_off_all__sets_intent_and_truthy_flag(self):
        graph = _make_graph()
        json_payload = '{"intents": ["turn_off_all"], "turn_off_all": true}'
        _configure_cleaned_output(graph, json_payload)

        result = graph._classify_intent(
            {"input": "desligue todas as luzes da casa"}
        )

        assert "turn_off_all" in result["intent"]
        assert result.get("output_turn_off_all")

    def test_classify__list_lights_status__sets_intent_and_truthy_flag(self):
        graph = _make_graph()
        json_payload = (
            '{"intents": ["list_lights_status"], "list_lights_status": true}'
        )
        _configure_cleaned_output(graph, json_payload)

        result = graph._classify_intent({"input": "mostre as luzes da casa"})

        assert "list_lights_status" in result["intent"]
        assert result.get("output_list_lights_status")

    def test_classify__multiple_areas__area_names_is_list_or_pipe_string(self):
        """
        When the user names multiple areas the LLM may return them either as a
        JSON list or a pipe-separated string. Either way the field must reach
        the state untouched (the handler is responsible for iteration).
        """
        graph = _make_graph()
        json_payload = (
            '{"intents": ["turn_on_by_area"], '
            '"turn_on_by_area": ["Cozinha", "Sala"]}'
        )
        _configure_cleaned_output(graph, json_payload)

        result = graph._classify_intent(
            {"input": "ligue as luzes da cozinha e da sala"}
        )

        assert "turn_on_by_area" in result["intent"]
        raw = result.get("output_turn_on_by_area")
        # Accept either a list or a pipe-string — both reach the handler
        if isinstance(raw, list):
            assert set(raw) >= {"Cozinha", "Sala"}, (
                f"Expected both areas in list, got {raw!r}"
            )
        else:
            assert "Cozinha" in str(raw) and "Sala" in str(raw), (
                f"Expected both areas in payload, got {raw!r}"
            )

    def test_classify__unknown_intent__falls_back_to_not_recognized(self):
        """When the LLM emits an unknown intent string, classify must coerce
        to ['not_recognized'] (no crash, no silent acceptance)."""
        graph = _make_graph()
        # No intents key at all -> default to not_recognized
        _configure_cleaned_output(graph, '{"foo": "bar"}')

        result = graph._classify_intent({"input": "blablabla"})

        assert "not_recognized" in result["intent"], (
            f"Expected 'not_recognized' fallback, got {result['intent']!r}"
        )
