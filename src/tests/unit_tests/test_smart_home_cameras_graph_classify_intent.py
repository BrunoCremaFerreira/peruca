"""
SmartHomeCamerasGraph._classify_intent Unit Tests

These tests are written BEFORE the implementation exists (TDD).
They will be skipped (not error) until SmartHomeCamerasGraph is importable.

Key design constraints verified:
  1. Uses json.loads() — NOT eval(). JSON booleans (true/false) and null must
     parse correctly without raising NameError.
  2. Alias repository is queried with entity_id_starts_with="camera." — NOT
     "light.", "sensor.", or any other prefix.
  3. Returns output fields: output_show_snapshot, output_check_status,
     output_not_recognized.
  4. Intents are returned as a list even for single-intent responses.
  5. Multiple cameras are pipe-delimited (e.g. "cozinha|portao").
  6. Both intents may appear in a single message (show_snapshot + check_status).
  7. Invalid/unparseable LLM output falls back to ["not_recognized"].
"""

import pytest
from unittest.mock import MagicMock, patch

from domain.entities import SmartHomeEntityAlias

try:
    from application.graphs.smart_home_cameras_graph import SmartHomeCamerasGraph

    _GRAPH_AVAILABLE = True
except ImportError:
    SmartHomeCamerasGraph = None  # type: ignore[assignment,misc]
    _GRAPH_AVAILABLE = False

_SKIP_IF_NOT_IMPLEMENTED = pytest.mark.skipif(
    not _GRAPH_AVAILABLE,
    reason="SmartHomeCamerasGraph not implemented yet",
)


# ===========================================================================
# Helpers
# ===========================================================================


def _make_graph() -> "SmartHomeCamerasGraph":
    """
    Build a SmartHomeCamerasGraph with all external dependencies mocked so
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

    with patch.object(SmartHomeCamerasGraph, "load_prompt", return_value="{input}"):
        graph = SmartHomeCamerasGraph(
            llm_chat=llm_chat,
            smart_home_service=smart_home_service,
            smart_home_entity_alias_repository=alias_repo,
        )

    return graph


def _configure_cleaned_output(graph: "SmartHomeCamerasGraph", cleaned_str: str) -> None:
    """
    Bypass the LLM call entirely: patch _remove_thinking_tag so that
    _classify_intent receives cleaned_str as the already-cleaned LLM output.
    """
    graph._remove_thinking_tag = MagicMock(return_value=cleaned_str)
    graph.llm_chat.invoke.return_value = MagicMock(content=cleaned_str)


# ===========================================================================
# TestSmartHomeCamerasGraphClassifyIntentShowSnapshot
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestSmartHomeCamerasGraphClassifyIntentShowSnapshot:
    def test_classify_show_snapshot__cozinha__intent_and_field_populated(self):
        """
        JSON with intents=["show_snapshot"] and show_snapshot="cozinha" must produce:
          - result["intent"] == ["show_snapshot"]
          - result["output_show_snapshot"] contains "cozinha"
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["show_snapshot"], "show_snapshot": "cozinha",'
            ' "check_status": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "mostre a camera da cozinha"})

        assert result["intent"] == ["show_snapshot"], (
            f"Expected intent=['show_snapshot'], got {result['intent']!r}"
        )
        assert "cozinha" in result["output_show_snapshot"], (
            f"Expected 'cozinha' in output_show_snapshot, got {result['output_show_snapshot']!r}"
        )

    def test_classify_show_snapshot__returns_intent_as_list(self):
        """
        result["intent"] must always be a list, not a string — even for a single intent.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["show_snapshot"], "show_snapshot": "sala",'
            ' "check_status": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "me mostra a camera da sala"})

        assert isinstance(result["intent"], list), (
            f"Expected list, got {type(result['intent'])}: {result['intent']!r}"
        )
        assert "show_snapshot" in result["intent"]

    def test_classify_show_snapshot__portao__output_field_contains_portao(self):
        """A different camera location ('portao') must appear in the output field."""
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["show_snapshot"], "show_snapshot": "portao",'
            ' "check_status": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "quero ver o portao"})

        assert "portao" in result["output_show_snapshot"], (
            f"Expected 'portao' in output_show_snapshot, got {result['output_show_snapshot']!r}"
        )

    def test_classify_show_snapshot__multiple_cameras_pipe_delimited__all_in_output(
        self,
    ):
        """
        When the LLM returns pipe-delimited camera locations (e.g. 'cozinha|portao'),
        both must be present in output_show_snapshot.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["show_snapshot"], "show_snapshot": "cozinha|portao",'
            ' "check_status": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "mostre a cozinha e o portao"})

        assert result["intent"] == ["show_snapshot"]
        assert "cozinha" in result["output_show_snapshot"], (
            f"Expected 'cozinha' in output_show_snapshot, got {result['output_show_snapshot']!r}"
        )
        assert "portao" in result["output_show_snapshot"], (
            f"Expected 'portao' in output_show_snapshot, got {result['output_show_snapshot']!r}"
        )


# ===========================================================================
# TestSmartHomeCamerasGraphClassifyIntentCheckStatus
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestSmartHomeCamerasGraphClassifyIntentCheckStatus:
    def test_classify_check_status__sala__intent_and_field_populated(self):
        """
        JSON with intents=["check_status"] and check_status="sala" must produce:
          - result["intent"] == ["check_status"]
          - result["output_check_status"] contains "sala"
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["check_status"], "show_snapshot": "",'
            ' "check_status": "sala", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "qual o estado da camera da sala?"})

        assert result["intent"] == ["check_status"], (
            f"Expected intent=['check_status'], got {result['intent']!r}"
        )
        assert "sala" in result["output_check_status"], (
            f"Expected 'sala' in output_check_status, got {result['output_check_status']!r}"
        )

    def test_classify_check_status__returns_intent_as_list(self):
        """result["intent"] must be a list for check_status as well."""
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["check_status"], "show_snapshot": "",'
            ' "check_status": "quarto", "not_recognized": ""}',
        )

        result = graph._classify_intent(
            {"input": "a camera do quarto esta funcionando?"}
        )

        assert isinstance(result["intent"], list)
        assert "check_status" in result["intent"]

    def test_classify_check_status__does_not_include_show_snapshot_in_intent(self):
        """When only check_status is requested, show_snapshot must not appear in intent list."""
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["check_status"], "show_snapshot": "",'
            ' "check_status": "cozinha", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "como esta a camera da cozinha?"})

        assert "show_snapshot" not in result["intent"], (
            f"Expected 'show_snapshot' absent from intent list, got {result['intent']!r}"
        )


# ===========================================================================
# TestSmartHomeCamerasGraphClassifyIntentNotRecognized
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestSmartHomeCamerasGraphClassifyIntentNotRecognized:
    def test_classify_not_recognized__unrelated_input__intent_is_not_recognized(self):
        """
        Input unrelated to cameras must produce result["intent"] == ["not_recognized"].
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["not_recognized"], "show_snapshot": "",'
            ' "check_status": "", "not_recognized": "nao entendido"}',
        )

        result = graph._classify_intent({"input": "acenda a luz da sala"})

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
            '{"intents": ["not_recognized"], "show_snapshot": "",'
            ' "check_status": "", "not_recognized": "esse comando nao e sobre cameras"}',
        )

        result = graph._classify_intent({"input": "adicione leite na lista"})

        assert result.get("output_not_recognized"), (
            f"Expected output_not_recognized to be populated, "
            f"got {result.get('output_not_recognized')!r}"
        )


# ===========================================================================
# TestSmartHomeCamerasGraphClassifyIntentMultipleIntents
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestSmartHomeCamerasGraphClassifyIntentMultipleIntents:
    def test_classify__both_intents__show_snapshot_and_check_status__all_returned(self):
        """
        When the LLM returns both show_snapshot and check_status, both must
        appear in result["intent"] in the original order.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["show_snapshot", "check_status"],'
            ' "show_snapshot": "cozinha", "check_status": "sala", "not_recognized": ""}',
        )

        result = graph._classify_intent(
            {"input": "mostre a cozinha e diga o status da sala"}
        )

        assert result["intent"] == ["show_snapshot", "check_status"], (
            f"Expected both intents in order, got {result['intent']!r}"
        )
        assert "cozinha" in result["output_show_snapshot"], (
            f"Expected 'cozinha' in output_show_snapshot, got {result['output_show_snapshot']!r}"
        )
        assert "sala" in result["output_check_status"], (
            f"Expected 'sala' in output_check_status, got {result['output_check_status']!r}"
        )


# ===========================================================================
# TestSmartHomeCamerasGraphClassifyIntentRobustness
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestSmartHomeCamerasGraphClassifyIntentRobustness:
    def test_classify__handles_null_values_in_json(self):
        """
        JSON with null in optional fields must parse correctly without raising
        NameError. json.loads() handles null natively; eval() would raise NameError.
        The result must still have a valid intent list.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["show_snapshot"], "show_snapshot": "cozinha",'
            ' "check_status": null, "not_recognized": null}',
        )

        # Must not raise NameError or any other exception
        result = graph._classify_intent({"input": "mostre a camera da cozinha"})

        assert isinstance(result["intent"], list), (
            f"Expected intent to be a list even with null fields, got {type(result['intent'])}"
        )
        assert "show_snapshot" in result["intent"]

    def test_classify__handles_missing_fields_in_json(self):
        """
        A JSON object missing some expected fields (e.g. no 'check_status')
        must not raise KeyError. Missing fields must be treated as empty/None.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["show_snapshot"], "show_snapshot": "sala"}',
        )

        # Must not raise KeyError
        result = graph._classify_intent({"input": "mostre a sala"})

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
            '{"intents": ["check_status"], "show_snapshot": "",'
            ' "check_status": "portao", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "como esta a camera do portao?"})

        assert result["intent"] == ["check_status"]

    def test_classify__invalid_json_text__falls_back_to_not_recognized(self):
        """
        When the LLM returns unparseable text (not JSON), the method must
        fall back gracefully: result["intent"] == ["not_recognized"].
        No exception must propagate.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph, "Desculpe, nao entendi o comando sobre cameras."
        )

        result = graph._classify_intent({"input": "algum input"})

        assert result["intent"] == ["not_recognized"], (
            f"Expected fallback to not_recognized for invalid JSON, got {result['intent']!r}"
        )

    def test_classify__empty_string_from_llm__falls_back_to_not_recognized(self):
        """An empty string from the LLM must trigger the not_recognized fallback."""
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
            '{"show_snapshot": "sala"}',
        )

        result = graph._classify_intent({"input": "me mostre a sala"})

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
            '{"intents": ["show_snapshot"], "show_snapshot": "cozinha",'
            ' "check_status": "", "not_recognized": "", "available": true, "streaming": false}',
        )

        # Must not raise NameError
        result = graph._classify_intent({"input": "mostre a camera da cozinha"})

        assert isinstance(result["intent"], list)
        assert "show_snapshot" in result["intent"]


# ===========================================================================
# TestSmartHomeCamerasGraphClassifyIntentEntityAliasResolution
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestSmartHomeCamerasGraphClassifyIntentEntityAliasResolution:
    def test_classify__alias_repo_queried_with_camera_prefix(self):
        """
        The alias repository must be queried for camera entities
        (entity_id_starts_with="camera.").
        This guards against copy-paste errors from other graphs that use
        "light.", "sensor.", or "climate." prefixes.
        """
        graph = _make_graph()
        _configure_cleaned_output(
            graph,
            '{"intents": ["show_snapshot"], "show_snapshot": "cozinha",'
            ' "check_status": "", "not_recognized": ""}',
        )

        graph._classify_intent({"input": "mostre a camera da cozinha"})

        assert graph.smart_home_entity_alias_repository.get_all.called, (
            "Expected alias repository get_all to be called during classify_intent"
        )
        call_kwargs = graph.smart_home_entity_alias_repository.get_all.call_args[1]
        prefix = call_kwargs.get("entity_id_starts_with", "")
        assert "camera." in prefix, (
            f"Expected alias repo queried with 'camera.' prefix, got: {prefix!r}"
        )
        assert "light." not in prefix, (
            f"Alias repo must NOT be queried with 'light.' prefix for cameras, got: {prefix!r}"
        )
        assert "sensor." not in prefix, (
            f"Alias repo must NOT be queried with 'sensor.' prefix for cameras, got: {prefix!r}"
        )

    def test_classify__builds_available_entities_dict_from_aliases(self):
        """
        result['available_entities'] must be a dict built from alias repository
        as {alias: entity_id}.
        """
        graph = _make_graph()
        alias = SmartHomeEntityAlias(entity_id="camera.cozinha", alias="Camera Cozinha")
        graph.smart_home_entity_alias_repository.get_all.return_value = [alias]
        _configure_cleaned_output(
            graph,
            '{"intents": ["show_snapshot"], "show_snapshot": "cozinha",'
            ' "check_status": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "mostre a camera da cozinha"})

        assert result["available_entities"] == {"Camera Cozinha": "camera.cozinha"}, (
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
            '{"intents": ["check_status"], "show_snapshot": "",'
            ' "check_status": "sala", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "status da camera da sala"})

        assert result["available_entities"] == {}, (
            f"Expected empty dict for available_entities, got {result['available_entities']!r}"
        )

    def test_classify__alias_repo_raises__falls_back_to_not_recognized(self):
        """
        When the alias repository raises an exception, _classify_intent must
        fall back gracefully: intent=["not_recognized"], available_entities={}.
        """
        graph = _make_graph()
        graph.smart_home_entity_alias_repository.get_all.side_effect = RuntimeError(
            "DB error"
        )
        _configure_cleaned_output(
            graph,
            '{"intents": ["show_snapshot"], "show_snapshot": "cozinha",'
            ' "check_status": "", "not_recognized": ""}',
        )

        result = graph._classify_intent({"input": "mostre a camera da cozinha"})

        assert result["intent"] == ["not_recognized"]
        assert result["available_entities"] == {}
