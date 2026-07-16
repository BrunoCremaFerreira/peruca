"""
LlmAppService._recent_history_hint Unit Tests (TDD — RED phase)

Feature: add shopping-list items from the conversation context. The
ShoppingListGraph classifier needs the recent history as a TEXTUAL hint, built
once per request by LlmAppService.chat() and injected into
context_hints["recent_history"] (same pattern as user_vehicles / user_pets).

Pinned contract for the builder `_recent_history_hint(user_id) -> str`:
  - window: last 2 full turns (4 messages), read from the same
    get_session_history factory _persist_turn writes to, chronological order;
  - line format: "usuario: <content>" for HumanMessage, "peruca: <content>"
    for AIMessage, joined with "\n";
  - each message is passed through sanitize_for_prompt BEFORE joining (its
    internal newlines are collapsed; the "\n" separators are added afterwards
    by construction) and must NOT be cut by the sanitizer's default 500-char
    cap — the last answer holds the ingredients;
  - total cap of ~3000 chars, truncating the OLDEST messages first; the most
    recent message stays intact;
  - best-effort: empty history, missing factory or a read error all yield the
    literal "(vazio)" (never an empty string, never an exception);
  - non-string message content (multimodal blocks) is skipped without crashing.

Expected to FAIL until the builder exists (AttributeError) and chat() wires the
hint into context_hints (KeyError on the wire test).
"""

import uuid
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from application.appservices.llm_app_service import LlmAppService
from application.appservices.view_models import ChatRequest
from domain.entities import User


_HINT_CAP_CHARS = 3000


# ===========================================================================
# Helpers
# ===========================================================================


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="resumo")


def _history_with(messages):
    history = MagicMock()
    history.messages = messages
    return history


def _make_service(user=None, messages=None, get_session_history="default"):
    """
    Build a LlmAppService with all dependencies mocked. `messages` seeds the
    session history the hint builder reads. Pass get_session_history=None to
    simulate a service wired without the factory.

    Returns (service, main_graph, get_session_history, history).
    """
    main_graph = MagicMock()
    main_graph.invoke.return_value = {"output": "ok", "intent": ["only_talking"]}

    user_repository = MagicMock()
    user_repository.get_by_external_id.return_value = user

    user_memory_service = MagicMock()
    user_memory_service.get_all_by_user.return_value = []

    history = _history_with(messages or [])
    if get_session_history == "default":
        get_session_history = MagicMock(return_value=history)

    service = LlmAppService(
        main_graph=main_graph,
        context_repository=MagicMock(),
        user_repository=user_repository,
        user_memory_service=user_memory_service,
        get_session_history=get_session_history,
    )
    return service, main_graph, get_session_history, history


def _turns(*pairs):
    """Build a flat [Human, AI, Human, AI, ...] message list from turn pairs."""
    messages = []
    for human_text, ai_text in pairs:
        messages.append(HumanMessage(content=human_text))
        messages.append(AIMessage(content=ai_text))
    return messages


# ===========================================================================
# TestRecentHistoryHintWindow
# ===========================================================================


class TestRecentHistoryHintWindow:
    def test_hint__two_turns__four_messages_in_chronological_order(self):
        # Arrange
        user = _sample_user()
        service, _, _, _ = _make_service(
            user=user,
            messages=_turns(
                ("como se faz bolo de laranja?", "Você vai precisar de 3 ovos."),
                ("e a cobertura?", "Use suco de 2 laranjas."),
            ),
        )
        # Act
        hint = service._recent_history_hint(user.id)
        # Assert — exact format and chronological order
        assert hint == (
            "usuario: como se faz bolo de laranja?\n"
            "peruca: Você vai precisar de 3 ovos.\n"
            "usuario: e a cobertura?\n"
            "peruca: Use suco de 2 laranjas."
        )

    def test_hint__five_turns__keeps_only_last_four_messages(self):
        # Arrange — 5 turns = 10 messages; only the last 4 messages (2 turns)
        # may enter the hint.
        user = _sample_user()
        service, _, _, _ = _make_service(
            user=user,
            messages=_turns(
                ("m1", "r1"),
                ("m2", "r2"),
                ("m3", "r3"),
                ("m4", "r4"),
                ("m5", "r5"),
            ),
        )
        # Act
        hint = service._recent_history_hint(user.id)
        # Assert
        assert hint == (
            "usuario: m4\nperuca: r4\nusuario: m5\nperuca: r5"
        )

    def test_hint__single_turn__two_messages(self):
        # Arrange — fewer messages than the window: use what exists.
        user = _sample_user()
        service, _, _, _ = _make_service(
            user=user, messages=_turns(("oi", "olá"))
        )
        # Act
        hint = service._recent_history_hint(user.id)
        # Assert
        assert hint == "usuario: oi\nperuca: olá"


# ===========================================================================
# TestRecentHistoryHintFallbacks
# ===========================================================================


class TestRecentHistoryHintFallbacks:
    def test_hint__empty_history__returns_vazio(self):
        # Arrange
        user = _sample_user()
        service, _, _, _ = _make_service(user=user, messages=[])
        # Act
        hint = service._recent_history_hint(user.id)
        # Assert — the literal placeholder, never an empty string
        assert hint == "(vazio)"

    def test_hint__no_session_history_factory__returns_vazio(self):
        # Arrange — service wired without get_session_history
        user = _sample_user()
        service, _, _, _ = _make_service(user=user, get_session_history=None)
        # Act
        hint = service._recent_history_hint(user.id)
        # Assert
        assert hint == "(vazio)"

    def test_hint__factory_raises__returns_vazio_without_raising(self):
        # Arrange — best-effort, like _persist_turn: a Redis failure must not
        # break the chat request.
        user = _sample_user()
        factory = MagicMock(side_effect=RuntimeError("redis unreachable"))
        service, _, _, _ = _make_service(user=user, get_session_history=factory)
        # Act — must not raise
        hint = service._recent_history_hint(user.id)
        # Assert
        assert hint == "(vazio)"

    def test_hint__messages_read_raises__returns_vazio_without_raising(self):
        # Arrange — the .messages access itself can hit the backend and fail.
        user = _sample_user()

        class _BrokenHistory:
            @property
            def messages(self):
                raise RuntimeError("redis down")

        factory = MagicMock(return_value=_BrokenHistory())
        service, _, _, _ = _make_service(user=user, get_session_history=factory)
        # Act — must not raise
        hint = service._recent_history_hint(user.id)
        # Assert
        assert hint == "(vazio)"


# ===========================================================================
# TestRecentHistoryHintSanitization
# ===========================================================================


class TestRecentHistoryHintSanitization:
    def test_hint__message_with_internal_newlines__collapsed_per_message(self):
        # Arrange — sanitize_for_prompt collapses a message's own newlines so
        # one message can never forge extra "usuario:"/"peruca:" lines; the
        # separators between messages are added afterwards by construction.
        user = _sample_user()
        service, _, _, _ = _make_service(
            user=user,
            messages=_turns(
                ("linha1\nlinha2   com    espaços", "resposta\nem\nlinhas")
            ),
        )
        # Act
        hint = service._recent_history_hint(user.id)
        # Assert
        assert hint == (
            "usuario: linha1 linha2 com espaços\nperuca: resposta em linhas"
        )

    def test_hint__non_string_content__skipped_without_crash(self):
        # Arrange — a multimodal message (content as a list of blocks) must be
        # skipped; the remaining string messages still build the hint.
        user = _sample_user()
        multimodal = HumanMessage(
            content=[{"type": "image_url", "image_url": {"url": "data:image/png;base64,xx"}}]
        )
        messages = [
            multimodal,
            AIMessage(content="que foto bonita"),
            HumanMessage(content="adicione leite"),
            AIMessage(content="Adicionado: leite"),
        ]
        service, _, _, _ = _make_service(user=user, messages=messages)
        # Act — must not raise
        hint = service._recent_history_hint(user.id)
        # Assert
        assert hint == (
            "peruca: que foto bonita\n"
            "usuario: adicione leite\n"
            "peruca: Adicionado: leite"
        )


# ===========================================================================
# TestRecentHistoryHintCap
# ===========================================================================


class TestRecentHistoryHintCap:
    def test_hint__over_cap__truncates_oldest_first_and_keeps_last_message_intact(
        self,
    ):
        # Arrange — 4 long messages (1200 chars each) blow past the ~3000-char
        # cap. The OLDEST messages are sacrificed first; the most recent
        # message (where the ingredients live) survives intact — which also
        # pins that the per-message sanitization is NOT using the default
        # 500-char cap.
        user = _sample_user()
        m1, r1, m2, r2 = "a" * 1200, "b" * 1200, "c" * 1200, "d" * 1200
        service, _, _, _ = _make_service(
            user=user, messages=_turns((m1, r1), (m2, r2))
        )
        # Act
        hint = service._recent_history_hint(user.id)
        # Assert
        assert len(hint) <= _HINT_CAP_CHARS, (
            f"hint exceeded the cap: {len(hint)} chars"
        )
        assert r2 in hint, "the most recent message must survive intact"
        assert m2 in hint, "the most recent turn must survive intact"
        assert m1 not in hint, "the oldest message must be truncated first"

    def test_hint__under_cap__nothing_truncated(self):
        # Arrange — regression: short histories are never touched by the cap.
        user = _sample_user()
        service, _, _, _ = _make_service(
            user=user, messages=_turns(("oi", "olá"), ("tudo bem?", "tudo sim"))
        )
        # Act
        hint = service._recent_history_hint(user.id)
        # Assert
        assert hint == (
            "usuario: oi\nperuca: olá\nusuario: tudo bem?\nperuca: tudo sim"
        )


# ===========================================================================
# TestChatWiresRecentHistoryHint
# ===========================================================================


class TestChatWiresRecentHistoryHint:
    def test_chat__main_graph_receives_recent_history_in_context_hints(self):
        # Arrange — end-to-end wire: chat() must build the hint from the prior
        # history and hand it to MainGraph via context_hints.
        user = _sample_user()
        service, main_graph, _, _ = _make_service(
            user=user, messages=_turns(("oi", "olá"))
        )
        request = ChatRequest(
            message="adicione esses ingredientes na lista",
            external_user_id=user.external_id,
            chat_id="c1",
        )
        # Act
        service.chat(request)
        # Assert
        main_graph.invoke.assert_called_once()
        invoke_request = main_graph.invoke.call_args.kwargs.get(
            "invoke_request"
        ) or main_graph.invoke.call_args.args[0]
        assert invoke_request.context_hints["recent_history"] == (
            "usuario: oi\nperuca: olá"
        )

    def test_chat__no_history__main_graph_receives_vazio(self):
        # Arrange
        user = _sample_user()
        service, main_graph, _, _ = _make_service(user=user, messages=[])
        request = ChatRequest(
            message="oi", external_user_id=user.external_id, chat_id="c1"
        )
        # Act
        service.chat(request)
        # Assert
        invoke_request = main_graph.invoke.call_args.kwargs.get(
            "invoke_request"
        ) or main_graph.invoke.call_args.args[0]
        assert invoke_request.context_hints["recent_history"] == "(vazio)"
