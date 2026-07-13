"""
OnlyTalkGraph read-only history Unit Tests (TDD - RED phase)

Bug being fixed:
    OnlyTalkGraph used RunnableWithMessageHistory, which AUTO-WRITES the turn to
    history. That made it the only writer, leaving non-conversational intents
    out of history and storing the RAW graph output rather than the consolidated
    answer the user receives.

Approved architectural fix (target of these tests):
    OnlyTalkGraph becomes READ-ONLY of the history. It must:
      - READ get_session_history(user.id).messages
      - inject those messages into the chain input under the `history` key
        (the MessagesPlaceholder(variable_name="history"))
      - invoke the chain WITHOUT auto-write (no RunnableWithMessageHistory)
      - NEVER call add_messages on the history.

These tests assert the INTENTION (reads history via the factory, injects the
read messages, never writes), not a fragile internal detail. The chain is
short-circuited by patching ChatPromptTemplate.from_messages so prompt | llm
yields a controllable chain whose `.invoke(input)` we inspect.

Expected to FAIL while OnlyTalkGraph still uses RunnableWithMessageHistory /
does not read & inject history.messages into the chain input.
"""

import uuid
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from application.graphs.only_talk_graph import OnlyTalkGraph
from domain.entities import GraphInvokeRequest, User


_TZ = "America/Sao_Paulo"


# ===========================================================================
# Helpers
# ===========================================================================

_PROMPT_TEMPLATE = "{user_name}|{user_summary}|{user_memories}|{current_datetime}"


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="resumo")


def _make_history(messages):
    """A history mock exposing `.messages` and a spyable `.add_messages`."""
    history = MagicMock()
    history.messages = messages
    return history


def _make_graph(get_session_history):
    llm_chat = MagicMock()
    with patch.object(OnlyTalkGraph, "load_prompt", return_value=_PROMPT_TEMPLATE):
        graph = OnlyTalkGraph(
            llm_chat=llm_chat,
            get_session_history=get_session_history,
        )
    return graph


def _invoke_capturing_chain_input(graph, request):
    """
    Run invoke while short-circuiting the LCEL chain.

    Patches ChatPromptTemplate.from_messages so that `prompt | llm` returns a
    chain whose `.invoke(input)` is captured. Returns the captured input dict.
    """
    captured = {}

    response = MagicMock()
    response.content = "resposta"

    chain_mock = MagicMock()

    def fake_invoke(input_payload, *args, **kwargs):
        captured["input"] = input_payload
        captured["config"] = kwargs.get("config")
        return response

    chain_mock.invoke.side_effect = fake_invoke

    def fake_from_messages(messages):
        prompt_mock = MagicMock()
        prompt_mock.__or__.return_value = chain_mock
        return prompt_mock

    with patch(
        "application.graphs.only_talk_graph.ChatPromptTemplate.from_messages",
        side_effect=fake_from_messages,
    ):
        result = graph.invoke(request)

    captured["result"] = result
    return captured


# ===========================================================================
# TestOnlyTalkGraphReadOnlyHistory
# ===========================================================================


class TestOnlyTalkGraphReadOnlyHistory:
    def test_invoke__reads_history_via_factory_with_user_id(self):
        # Arrange
        user = _sample_user()
        history = _make_history([HumanMessage(content="oi"), AIMessage(content="olá")])
        get_session_history = MagicMock(return_value=history)
        graph = _make_graph(get_session_history)
        request = GraphInvokeRequest(message="tudo bem?", user=user, memories=[], user_timezone=_TZ)
        # Act
        _invoke_capturing_chain_input(graph, request)
        # Assert
        get_session_history.assert_called_once_with(user.id)

    def test_invoke__injects_read_messages_into_chain_history_key(self):
        # Arrange
        prior = [HumanMessage(content="oi"), AIMessage(content="olá")]
        user = _sample_user()
        history = _make_history(prior)
        get_session_history = MagicMock(return_value=history)
        graph = _make_graph(get_session_history)
        request = GraphInvokeRequest(message="tudo bem?", user=user, memories=[], user_timezone=_TZ)
        # Act
        captured = _invoke_capturing_chain_input(graph, request)
        # Assert — the messages read from history are passed under `history`.
        assert "history" in captured["input"], (
            f"chain input must carry a 'history' key, got: {captured['input']!r}"
        )
        assert captured["input"]["history"] == prior

    def test_invoke__passes_current_message_as_input(self):
        # Arrange
        user = _sample_user()
        history = _make_history([])
        get_session_history = MagicMock(return_value=history)
        graph = _make_graph(get_session_history)
        request = GraphInvokeRequest(message="tudo bem?", user=user, memories=[], user_timezone=_TZ)
        # Act
        captured = _invoke_capturing_chain_input(graph, request)
        # Assert — `input` is now a one-element list of HumanMessage whose
        # content is the plain string (no image → string content, zero regression).
        input_messages = captured["input"].get("input")
        assert isinstance(input_messages, list) and len(input_messages) == 1
        assert input_messages[0].content == "tudo bem?"

    def test_invoke__does_not_write_history(self):
        # Arrange
        user = _sample_user()
        history = _make_history([HumanMessage(content="oi")])
        get_session_history = MagicMock(return_value=history)
        graph = _make_graph(get_session_history)
        request = GraphInvokeRequest(message="e aí?", user=user, memories=[], user_timezone=_TZ)
        # Act
        _invoke_capturing_chain_input(graph, request)
        # Assert — read-only: never writes.
        history.add_messages.assert_not_called()

    def test_invoke__invokes_chain_directly_not_via_auto_write_wrapper(self):
        # Arrange — the only writer of the turn must be LlmAppService.chat().
        # The fixed OnlyTalkGraph must invoke the plain `prompt | llm` chain
        # directly (passing input + history), instead of wrapping it in the
        # auto-writing RunnableWithMessageHistory. We assert the plain chain's
        # .invoke received the manually-built input dict (with `input` and
        # `history` keys). Under the old wrapper-based code the chain is invoked
        # by the wrapper with a different shape (no explicit `history` key from
        # us), so this fails until the refactor.
        user = _sample_user()
        history = _make_history([HumanMessage(content="oi")])
        get_session_history = MagicMock(return_value=history)
        graph = _make_graph(get_session_history)
        request = GraphInvokeRequest(message="e aí?", user=user, memories=[], user_timezone=_TZ)
        # Act
        captured = _invoke_capturing_chain_input(graph, request)
        # Assert — chain invoked directly with our explicit input + history.
        assert set(["input", "history"]).issubset(captured["input"].keys()), (
            "OnlyTalkGraph must invoke the plain chain directly with both "
            f"'input' and 'history' keys, got: {captured['input']!r}"
        )
        history.add_messages.assert_not_called()

    def test_invoke__empty_history__still_invokes_and_returns_response(self):
        # Arrange
        user = _sample_user()
        history = _make_history([])
        get_session_history = MagicMock(return_value=history)
        graph = _make_graph(get_session_history)
        request = GraphInvokeRequest(message="oi", user=user, memories=[], user_timezone=_TZ)
        # Act
        captured = _invoke_capturing_chain_input(graph, request)
        # Assert — return is now a dict {"output", "image_description"}.
        assert captured["input"].get("history") == []
        assert captured["result"]["output"] == "resposta"
        assert captured["result"]["image_description"] is None
        history.add_messages.assert_not_called()
