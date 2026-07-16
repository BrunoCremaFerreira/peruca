"""
LlmAppService conversation-history write Unit Tests (TDD - RED phase)

Bug being fixed:
    Conversation history was only persisted on the `only_talking` path (via the
    auto-write of RunnableWithMessageHistory inside OnlyTalkGraph). Any other
    intent (lights, list, sensors, music) left the whole turn out of history,
    creating gaps. And even on only_talking it stored the RAW OnlyTalkGraph
    output, not the consolidated `_handle_final_response` answer the user gets.

Approved architectural fix (target of these tests):
    LlmAppService.chat() becomes the single, always-on writer of the turn.
    After obtaining `output = result.get("output")`, it persists
        [HumanMessage(content=message), AIMessage(content=output)]
    via a `get_session_history` factory injected in the constructor, keyed by
    `user.id` — for ANY intent. Guards:
      - do not write when output is empty/None/whitespace
      - wrap the write in try/except so a Redis failure never breaks the reply.

New constructor contract:
    LlmAppService(main_graph, context_repository, user_repository,
                  user_memory_service, music_service=None,
                  get_session_history=<Callable[[str], BaseChatMessageHistory]>)

Expected to FAIL until LlmAppService.chat() writes the turn:
  - missing `get_session_history` ctor kwarg -> TypeError, or
  - add_messages never called -> AssertionError.
"""

import uuid
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from application.appservices.llm_app_service import LlmAppService
from application.appservices.view_models import ChatRequest
from domain.entities import User
from domain.exceptions import NofFoundValidationError


# ===========================================================================
# Helpers
# ===========================================================================


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="resumo")


def _make_service(user=None, invoke_result=None):
    """
    Build a LlmAppService with all dependencies mocked, including the new
    `get_session_history` factory.

    Returns (service, main_graph, get_session_history, history).
    """
    main_graph = MagicMock()
    main_graph.invoke.return_value = invoke_result or {
        "output": "ok",
        "intent": ["only_talking"],
    }

    context_repository = MagicMock()

    user_repository = MagicMock()
    user_repository.get_by_external_id.return_value = user

    user_memory_service = MagicMock()
    user_memory_service.get_all_by_user.return_value = []

    history = MagicMock()
    get_session_history = MagicMock(return_value=history)

    service = LlmAppService(
        main_graph=main_graph,
        context_repository=context_repository,
        user_repository=user_repository,
        user_memory_service=user_memory_service,
        get_session_history=get_session_history,
    )
    return service, main_graph, get_session_history, history


def _request(user: User) -> ChatRequest:
    return ChatRequest(
        message="oi", external_user_id=user.external_id, chat_id="c1"
    )


def _assert_turn_written(history: MagicMock, message: str, output: str) -> None:
    """The single add_messages call must carry Human(message) + AI(output)."""
    history.add_messages.assert_called_once()
    written = history.add_messages.call_args[0][0]
    assert isinstance(written, list)
    assert len(written) == 2

    human, ai = written
    assert isinstance(human, HumanMessage)
    assert human.content == message
    assert isinstance(ai, AIMessage)
    assert ai.content == output


# ===========================================================================
# TestLlmAppServiceWritesTurn
# ===========================================================================


class TestLlmAppServiceWritesTurn:
    def test_chat__non_conversational_intent__writes_turn_once(self):
        # Arrange — the main gap: a lights intent must still be recorded.
        user = _sample_user()
        service, _, get_session_history, history = _make_service(
            user=user,
            invoke_result={
                "intent": ["smart_home_lights"],
                "output": "Liguei a luz",
            },
        )
        request = _request(user)
        # Act
        service.chat(request)
        # Assert — the factory is also consulted by the recent_history hint
        # (read-only), so we pin the write itself: exactly one persisted turn.
        assert all(
            call.args == (user.id,)
            for call in get_session_history.call_args_list
        )
        _assert_turn_written(history, message="oi", output="Liguei a luz")

    def test_chat__only_talking_intent__writes_consolidated_output(self):
        # Arrange — must store the consolidated `output`, not the raw graph text.
        user = _sample_user()
        service, _, _, history = _make_service(
            user=user,
            invoke_result={
                "intent": ["only_talking"],
                "output": "Resposta consolidada",
            },
        )
        request = _request(user)
        # Act
        service.chat(request)
        # Assert
        _assert_turn_written(history, message="oi", output="Resposta consolidada")

    def test_chat__multiple_intents__writes_single_consolidated_turn(self):
        # Arrange — multi-intent must write exactly once, with the merged output.
        user = _sample_user()
        service, _, _, history = _make_service(
            user=user,
            invoke_result={
                "intent": ["smart_home_lights", "only_talking"],
                "output": "Liguei a luz e estou bem, obrigado!",
            },
        )
        request = _request(user)
        # Act
        service.chat(request)
        # Assert
        _assert_turn_written(
            history,
            message="oi",
            output="Liguei a luz e estou bem, obrigado!",
        )

    def test_chat__uses_user_id_as_session_key(self):
        # Arrange
        user = _sample_user()
        service, _, get_session_history, _ = _make_service(user=user)
        request = _request(user)
        # Act
        service.chat(request)
        # Assert — same key the OnlyTalkGraph reads from. Both the
        # recent_history hint (read) and _persist_turn (write) must use it.
        assert get_session_history.call_args_list
        assert all(
            call.args == (user.id,)
            for call in get_session_history.call_args_list
        )


# ===========================================================================
# TestLlmAppServiceDoesNotWrite
# ===========================================================================


class TestLlmAppServiceDoesNotWrite:
    @pytest.mark.parametrize("output", [None, "", "   ", "\n\t "])
    def test_chat__empty_or_whitespace_output__does_not_write(self, output):
        # Arrange
        user = _sample_user()
        service, _, _, history = _make_service(
            user=user,
            invoke_result={"intent": ["only_talking"], "output": output},
        )
        request = _request(user)
        # Act
        service.chat(request)
        # Assert
        history.add_messages.assert_not_called()

    def test_chat__unknown_user__does_not_write(self):
        # Arrange
        service, main_graph, get_session_history, history = _make_service(user=None)
        request = ChatRequest(
            message="oi", external_user_id=str(uuid.uuid4()), chat_id="c1"
        )
        # Act / Assert — preserves existing not-found behaviour.
        with pytest.raises(NofFoundValidationError):
            service.chat(request)
        main_graph.invoke.assert_not_called()
        history.add_messages.assert_not_called()


# ===========================================================================
# TestLlmAppServiceWriteFailureIsSwallowed
# ===========================================================================


class TestLlmAppServiceWriteFailureIsSwallowed:
    def test_chat__history_write_raises__still_returns_output(self):
        # Arrange — a Redis failure must not break the reply.
        user = _sample_user()
        service, _, _, history = _make_service(
            user=user,
            invoke_result={"intent": ["only_talking"], "output": "Tudo certo"},
        )
        history.add_messages.side_effect = RuntimeError("redis down")
        request = _request(user)
        # Act — must not raise.
        result = service.chat(request)
        # Assert
        assert result == {"intents": ["only_talking"], "output": "Tudo certo"}

    def test_chat__get_session_history_raises__still_returns_output(self):
        # Arrange — even building the history can fail and must be swallowed.
        user = _sample_user()
        service, _, get_session_history, _ = _make_service(
            user=user,
            invoke_result={"intent": ["only_talking"], "output": "Resposta"},
        )
        get_session_history.side_effect = RuntimeError("redis unreachable")
        request = _request(user)
        # Act — must not raise.
        result = service.chat(request)
        # Assert
        assert result["output"] == "Resposta"
