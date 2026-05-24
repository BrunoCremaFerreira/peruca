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
        json_with_null = '{"intents": ["turn_on"], "turn_off": null, "turn_on": "luz da sala"}'
        _configure_cleaned_output(graph, json_with_null)

        # Must not raise NameError
        result = graph._classify_intent({"input": "acenda a luz da sala"})

        assert "turn_on" in result["intent"], (
            f"Expected 'turn_on' in intent list, got: {result['intent']}"
        )

    def test_classify_intent__llm_returns_json_with_true_false__parses_without_error(self):
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
