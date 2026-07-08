"""
LlmAppService.reset_context() Unit Tests (TDD - RED phase)

New feature (target of these tests):
    A REST-only endpoint resets a user's conversation history (chat_history) —
    the same history OnlyTalkGraph reads and LlmAppService._persist_turn writes,
    obtained via `get_session_history(user_id)`.

Approved design (plan §2.1 / §2.4):
    def reset_context(self, user_id: str) -> None:
        if self.get_session_history is None:
            return
        self.get_session_history(user_id).clear()

    - Guard for a None factory is a no-op (mirrors _persist_turn).
    - Unlike _persist_turn (which swallows exceptions on a best-effort
      background write), reset_context is a synchronous, explicit API action:
      it PROPAGATES any exception raised by .clear() so the caller sees a 500
      instead of a lying 200.

Expected to FAIL until LlmAppService gains reset_context:
    AttributeError: 'LlmAppService' object has no attribute 'reset_context'.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from application.appservices.llm_app_service import LlmAppService


# ===========================================================================
# Helpers
# ===========================================================================

_NO_FACTORY = object()  # sentinel: build the service with get_session_history=None


def _make_service(get_session_history=_NO_FACTORY):
    """
    Build a LlmAppService with all dependencies mocked.

    By default a MagicMock factory returning a MagicMock history is wired in.
    Pass `get_session_history=None` to build a service without a history
    factory (the in-memory-disabled path).

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
    )
    return service, get_session_history, history


# ===========================================================================
# TestLlmAppServiceResetContext
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
        # Arrange — no history factory configured.
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
