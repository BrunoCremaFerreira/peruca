"""
OnlyTalkGraph {user_memories} injection Unit Tests (TDD - RED phase)

OnlyTalkGraph.invoke will start formatting the persona prompt with a new
{user_memories} placeholder, derived from invoke_request.memories:
  - non-empty memories -> rendered into the system message (bullet list)
  - empty memories      -> fallback text
      "(você ainda não tem memórias registradas sobre esta pessoa)"

Test strategy (deterministic, no real LLM / no RunnableWithMessageHistory run):
  - patch OnlyTalkGraph.load_prompt to a template exposing the placeholders
  - patch ChatPromptTemplate.from_messages to CAPTURE the formatted system
    message that invoke builds (first positional arg, the messages list).
  - the captured system text is then asserted.

The class-level _context_memory_store dict and unique user.id per test keep the
in-memory history isolated.

Expected to FAIL until OnlyTalkGraph.invoke formats with user_memories=.
"""

import uuid
from unittest.mock import MagicMock, patch

from application.graphs.only_talk_graph import OnlyTalkGraph
from domain.entities import GraphInvokeRequest, User


# ===========================================================================
# Helpers
# ===========================================================================

FALLBACK_TEXT = "(você ainda não tem memórias registradas sobre esta pessoa)"

# Template exposes every placeholder invoke is expected to pass.
_PROMPT_TEMPLATE = "{user_name}|{user_summary}|{user_memories}|{current_datetime}"


def _make_graph() -> OnlyTalkGraph:
    llm_chat = MagicMock()
    with patch.object(OnlyTalkGraph, "load_prompt", return_value=_PROMPT_TEMPLATE):
        graph = OnlyTalkGraph(llm_chat=llm_chat, provider="OLLAMA")
    return graph


def _make_request(memories) -> GraphInvokeRequest:
    user = User(
        id=str(uuid.uuid4()),
        external_id=str(uuid.uuid4()),
        name="Alice",
        summary="resumo",
    )
    return GraphInvokeRequest(message="oi", user=user, memories=memories)


def _capture_system_message(graph: OnlyTalkGraph, request: GraphInvokeRequest) -> str:
    """
    Run invoke while capturing the system message passed to
    ChatPromptTemplate.from_messages. The downstream chain is short-circuited
    by making from_messages return a MagicMock whose pipe yields a runnable
    that returns a fake AI response.
    """
    captured = {}

    real_response = MagicMock()
    real_response.content = "ok"

    def fake_from_messages(messages):
        # messages: [("system", <formatted>), MessagesPlaceholder, ("human", ...)]
        captured["system"] = messages[0][1]
        prompt_mock = MagicMock()
        # prompt | llm  -> chain ; chain wrapped by RunnableWithMessageHistory
        chain_mock = MagicMock()
        chain_mock.invoke.return_value = real_response
        prompt_mock.__or__.return_value = chain_mock
        return prompt_mock

    with patch(
        "application.graphs.only_talk_graph.ChatPromptTemplate.from_messages",
        side_effect=fake_from_messages,
    ), patch(
        "application.graphs.only_talk_graph.RunnableWithMessageHistory"
    ) as rwmh:
        rwmh.return_value.invoke.return_value = real_response
        graph.invoke(request)

    return captured["system"]


# ===========================================================================
# TestOnlyTalkGraphMemories
# ===========================================================================


class TestOnlyTalkGraphMemories:
    def setup_method(self):
        # Class-level store must be clean between tests.
        OnlyTalkGraph._context_memory_store.clear()

    def teardown_method(self):
        OnlyTalkGraph._context_memory_store.clear()

    def test_invoke__with_memories__system_message_contains_memory(self):
        # Arrange
        graph = _make_graph()
        request = _make_request(memories=["Prefere café sem açúcar"])
        # Act
        system_message = _capture_system_message(graph, request)
        # Assert
        assert "Prefere café sem açúcar" in system_message

    def test_invoke__empty_memories__system_message_contains_fallback(self):
        # Arrange
        graph = _make_graph()
        request = _make_request(memories=[])
        # Act
        system_message = _capture_system_message(graph, request)
        # Assert
        assert FALLBACK_TEXT in system_message
