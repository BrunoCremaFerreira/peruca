"""
MemoryGraph Unit Tests (TDD - RED phase)

MemoryGraph is a single-step chain graph (prompt | llm, like OnlyTalkGraph),
not a StateGraph. Its invoke(GraphInvokeRequest) -> dict:
  - builds {existing_memories} from invoke_request.memories
  - calls the chain (prompt | llm)
  - applies _remove_thinking_tag and json.loads
  - falls back to {"memories": []} on parse failure (never raises)

Helper strategy mirrors test_shopping_list_graph_classify_intent.py:
  - _make_graph() patches load_prompt to avoid filesystem access
  - _configure_llm_output sets graph.llm_chat.return_value (the pipe operator
    calls llm_chat as a callable), with .content = raw_string
  - _remove_thinking_tag is NOT mocked, so the real cleaning pipeline runs
    (this is what strips ```fences``` and <think> tags)

Expected to FAIL with ImportError until
application.graphs.memory_graph.MemoryGraph exists.
"""

from unittest.mock import MagicMock, patch

from application.graphs.memory_graph import MemoryGraph
from domain.entities import GraphInvokeRequest


# ===========================================================================
# Helpers
# ===========================================================================


def _make_graph() -> MemoryGraph:
    """Build a MemoryGraph with the LLM mocked and load_prompt patched."""
    llm_chat = MagicMock()
    with patch.object(
        MemoryGraph,
        "load_prompt",
        return_value="{existing_memories}\n{input}",
    ):
        graph = MemoryGraph(llm_chat=llm_chat, provider="OLLAMA")
    return graph


def _configure_llm_output(graph: MemoryGraph, raw_string: str) -> None:
    """
    Configure the chain output. LangChain's pipe (prompt | llm_chat) calls
    llm_chat as a callable, so set llm_chat.return_value (not .invoke).
    _remove_thinking_tag is intentionally NOT mocked.
    """
    response = MagicMock()
    response.content = raw_string
    graph.llm_chat.return_value = response


def _make_invoke_request(message="meu café é sempre sem açúcar", memories=None):
    user = MagicMock()
    user.id = "user-1"
    user.name = "Alice"
    return GraphInvokeRequest(message=message, user=user, memories=memories or [])


# ===========================================================================
# TestMemoryGraphHappyPath
# ===========================================================================


class TestMemoryGraphHappyPath:
    def test_invoke__clean_json_with_fact__returns_memories_list(self):
        # Arrange
        graph = _make_graph()
        _configure_llm_output(graph, '{"memories": ["Prefere café sem açúcar"]}')
        # Act
        result = graph.invoke(_make_invoke_request())
        # Assert
        assert result["memories"] == ["Prefere café sem açúcar"]

    def test_invoke__multiple_facts__returns_all(self):
        # Arrange
        graph = _make_graph()
        _configure_llm_output(
            graph, '{"memories": ["Fato A", "Fato B"]}'
        )
        # Act
        result = graph.invoke(_make_invoke_request())
        # Assert
        assert result["memories"] == ["Fato A", "Fato B"]


# ===========================================================================
# TestMemoryGraphNonFactual
# ===========================================================================


class TestMemoryGraphNonFactual:
    def test_invoke__command_yields_empty_memories(self):
        # Arrange (a command like "liga a luz" must not become a memory)
        graph = _make_graph()
        _configure_llm_output(graph, '{"memories": []}')
        # Act
        result = graph.invoke(_make_invoke_request(message="liga a luz da sala"))
        # Assert
        assert result["memories"] == []


# ===========================================================================
# TestMemoryGraphCleaningPipeline
# ===========================================================================


class TestMemoryGraphCleaningPipeline:
    def test_invoke__json_wrapped_in_code_fence__parses_ok(self):
        # Arrange
        graph = _make_graph()
        raw = '```json\n{"memories": ["Prefere café sem açúcar"]}\n```'
        _configure_llm_output(graph, raw)
        # Act
        result = graph.invoke(_make_invoke_request())
        # Assert
        assert result["memories"] == ["Prefere café sem açúcar"]

    def test_invoke__output_with_think_tag__parses_ok(self):
        # Arrange
        graph = _make_graph()
        raw = '<think>\n\n</think>\n\n{"memories": ["Tem um gato chamado Mia"]}'
        _configure_llm_output(graph, raw)
        # Act
        result = graph.invoke(_make_invoke_request())
        # Assert
        assert result["memories"] == ["Tem um gato chamado Mia"]


# ===========================================================================
# TestMemoryGraphFallback
# ===========================================================================


class TestMemoryGraphFallback:
    def test_invoke__invalid_json__falls_back_to_empty_memories(self):
        # Arrange (natural-language, non-JSON output)
        graph = _make_graph()
        _configure_llm_output(graph, "Desculpe, não consegui extrair nada.")
        # Act
        result = graph.invoke(_make_invoke_request())
        # Assert
        assert result["memories"] == []

    def test_invoke__empty_string__falls_back_to_empty_memories(self):
        # Arrange
        graph = _make_graph()
        _configure_llm_output(graph, "")
        # Act
        result = graph.invoke(_make_invoke_request())
        # Assert
        assert result["memories"] == []
