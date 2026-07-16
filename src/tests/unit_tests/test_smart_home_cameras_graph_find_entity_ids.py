"""
SmartHomeCamerasGraph._find_entity_ids Unit Tests

TDD — written BEFORE the fix. The id_parser LLM can hallucinate free text
(e.g. it returned the sentence "Compreendido. Por favor, envie a string de
nomes e a lista de câmeras disponíveis...") instead of an entity_id or "None".
The current implementation accepts any non-"NONE"/non-empty token as an
entity_id, which produces a bogus GET /api/camera_proxy/<sentence> → 404.

Intended fix: _find_entity_ids must only return ids that actually exist in
`available_entities` (present in available_entities.values()); anything else is
discarded.

The parser is invoked via async_runner.run(_invoke_with_timeout()), which awaits
self.llm_chat.ainvoke(prompt) and reads response.content — so we mock
llm_chat.ainvoke as an AsyncMock returning an object exposing `.content`.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from application.graphs.smart_home_cameras_graph import SmartHomeCamerasGraph


_HALLUCINATED_SENTENCE = (
    "Compreendido. Por favor, envie a string de nomes e a lista de "
    "câmeras disponíveis para que eu possa processar a solicitação."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph() -> SmartHomeCamerasGraph:
    """
    Build a SmartHomeCamerasGraph with external dependencies mocked.

    load_prompt is patched persistently (also for the parser template used
    inside _find_entity_ids) so no filesystem access happens. The template
    must contain the {input} and {available_entities} placeholders because
    _find_entity_ids calls parser_template.format(input=..., available_entities=...).
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

    # Persistently stub load_prompt for the parser template used at call time.
    graph.load_prompt = MagicMock(return_value="{input} {available_entities}")
    return graph


def _stub_parser_output(graph: SmartHomeCamerasGraph, content: str) -> None:
    """Make the id_parser LLM return `content` as its response .content."""
    graph.llm_chat.ainvoke = AsyncMock(return_value=SimpleNamespace(content=content))


# ===========================================================================
# TestFindEntityIds
# ===========================================================================


class TestFindEntityIds:
    def test_find_entity_ids__hallucinated_sentence__returns_empty(self):
        """
        A free-text sentence that is NOT in available_entities.values() must be
        discarded — _find_entity_ids must return []. Guards against the
        GET /api/camera_proxy/<sentence> → 404 bug.
        """
        graph = _make_graph()
        _stub_parser_output(graph, _HALLUCINATED_SENTENCE)

        result = graph._find_entity_ids(
            "cozinha", available_entities={"cozinha": "camera.cozinha"}
        )

        assert result == [], (
            f"Hallucinated free text must be discarded, got: {result!r}"
        )

    def test_find_entity_ids__valid_entity_id__returns_it(self):
        """A valid entity_id present in available_entities must be returned."""
        graph = _make_graph()
        _stub_parser_output(graph, "camera.cozinha")

        result = graph._find_entity_ids(
            "cozinha", available_entities={"cozinha": "camera.cozinha"}
        )

        assert result == ["camera.cozinha"], (
            f"Expected ['camera.cozinha'], got: {result!r}"
        )

    def test_find_entity_ids__mixed_valid_and_invalid__returns_only_valid(self):
        """
        Pipe-delimited output mixing a valid id with hallucinated text must
        keep only the valid id.
        """
        graph = _make_graph()
        _stub_parser_output(graph, f"camera.cozinha|{_HALLUCINATED_SENTENCE}")

        result = graph._find_entity_ids(
            "cozinha", available_entities={"cozinha": "camera.cozinha"}
        )

        assert result == ["camera.cozinha"], (
            f"Expected only the valid id, got: {result!r}"
        )

    def test_find_entity_ids__none_token__returns_empty(self):
        """
        Regression: 'None' must continue to yield [] (existing behaviour must
        not break under the new filtering).
        """
        graph = _make_graph()
        _stub_parser_output(graph, "None")

        result = graph._find_entity_ids(
            "camera inexistente", available_entities={"cozinha": "camera.cozinha"}
        )

        assert result == [], f"Expected [], got: {result!r}"

    def test_find_entity_ids__injects_aliases_in_declared_prompt_format(self):
        """
        The id-parser prompt declares (and its few-shots show) the available
        cameras as `'friendly_name' = 'entity_id'` entries joined by ", ".
        The code must inject exactly that format — not the Python dict repr
        (`{'name': 'id'}`) that str(dict) produces.
        """
        graph = _make_graph()
        _stub_parser_output(graph, "camera.cozinha|camera.portao")

        graph._find_entity_ids(
            "cozinha|portão",
            available_entities={
                "Câmera da cozinha": "camera.cozinha",
                "Câmera do portão": "camera.portao",
            },
        )

        prompt_sent = graph.llm_chat.ainvoke.call_args.args[0]
        expected = (
            "'Câmera da cozinha' = 'camera.cozinha', "
            "'Câmera do portão' = 'camera.portao'"
        )
        assert expected in prompt_sent, (
            f"Aliases must be injected as 'name' = 'id' entries, got: {prompt_sent!r}"
        )
        assert "{'Câmera da cozinha': 'camera.cozinha'" not in prompt_sent, (
            "Python dict repr must not be injected into the parser prompt"
        )
