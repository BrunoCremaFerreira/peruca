"""
LlmAppService.reset_context() Unit Tests.

Original feature:
    A REST-only endpoint resets a user's conversation history (chat_history) —
    the same history OnlyTalkGraph reads and LlmAppService._persist_turn writes,
    obtained via `get_session_history(user_id)`.

Fase E / F6 (chat context compaction, plan §6.3) — reset_context becomes
STORE-FIRST:

    def reset_context(self, user_id: str) -> None:
        if self.conversation_context_store is not None:
            self.conversation_context_store.clear(user_id)
            return
        if self.get_session_history is None:
            return
        self.get_session_history(user_id).clear()

    - With a ConversationContextStore injected, `store.clear(user_id)` wipes the
      history AND the summary in one place. A reset that only cleared the history
      would leave a summary of a conversation that no longer exists — the user
      asks for a clean slate and Peruca still "remembers".
    - No double-clear: the store already owns the history, so
      get_session_history must NOT be called on the store path (it would be a
      second, redundant write — and on the in-memory backend a second clear of
      the very same object).
    - Without a store, the current fallback is kept (retro-compat, §6.4).
    - Neither store nor factory → silent no-op (mirrors _persist_turn).
    - Exceptions keep PROPAGATING (§6.3): reset is an explicit, synchronous API
      action — the caller must see a real 500, never a lying 200.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from application.appservices.llm_app_service import LlmAppService


# ===========================================================================
# Helpers
# ===========================================================================

_NO_FACTORY = object()  # sentinel: build the service with get_session_history=None


def _make_service(get_session_history=_NO_FACTORY, conversation_context_store=None):
    """
    Build a LlmAppService with all dependencies mocked.

    By default a MagicMock factory returning a MagicMock history is wired in and
    NO conversation context store (the legacy/fallback path).
    Pass `get_session_history=None` to build a service without a history factory
    (the in-memory-disabled path).

    Returns (service, get_session_history, history) — `history` is None when no
    factory was wired in.
    """
    main_graph = MagicMock()
    context_repository = MagicMock()
    user_repository = MagicMock()
    user_memory_service = MagicMock()

    history = None
    if get_session_history is _NO_FACTORY:
        history = MagicMock()
        get_session_history = MagicMock(return_value=history)

    service = LlmAppService(
        main_graph=main_graph,
        context_repository=context_repository,
        user_repository=user_repository,
        user_memory_service=user_memory_service,
        get_session_history=get_session_history,
        conversation_context_store=conversation_context_store,
    )
    return service, get_session_history, history


# ===========================================================================
# TestLlmAppServiceResetContext — fallback path (no store injected)
# ===========================================================================


class TestLlmAppServiceResetContext:
    def test_reset_context__valid_user_id__calls_get_session_history_with_user_id(
        self,
    ):
        # Arrange
        user_id = str(uuid.uuid4())
        service, get_session_history, _ = _make_service()
        # Act
        service.reset_context(user_id=user_id)
        # Assert — same key the history is written/read under.
        get_session_history.assert_called_once_with(user_id)

    def test_reset_context__valid_user_id__calls_clear_once(self):
        # Arrange
        user_id = str(uuid.uuid4())
        service, _, history = _make_service()
        # Act
        service.reset_context(user_id=user_id)
        # Assert — clear() takes no args; the per-user scope lives in the
        # history lookup, not in clear().
        history.clear.assert_called_once_with()

    def test_reset_context__get_session_history_is_none__is_noop_and_does_not_raise(
        self,
    ):
        # Arrange — no history factory and no store configured.
        service, _, _ = _make_service(get_session_history=None)
        # Act / Assert — must be a silent no-op.
        assert service.reset_context(user_id=str(uuid.uuid4())) is None

    def test_reset_context__returns_none(self):
        # Arrange
        service, _, _ = _make_service()
        # Act
        result = service.reset_context(user_id=str(uuid.uuid4()))
        # Assert — contract is `-> None`.
        assert result is None

    def test_reset_context__empty_string_user_id__still_calls_get_session_history(
        self,
    ):
        # Arrange — documents the conscious absence of format/existence
        # validation (plan §2.3).
        service, get_session_history, _ = _make_service()
        # Act
        service.reset_context(user_id="")
        # Assert
        get_session_history.assert_called_once_with("")

    def test_reset_context__history_clear_raises__propagates_exception(self):
        # Arrange — locks the §2.4 decision: propagate, do NOT swallow.
        service, _, history = _make_service()
        history.clear.side_effect = RuntimeError("redis down")
        # Act / Assert
        with pytest.raises(RuntimeError):
            service.reset_context(user_id=str(uuid.uuid4()))


# ===========================================================================
# TestLlmAppServiceResetContextStoreFirst — compaction store injected (§6.3)
# ===========================================================================


class TestLlmAppServiceResetContextStoreFirst:
    def test_reset_context__with_store__calls_store_clear_with_user_id(self):
        # Arrange
        user_id = str(uuid.uuid4())
        store = MagicMock()
        service, _, _ = _make_service(conversation_context_store=store)
        # Act
        service.reset_context(user_id=user_id)
        # Assert — one call clears history AND summary.
        store.clear.assert_called_once_with(user_id)

    def test_reset_context__with_store__does_not_double_clear_via_session_history(
        self,
    ):
        # Arrange
        store = MagicMock()
        service, get_session_history, history = _make_service(
            conversation_context_store=store
        )
        # Act
        service.reset_context(user_id=str(uuid.uuid4()))
        # Assert — the store owns the history; clearing it twice is redundant
        # (and, in-memory, clears the very same object twice).
        get_session_history.assert_not_called()
        history.clear.assert_not_called()

    def test_reset_context__with_store_and_no_history_factory__still_clears(self):
        # Arrange — Redis store wired, no session-history factory.
        store = MagicMock()
        user_id = str(uuid.uuid4())
        service, _, _ = _make_service(
            get_session_history=None, conversation_context_store=store
        )
        # Act
        service.reset_context(user_id=user_id)
        # Assert
        store.clear.assert_called_once_with(user_id)

    def test_reset_context__with_store__returns_none(self):
        # Arrange
        store = MagicMock()
        service, _, _ = _make_service(conversation_context_store=store)
        # Act
        result = service.reset_context(user_id=str(uuid.uuid4()))
        # Assert
        assert result is None

    def test_reset_context__store_clear_raises__propagates_exception(self):
        # Arrange — same semantics as the fallback path: a failed reset is a 500.
        store = MagicMock()
        store.clear.side_effect = RuntimeError("redis down")
        service, _, _ = _make_service(conversation_context_store=store)
        # Act / Assert
        with pytest.raises(RuntimeError):
            service.reset_context(user_id=str(uuid.uuid4()))

    def test_reset_context__store_clear_raises__does_not_fall_back_to_history(self):
        # Arrange — a failing store must NOT silently degrade into a partial
        # reset (history wiped, summary kept).
        store = MagicMock()
        store.clear.side_effect = RuntimeError("redis down")
        service, get_session_history, _ = _make_service(
            conversation_context_store=store
        )
        # Act / Assert
        with pytest.raises(RuntimeError):
            service.reset_context(user_id=str(uuid.uuid4()))
        get_session_history.assert_not_called()
