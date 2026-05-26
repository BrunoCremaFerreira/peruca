"""
SmartHomeSensorsGraph._classify_intent Unit Tests

These tests are written BEFORE the implementation exists (TDD).
They will be skipped (not error) until SmartHomeSensorsGraph is importable.

Key design constraints being verified:
  1. Uses json.loads() — NOT eval(). JSON booleans (true/false) and null must
     parse correctly without raising NameError.
  2. Alias repository is queried with entity_id_starts_with="sensor." (or
     "binary_sensor.") — NOT "light." or "climate.".
  3. Returns output fields: output_query_current_state, output_query_history,
     output_not_recognized.
  4. The classify node parses a compact encoding for sensor type + location:
     "door|cozinha" means sensor_type=door, location=cozinha.
     "motion|lavanderia|3" means sensor_type=motion, location=lavanderia, hours_back=3.
"""

import pytest
from unittest.mock import MagicMock, patch

from domain.entities import SmartHomeEntityAlias

try:
    from application.graphs.smart_home_sensors_graph import SmartHomeSensorsGraph
    _GRAPH_AVAILABLE = True
except ImportError:
    SmartHomeSensorsGraph = None  # type: ignore[assignment,misc]
    _GRAPH_AVAILABLE = False

_SKIP_IF_NOT_IMPLEMENTED = pytest.mark.skipif(
    not _GRAPH_AVAILABLE,
    reason="SmartHomeSensorsGraph not implemented yet",
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_graph() -> "SmartHomeSensorsGraph":
    """
    Build a SmartHomeSensorsGraph with all external dependencies mocked so
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

    with patch.object(SmartHomeSensorsGraph, "load_prompt", return_value="{input}"):
        graph = SmartHomeSensorsGraph(
            llm_chat=llm_chat,
            smart_home_service=smart_home_service,
            smart_home_entity_alias_repository=alias_repo,
        )

    return graph


def _configure_cleaned_output(graph: "SmartHomeSensorsGraph", cleaned_str: str) -> None:
    """
    Bypass the LLM call entirely: patch _remove_thinking_tag so that
    _classify_intent receives cleaned_str as the already-cleaned LLM output.
    """
    graph._remove_thinking_tag = MagicMock(return_value=cleaned_str)
    graph.llm_chat.invoke.return_value = MagicMock(content=cleaned_str)


# ===========================================================================
# TestSmartHomeSensorsGraphClassifyIntentQueryCurrentState
# ===========================================================================

@_SKIP_IF_NOT_IMPLEMENTED
class TestSmartHomeSensorsGraphClassifyIntentQueryCurrentState:

    def test_classify_query_current_state__door_cozinha__intent_and_fields_populated(self):
        """
        JSON with intents=["query_current_state"] and query_current_state="door|cozinha"
        must produce:
          - result["intent"] == ["query_current_state"]
          - "door" and "cozinha" extractable from result["output_query_current_state"]
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["query_current_state"], "query_current_state": "door|cozinha",'
            ' "query_history": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "a porta da cozinha está aberta?"})

        assert result["intent"] == ["query_current_state"], (
            f"Expected intent=['query_current_state'], got {result['intent']!r}"
        )
        assert "door" in result["output_query_current_state"], (
            f"Expected 'door' in output_query_current_state, got {result['output_query_current_state']!r}"
        )
        assert "cozinha" in result["output_query_current_state"], (
            f"Expected 'cozinha' in output_query_current_state, got {result['output_query_current_state']!r}"
        )

    def test_classify_query_current_state__temperature_no_location__empty_location(self):
        """
        When the LLM returns query_current_state="temperature|" (no location),
        the output field must still be populated and the intent must be set.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["query_current_state"], "query_current_state": "temperature|",'
            ' "query_history": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "qual é a temperatura?"})

        assert result["intent"] == ["query_current_state"], (
            f"Expected intent=['query_current_state'], got {result['intent']!r}"
        )
        assert "temperature" in result["output_query_current_state"], (
            f"Expected 'temperature' in output_query_current_state, "
            f"got {result['output_query_current_state']!r}"
        )

    def test_classify_intent_list__contains_query_current_state(self):
        """
        result["intent"] must be a list, not a string, even when there is only
        one intent. This mirrors the multi-intent contract of other graphs.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["query_current_state"], "query_current_state": "humidity|banheiro",'
            ' "query_history": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "qual a umidade no banheiro?"})

        assert isinstance(result["intent"], list), (
            f"Expected result['intent'] to be a list, got {type(result['intent'])}"
        )
        assert "query_current_state" in result["intent"], (
            f"Expected 'query_current_state' in intent list, got {result['intent']!r}"
        )

    def test_classify_query_current_state__motion_sala__intent_and_field_populated(self):
        """
        JSON with query_current_state="motion|sala" must map intent and output correctly.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["query_current_state"], "query_current_state": "motion|sala",'
            ' "query_history": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "tem alguém na sala?"})

        assert result["intent"] == ["query_current_state"]
        assert "motion" in result["output_query_current_state"]
        assert "sala" in result["output_query_current_state"]


# ===========================================================================
# TestSmartHomeSensorsGraphClassifyIntentQueryHistory
# ===========================================================================

@_SKIP_IF_NOT_IMPLEMENTED
class TestSmartHomeSensorsGraphClassifyIntentQueryHistory:

    def test_classify_query_history__motion_lavanderia__intent_and_fields_populated(self):
        """
        JSON with intents=["query_history"] and query_history="motion|lavanderia|3"
        must produce:
          - result["intent"] == ["query_history"]
          - output contains "motion", "lavanderia", and "3" (hours_back)
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["query_history"], "query_current_state": "",'
            ' "query_history": "motion|lavanderia|3", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "houve movimento na lavanderia nas últimas 3 horas?"})

        assert result["intent"] == ["query_history"], (
            f"Expected intent=['query_history'], got {result['intent']!r}"
        )
        assert "motion" in result["output_query_history"], (
            f"Expected 'motion' in output_query_history, got {result['output_query_history']!r}"
        )
        assert "lavanderia" in result["output_query_history"], (
            f"Expected 'lavanderia' in output_query_history, got {result['output_query_history']!r}"
        )

    def test_classify_query_history__hours_back_present_in_output(self):
        """
        The hours_back component ("3") must be present in the output_query_history field,
        allowing downstream nodes to extract it without re-calling the LLM.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["query_history"], "query_current_state": "",'
            ' "query_history": "temperature|sala|6", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "como variou a temperatura da sala nas últimas 6 horas?"})

        assert "6" in result["output_query_history"], (
            f"Expected hours_back '6' in output_query_history, got {result['output_query_history']!r}"
        )

    def test_classify_query_history__returns_history_intent(self):
        """
        The intent list must contain 'query_history' and nothing else
        when the input is a history query.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["query_history"], "query_current_state": "",'
            ' "query_history": "door|entrada|2", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "a porta da entrada abriu nas últimas 2 horas?"})

        assert "query_history" in result["intent"]
        assert "query_current_state" not in result["intent"]


# ===========================================================================
# TestSmartHomeSensorsGraphClassifyIntentNotRecognized
# ===========================================================================

@_SKIP_IF_NOT_IMPLEMENTED
class TestSmartHomeSensorsGraphClassifyIntentNotRecognized:

    def test_classify_not_recognized__unrelated_input__intent_is_not_recognized(self):
        """
        Input unrelated to sensors must produce result["intent"] == ["not_recognized"].
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["not_recognized"], "query_current_state": "",'
            ' "query_history": "", "not_recognized": "não entendido"}',
        )

        result = graph._classify_intent({"input": "toque uma música"})

        assert result["intent"] == ["not_recognized"], (
            f"Expected intent=['not_recognized'] for unrelated input, got {result['intent']!r}"
        )

    def test_classify_not_recognized__output_field_populated(self):
        """
        When intent is 'not_recognized', result['output_not_recognized'] must be
        populated with the LLM's explanation (not empty and not None).
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["not_recognized"], "query_current_state": "",'
            ' "query_history": "", "not_recognized": "esse comando não é sobre sensores"}',
        )

        result = graph._classify_intent({"input": "adicione leite na lista"})

        assert result.get("output_not_recognized"), (
            f"Expected output_not_recognized to be populated, got {result.get('output_not_recognized')!r}"
        )


# ===========================================================================
# TestSmartHomeSensorsGraphClassifyIntentRobustness
# ===========================================================================

@_SKIP_IF_NOT_IMPLEMENTED
class TestSmartHomeSensorsGraphClassifyIntentRobustness:

    def test_classify__handles_null_values_in_json(self):
        """
        JSON with null in optional fields must parse correctly without raising
        NameError. json.loads() handles null natively; eval() would raise NameError.
        The result must still have a valid intent list.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["query_current_state"], "query_current_state": "door|cozinha",'
            ' "query_history": null, "not_recognized": null}',
        )

        # Must not raise NameError or any other exception
        result = graph._classify_intent({"input": "a porta da cozinha está aberta?"})

        assert isinstance(result["intent"], list), (
            f"Expected intent to be a list even with null fields, got {type(result['intent'])}"
        )
        assert "query_current_state" in result["intent"]

    def test_classify__handles_missing_fields_in_json(self):
        """
        A JSON object that is missing some expected fields (e.g. no 'query_history')
        must not raise KeyError. Missing fields must be treated as empty/None.
        """
        graph = _make_graph()
        # JSON intentionally missing 'query_history' and 'not_recognized' fields
        _configure_cleaned_output(
            graph,
            '{"intents": ["query_current_state"], "query_current_state": "motion|sala"}',
        )

        # Must not raise KeyError
        result = graph._classify_intent({"input": "tem movimento na sala?"})

        assert isinstance(result["intent"], list)

    def test_classify__handles_empty_string_fields(self):
        """
        Fields with empty string values must be treated as absent/no-op and must
        not cause any exception. This is the most common LLM output pattern when
        a field is not applicable.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["query_history"], "query_current_state": "",'
            ' "query_history": "smoke|cozinha|1", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "houve fumaça na cozinha na última hora?"})

        assert result["intent"] == ["query_history"]

    def test_classify__invalid_json_text__falls_back_to_not_recognized(self):
        """
        When the LLM returns unparseable text (not JSON), the method must
        fall back gracefully: result["intent"] == ["not_recognized"].
        No exception must propagate.
        """
        graph = _make_graph()
        _configure_cleaned_output(graph, "Desculpe, não entendi o comando sobre sensores.")

        result = graph._classify_intent({"input": "algum input"})

        assert result["intent"] == ["not_recognized"], (
            f"Expected fallback to not_recognized for invalid JSON, got {result['intent']!r}"
        )

    def test_classify__empty_string_from_llm__falls_back_to_not_recognized(self):
        """
        An empty string from the LLM must trigger the not_recognized fallback.
        """
        graph = _make_graph()
        _configure_cleaned_output(graph, "")

        result = graph._classify_intent({"input": "algum input"})

        assert result["intent"] == ["not_recognized"], (
            f"Expected fallback to not_recognized for empty LLM output, got {result['intent']!r}"
        )

    def test_classify__json_missing_intents_field__falls_back_to_not_recognized(self):
        """
        Valid JSON that lacks the 'intents' key must produce not_recognized
        instead of raising KeyError.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"query_current_state": "door|sala"}',
        )

        result = graph._classify_intent({"input": "a porta está aberta?"})

        assert result["intent"] == ["not_recognized"], (
            f"Expected not_recognized when 'intents' key is absent, got {result['intent']!r}"
        )

    def test_classify__json_with_boolean_literals__parses_without_error(self):
        """
        JSON with boolean literals (true/false) must parse correctly.
        eval() raises NameError on 'true'/'false'; json.loads() handles them.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["query_current_state"], "query_current_state": "presence|sala",'
            ' "query_history": "", "not_recognized": "", "detected": true, "active": false}',
        )

        # Must not raise NameError
        result = graph._classify_intent({"input": "há alguém na sala?"})

        assert isinstance(result["intent"], list)
        assert "query_current_state" in result["intent"]


# ===========================================================================
# TestSmartHomeSensorsGraphClassifyIntentEntityAliasResolution
# ===========================================================================

@_SKIP_IF_NOT_IMPLEMENTED
class TestSmartHomeSensorsGraphClassifyIntentEntityAliasResolution:

    def test_classify__alias_repo_queried_for_sensor_entities(self):
        """
        The alias repository must be queried for sensor entities (entity_id_starts_with
        containing "sensor." or similar prefix — NOT "light." or "climate.").
        This guards against copy-paste errors from other graphs.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["query_current_state"], "query_current_state": "door|frente",'
            ' "query_history": "", "not_recognized": ""}',
        )

        graph._classify_intent({"input": "a porta da frente está aberta?"})

        # The alias repo must have been called — the exact prefix is implementation detail,
        # but it must NOT be "light." or "climate."
        assert graph.smart_home_entity_alias_repository.get_all.called, (
            "Expected alias repository get_all to be called during classify_intent"
        )
        call_kwargs = graph.smart_home_entity_alias_repository.get_all.call_args[1]
        prefix = call_kwargs.get("entity_id_starts_with", "")
        assert "light." not in prefix, (
            f"Alias repo must NOT be queried with 'light.' prefix for sensors, got: {prefix!r}"
        )
        assert "climate." not in prefix, (
            f"Alias repo must NOT be queried with 'climate.' prefix for sensors, got: {prefix!r}"
        )

    def test_classify__builds_available_entities_dict_from_aliases(self):
        """
        result['available_entities'] must be a dict built from alias repository
        as {alias: entity_id}.
        """
        graph = _make_graph()
        alias = SmartHomeEntityAlias(entity_id="binary_sensor.door_frente", alias="Porta da Frente")
        graph.smart_home_entity_alias_repository.get_all.return_value = [alias]
        _configure_cleaned_output(
            graph,
            '{"intents": ["query_current_state"], "query_current_state": "door|frente",'
            ' "query_history": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "a porta da frente está aberta?"})

        assert result["available_entities"] == {"Porta da Frente": "binary_sensor.door_frente"}, (
            f"Expected available_entities to map alias to entity_id, "
            f"got {result['available_entities']!r}"
        )

    def test_classify__empty_alias_list__available_entities_is_empty_dict(self):
        """
        When alias repository returns [], available_entities must be {} (not None).
        """
        graph = _make_graph()
        graph.smart_home_entity_alias_repository.get_all.return_value = []
        _configure_cleaned_output(
            graph,
            '{"intents": ["query_current_state"], "query_current_state": "temperature|sala",'
            ' "query_history": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "qual a temperatura da sala?"})

        assert result["available_entities"] == {}, (
            f"Expected empty dict for available_entities, got {result['available_entities']!r}"
        )

    def test_classify__alias_repo_raises__falls_back_to_not_recognized(self):
        """
        When the alias repository raises an exception, _classify_intent must
        fall back gracefully: intent=["not_recognized"], available_entities={}.
        """
        graph = _make_graph()
        graph.smart_home_entity_alias_repository.get_all.side_effect = RuntimeError("DB error")
        _configure_cleaned_output(
            graph,
            '{"intents": ["query_current_state"], "query_current_state": "door|cozinha",'
            ' "query_history": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "a porta da cozinha está aberta?"})

        assert result["intent"] == ["not_recognized"]
        assert result["available_entities"] == {}


# ===========================================================================
# TestSmartHomeSensorsGraphClassifyIntentMultipleIntents
# ===========================================================================

@_SKIP_IF_NOT_IMPLEMENTED
class TestSmartHomeSensorsGraphClassifyIntentMultipleIntents:

    def test_classify__multiple_intents__all_returned_in_order(self):
        """
        When the LLM returns multiple intents (e.g. query_current_state + query_history),
        all must appear in result["intent"] in the original order.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["query_current_state", "query_history"],'
            ' "query_current_state": "door|cozinha",'
            ' "query_history": "motion|cozinha|2", "not_recognized": ""}',
        )

        result = graph._classify_intent({
            "input": "a porta da cozinha está aberta e houve movimento lá nas últimas 2 horas?"
        })

        assert result["intent"] == ["query_current_state", "query_history"], (
            f"Expected both intents in order, got {result['intent']!r}"
        )
