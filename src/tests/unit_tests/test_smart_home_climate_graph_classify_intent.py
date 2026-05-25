"""
SmartHomeClimateGraph._classify_intent Unit Tests

These tests serve as the specification for the SmartHomeClimateGraph implementation.
The graph does not exist yet; the import is guarded with a try/except ImportError
so that the test file is always collectable — tests will xfail until the graph is
implemented.

Key differences from SmartHomeLightsGraph that this file exercises:
  1. Uses json.loads() — NOT eval(). JSON booleans (true/false) and null must
     parse correctly without raising NameError.
  2. Alias repository is queried with entity_id_starts_with="climate." — NOT "light.".
  3. Returns additional output fields: output_set_temperature, output_set_hvac_mode,
     output_query_state (not present in the lights graph).
"""

import pytest
from unittest.mock import MagicMock, patch

from domain.entities import SmartHomeEntityAlias

try:
    from application.graphs.smart_home_climate_graph import SmartHomeClimateGraph
    _GRAPH_AVAILABLE = True
except ImportError:
    SmartHomeClimateGraph = None  # type: ignore[assignment,misc]
    _GRAPH_AVAILABLE = False

_SKIP_IF_NOT_IMPLEMENTED = pytest.mark.skipif(
    not _GRAPH_AVAILABLE,
    reason="SmartHomeClimateGraph not implemented yet",
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_graph():
    """
    Build a SmartHomeClimateGraph with all external dependencies mocked so
    that the unit under test (_classify_intent) runs in full isolation.

    - load_prompt: patched to return a minimal template that accepts {input}
    - llm_chat: MagicMock — its return value is controlled per test
    - smart_home_service: MagicMock (not exercised by _classify_intent)
    - smart_home_entity_alias_repository: MagicMock — returns empty alias list
    """
    llm_chat = MagicMock()
    smart_home_service = MagicMock()
    alias_repo = MagicMock()
    alias_repo.get_all.return_value = []

    with patch.object(SmartHomeClimateGraph, "load_prompt", return_value="{input}"):
        graph = SmartHomeClimateGraph(
            llm_chat=llm_chat,
            smart_home_service=smart_home_service,
            smart_home_entity_alias_repository=alias_repo,
        )

    return graph


def _set_llm_response(graph, json_str: str) -> None:
    """
    Configure what the LLM will return for the next _classify_intent call.

    Patches _remove_thinking_tag so that _classify_intent receives json_str
    as the already-cleaned LLM output, bypassing the actual LLM invocation.
    """
    graph._remove_thinking_tag = MagicMock(return_value=json_str)
    graph.llm_chat.invoke.return_value = MagicMock(content=json_str)


# ===========================================================================
# TestClassifyIntentJsonParsing — parsing behaviour
# ===========================================================================

@_SKIP_IF_NOT_IMPLEMENTED
class TestClassifyIntentJsonParsing:

    def test_classify_intent__valid_json_turn_on__returns_turn_on_intent(self):
        """
        A well-formed JSON response with intents=["turn_on"] must produce
        result["intent"] == ["turn_on"].
        """
        graph = _make_graph()
        _set_llm_response(
            graph,
            '{"intents": ["turn_on"], "turn_on": "ar da sala", "turn_off": "",'
            ' "set_temperature": "", "set_hvac_mode": "", "query_state": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "ligue o ar da sala"})

        assert result["intent"] == ["turn_on"]

    def test_classify_intent__valid_json_set_temperature__returns_set_temperature_intent(self):
        """
        A well-formed JSON response with intents=["set_temperature"] must produce
        result["intent"] == ["set_temperature"].
        """
        graph = _make_graph()
        _set_llm_response(
            graph,
            '{"intents": ["set_temperature"], "turn_on": "", "turn_off": "",'
            ' "set_temperature": "ar da sala, 22", "set_hvac_mode": "", "query_state": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "coloque o ar da sala em 22 graus"})

        assert result["intent"] == ["set_temperature"]

    def test_classify_intent__valid_json_with_null_fields__does_not_raise(self):
        """
        JSON fields set to null must not raise any exception and result["intent"]
        must be a list (json.loads handles null natively; eval would raise NameError).
        """
        graph = _make_graph()
        _set_llm_response(
            graph,
            '{"intents": ["turn_on"], "turn_on": "ar da sala", "turn_off": null,'
            ' "set_temperature": null, "set_hvac_mode": null, "query_state": null, "not_recognized": null}',
        )

        result = graph._classify_intent({"input": "ligue o ar da sala"})

        assert isinstance(result["intent"], list)

    def test_classify_intent__json_with_boolean_true__does_not_raise(self):
        """
        JSON booleans (true / false) must parse correctly.
        eval() would raise NameError on 'true' and 'false' because they are JSON
        literals, not Python identifiers. json.loads() handles them natively.
        This test would fail if the implementation used eval() instead of json.loads().
        """
        graph = _make_graph()
        _set_llm_response(
            graph,
            '{"intents": ["turn_on"], "turn_on": "ar da sala", "active": true,'
            ' "confirmed": false, "turn_off": "", "set_temperature": "",'
            ' "set_hvac_mode": "", "query_state": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "ligue o ar da sala"})

        assert isinstance(result["intent"], list)
        assert "turn_on" in result["intent"]

    def test_classify_intent__invalid_json_text__falls_back_to_not_recognized(self):
        """
        When the LLM returns free text that cannot be parsed as JSON, the method
        must fall back gracefully: result["intent"] == ["not_recognized"].
        """
        graph = _make_graph()
        _set_llm_response(graph, "Desculpe, não entendi o comando.")

        result = graph._classify_intent({"input": "faça algo"})

        assert result["intent"] == ["not_recognized"]

    def test_classify_intent__empty_string__falls_back_to_not_recognized(self):
        """
        An empty string from the LLM must trigger the fallback path:
        result["intent"] == ["not_recognized"].
        """
        graph = _make_graph()
        _set_llm_response(graph, "")

        result = graph._classify_intent({"input": "faça algo"})

        assert result["intent"] == ["not_recognized"]

    def test_classify_intent__json_missing_intents_field__falls_back_to_not_recognized(self):
        """
        A valid JSON object that does not contain the 'intents' key must produce
        result["intent"] == ["not_recognized"] rather than raising a KeyError.
        """
        graph = _make_graph()
        _set_llm_response(graph, '{"turn_on": "ar da sala"}')

        result = graph._classify_intent({"input": "ligue o ar da sala"})

        assert result["intent"] == ["not_recognized"]


# ===========================================================================
# TestClassifyIntentOutputFields — field extraction
# ===========================================================================

@_SKIP_IF_NOT_IMPLEMENTED
class TestClassifyIntentOutputFields:

    def test_classify_intent__turn_on_field__populated_in_output_turn_on(self):
        """The 'turn_on' JSON field must be mapped to result['output_turn_on']."""
        graph = _make_graph()
        _set_llm_response(
            graph,
            '{"intents": ["turn_on"], "turn_on": "ar da sala", "turn_off": "",'
            ' "set_temperature": "", "set_hvac_mode": "", "query_state": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "ligue o ar da sala"})

        assert result["output_turn_on"] == "ar da sala"

    def test_classify_intent__turn_off_field__populated_in_output_turn_off(self):
        """The 'turn_off' JSON field must be mapped to result['output_turn_off']."""
        graph = _make_graph()
        _set_llm_response(
            graph,
            '{"intents": ["turn_off"], "turn_on": "", "turn_off": "ar do quarto",'
            ' "set_temperature": "", "set_hvac_mode": "", "query_state": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "desligue o ar do quarto"})

        assert result["output_turn_off"] == "ar do quarto"

    def test_classify_intent__set_temperature_field__populated_in_output_set_temperature(self):
        """The 'set_temperature' JSON field must be mapped to result['output_set_temperature']."""
        graph = _make_graph()
        _set_llm_response(
            graph,
            '{"intents": ["set_temperature"], "turn_on": "", "turn_off": "",'
            ' "set_temperature": "ar da sala, 22", "set_hvac_mode": "", "query_state": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "coloque o ar da sala em 22 graus"})

        assert result["output_set_temperature"] == "ar da sala, 22"

    def test_classify_intent__set_hvac_mode_field__populated_in_output_set_hvac_mode(self):
        """The 'set_hvac_mode' JSON field must be mapped to result['output_set_hvac_mode']."""
        graph = _make_graph()
        _set_llm_response(
            graph,
            '{"intents": ["set_hvac_mode"], "turn_on": "", "turn_off": "",'
            ' "set_temperature": "", "set_hvac_mode": "ar da sala, frio", "query_state": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "coloque o ar da sala no modo frio"})

        assert result["output_set_hvac_mode"] == "ar da sala, frio"

    def test_classify_intent__query_state_field__populated_in_output_query_state(self):
        """The 'query_state' JSON field must be mapped to result['output_query_state']."""
        graph = _make_graph()
        _set_llm_response(
            graph,
            '{"intents": ["query_state"], "turn_on": "", "turn_off": "",'
            ' "set_temperature": "", "set_hvac_mode": "", "query_state": "ar da sala", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "qual é a temperatura do ar da sala?"})

        assert result["output_query_state"] == "ar da sala"

    def test_classify_intent__not_recognized_field__populated_in_output_not_recognized(self):
        """The 'not_recognized' JSON field must be mapped to result['output_not_recognized']."""
        graph = _make_graph()
        _set_llm_response(
            graph,
            '{"intents": ["not_recognized"], "turn_on": "", "turn_off": "",'
            ' "set_temperature": "", "set_hvac_mode": "", "query_state": "", "not_recognized": "comando desconhecido"}',
        )

        result = graph._classify_intent({"input": "faça um bolo"})

        assert result["output_not_recognized"] == "comando desconhecido"


# ===========================================================================
# TestClassifyIntentEntityAliasResolution — alias repository integration
# ===========================================================================

@_SKIP_IF_NOT_IMPLEMENTED
class TestClassifyIntentEntityAliasResolution:

    def test_classify_intent__loads_climate_aliases_with_correct_prefix(self):
        """
        The alias repository must be queried with entity_id_starts_with="climate.",
        NOT with "light." (which is the prefix used by SmartHomeLightsGraph).
        This test will catch a copy-paste error in the prefix argument.
        """
        graph = _make_graph()
        _set_llm_response(
            graph,
            '{"intents": ["turn_on"], "turn_on": "ar da sala", "turn_off": "",'
            ' "set_temperature": "", "set_hvac_mode": "", "query_state": "", "not_recognized": ""}',
        )

        graph._classify_intent({"input": "ligue o ar da sala"})

        graph.smart_home_entity_alias_repository.get_all.assert_called_once_with(
            entity_id_starts_with="climate."
        )

    def test_classify_intent__builds_available_entities_dict_from_aliases(self):
        """
        The returned dict['available_entities'] must be built from the alias
        repository response as {alias: entity_id}.
        """
        graph = _make_graph()
        alias = SmartHomeEntityAlias(entity_id="climate.sala", alias="Ar da sala")
        graph.smart_home_entity_alias_repository.get_all.return_value = [alias]
        _set_llm_response(
            graph,
            '{"intents": ["turn_on"], "turn_on": "Ar da sala", "turn_off": "",'
            ' "set_temperature": "", "set_hvac_mode": "", "query_state": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "ligue o ar da sala"})

        assert result["available_entities"] == {"Ar da sala": "climate.sala"}

    def test_classify_intent__alias_repo_raises__falls_back_gracefully(self):
        """
        When the alias repository raises an exception (e.g. DB connectivity error),
        _classify_intent must fall back gracefully:
          - result["intent"] == ["not_recognized"]
          - result["available_entities"] == {}
        No exception must propagate to the caller.
        """
        graph = _make_graph()
        graph.smart_home_entity_alias_repository.get_all.side_effect = RuntimeError("DB error")
        _set_llm_response(
            graph,
            '{"intents": ["turn_on"], "turn_on": "ar da sala", "turn_off": "",'
            ' "set_temperature": "", "set_hvac_mode": "", "query_state": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "ligue o ar da sala"})

        assert result["intent"] == ["not_recognized"]
        assert result["available_entities"] == {}

    def test_classify_intent__empty_alias_list__available_entities_is_empty_dict(self):
        """
        When the alias repository returns an empty list, result['available_entities']
        must be an empty dict (not None and not a list).
        """
        graph = _make_graph()
        graph.smart_home_entity_alias_repository.get_all.return_value = []
        _set_llm_response(
            graph,
            '{"intents": ["turn_on"], "turn_on": "ar da sala", "turn_off": "",'
            ' "set_temperature": "", "set_hvac_mode": "", "query_state": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "ligue o ar da sala"})

        assert result["available_entities"] == {}


# ===========================================================================
# TestClassifyIntentMultipleIntents — multi-intent support
# ===========================================================================

@_SKIP_IF_NOT_IMPLEMENTED
class TestClassifyIntentMultipleIntents:

    def test_classify_intent__multiple_intents__all_returned(self):
        """
        When the LLM returns more than one intent (e.g. turn_on + set_temperature),
        all of them must appear in result["intent"] in the original order.
        """
        graph = _make_graph()
        _set_llm_response(
            graph,
            '{"intents": ["turn_on", "set_temperature"], "turn_on": "ar da sala",'
            ' "turn_off": "", "set_temperature": "ar da sala, 22",'
            ' "set_hvac_mode": "", "query_state": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "ligue o ar da sala em 22 graus"})

        assert result["intent"] == ["turn_on", "set_temperature"]
