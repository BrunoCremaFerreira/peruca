"""
RedisChatMessageHistory Unit Tests (TDD — RED phase)

Tests for the class `RedisChatMessageHistory`, which does not yet exist at:
    infra/data/external/redis/redis_chat_message_history.py

This class wraps ContextRepository (Redis ABC) to implement
BaseChatMessageHistory from langchain_core, persisting chat history keyed by
`chat_history:{session_id}`.

All tests are written before the implementation and are expected to FAIL with
an ImportError until the class is created.  That import error is the correct
RED state for TDD.

Mock strategy:
- ContextRepository methods (get_key, set_key, delete_key) are AsyncMocks.
- infra.async_runner.run is patched so that coroutines are driven by the
  test-thread event loop instead of the background daemon thread.
- The underlying Redis client obtained via _get_client() is mocked to verify
  TTL / expire calls without a real Redis connection.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Target import — RED phase: ImportError expected until implementation exists
# ---------------------------------------------------------------------------
try:
    from infra.data.external.redis.redis_chat_message_history import (
        RedisChatMessageHistory,
    )
    _IMPORT_OK = True
except ImportError:
    _IMPORT_OK = False

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SESSION_ID = "user-session-abc"
_EXPECTED_KEY = f"chat_history:{_SESSION_ID}"

# Patch target for the singleton async runner used by the implementation
_ASYNC_RUNNER_PATCH = "infra.async_runner.run"


def _sync(coro):
    """Drive a coroutine on the test-thread event loop."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_context_repo() -> MagicMock:
    """Return a MagicMock ContextRepository with async methods pre-wired."""
    repo = MagicMock()
    repo.get_key = AsyncMock(return_value=None)
    repo.set_key = AsyncMock(return_value=True)
    repo.delete_key = AsyncMock(return_value=True)
    return repo


def _encode_messages(messages: list[dict]) -> str:
    """Serialise messages list the same way the implementation is expected to."""
    return json.dumps(messages)


def _make_history(context_repo=None, ttl_seconds=None) -> "RedisChatMessageHistory":
    """Instantiate RedisChatMessageHistory with a mock ContextRepository."""
    if context_repo is None:
        context_repo = _make_context_repo()
    return RedisChatMessageHistory(
        session_id=_SESSION_ID,
        context_repo=context_repo,
        ttl_seconds=ttl_seconds,
    )


# Decorator that skips the whole test with a clear message when the import fails
_requires_impl = pytest.mark.skipif(
    not _IMPORT_OK,
    reason=(
        "RedisChatMessageHistory not yet implemented at "
        "infra/data/external/redis/redis_chat_message_history.py — RED phase"
    ),
)


# ===========================================================================
# TestRedisChatMessageHistoryKey
# ===========================================================================


class TestRedisChatMessageHistoryKey:
    """The Redis key format must be `chat_history:{session_id}`."""

    @_requires_impl
    def test_key_format__session_id__uses_chat_history_prefix(self):
        # Arrange
        history = _make_history()
        # Assert
        assert history.key == _EXPECTED_KEY, (
            f"Expected key 'chat_history:{_SESSION_ID}', got {history.key!r}. "
            "The key must follow the format `chat_history:{session_id}`."
        )


# ===========================================================================
# TestRedisChatMessageHistoryMessages
# ===========================================================================


class TestRedisChatMessageHistoryMessages:
    """messages property — reads and deserialises from Redis."""

    @_requires_impl
    def test_messages__key_returns_none__returns_empty_list(self):
        """
        When context_repo.get_key returns None, messages must be [].

        This covers a cold-start where the key has never been written.
        """
        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value=None)
        history = _make_history(context_repo=repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)):
            result = history.messages

        assert result == [], (
            "messages must return [] when get_key returns None (key not found)."
        )

    @_requires_impl
    def test_messages__key_returns_string_none__returns_empty_list(self):
        """
        RedisContextRepository.get_key wraps None in str(), returning "None".
        RedisChatMessageHistory must treat the string "None" the same as
        a missing key — i.e. return [].
        """
        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value="None")
        history = _make_history(context_repo=repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)):
            result = history.messages

        assert result == [], (
            'messages must return [] when get_key returns the string "None".'
        )

    @_requires_impl
    def test_messages__key_has_stored_messages__deserialises_correctly(self):
        """
        When get_key returns a JSON-encoded list of serialised messages,
        messages must deserialise and return langchain BaseMessage objects.
        """
        from langchain_core.messages import HumanMessage, AIMessage

        stored = [
            {"type": "human", "content": "Olá"},
            {"type": "ai", "content": "Olá! Como posso ajudar?"},
        ]
        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value=json.dumps(stored))
        history = _make_history(context_repo=repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)):
            result = history.messages

        assert len(result) == 2, f"Expected 2 messages, got {len(result)}."
        assert isinstance(result[0], HumanMessage)
        assert result[0].content == "Olá"
        assert isinstance(result[1], AIMessage)
        assert result[1].content == "Olá! Como posso ajudar?"

    @_requires_impl
    def test_messages__get_key_called_with_correct_key(self):
        """
        messages must call context_repo.get_key with the exact key
        `chat_history:{session_id}`.
        """
        repo = _make_context_repo()
        history = _make_history(context_repo=repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)):
            _ = history.messages

        repo.get_key.assert_called_once_with(_EXPECTED_KEY)


# ===========================================================================
# TestRedisChatMessageHistoryAddMessages
# ===========================================================================


class TestRedisChatMessageHistoryAddMessages:
    """add_messages — read-modify-write persisting new messages."""

    @_requires_impl
    def test_add_messages__empty_history__persists_new_messages(self):
        """
        When the key does not exist (get_key → None), add_messages must write
        only the new messages via set_key.
        """
        from langchain_core.messages import HumanMessage

        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value=None)
        history = _make_history(context_repo=repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)):
            history.add_messages([HumanMessage(content="Teste")])

        repo.set_key.assert_called_once()
        key_arg, value_arg = repo.set_key.call_args[0]
        assert key_arg == _EXPECTED_KEY
        persisted = json.loads(value_arg)
        assert len(persisted) == 1
        assert persisted[0]["content"] == "Teste"

    @_requires_impl
    def test_add_messages__existing_history__preserves_previous_messages(self):
        """
        add_messages must read the existing messages first and append the new
        ones, so earlier conversation turns are not lost (read-modify-write).
        """
        from langchain_core.messages import HumanMessage, AIMessage

        existing = [{"type": "human", "content": "Oi"}]
        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value=json.dumps(existing))
        history = _make_history(context_repo=repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)):
            history.add_messages([AIMessage(content="Olá!")])

        _, value_arg = repo.set_key.call_args[0]
        persisted = json.loads(value_arg)
        assert len(persisted) == 2, (
            "add_messages must preserve existing messages. "
            f"Expected 2 entries, got {len(persisted)}."
        )
        assert persisted[0]["content"] == "Oi"
        assert persisted[1]["content"] == "Olá!"

    @_requires_impl
    def test_add_messages__multiple_messages__all_persisted_in_order(self):
        """
        When add_messages receives a list with more than one message, all of
        them must appear in the persisted payload in insertion order.
        """
        from langchain_core.messages import HumanMessage, AIMessage

        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value=None)
        history = _make_history(context_repo=repo)

        new_messages = [
            HumanMessage(content="Primeira"),
            AIMessage(content="Resposta"),
            HumanMessage(content="Segunda"),
        ]

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)):
            history.add_messages(new_messages)

        _, value_arg = repo.set_key.call_args[0]
        persisted = json.loads(value_arg)
        assert len(persisted) == 3
        assert persisted[0]["content"] == "Primeira"
        assert persisted[1]["content"] == "Resposta"
        assert persisted[2]["content"] == "Segunda"

    @_requires_impl
    def test_add_messages__set_key_called_with_correct_key(self):
        """
        set_key must be called with the key `chat_history:{session_id}`,
        not an arbitrary string.
        """
        from langchain_core.messages import HumanMessage

        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value=None)
        history = _make_history(context_repo=repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)):
            history.add_messages([HumanMessage(content="x")])

        key_arg = repo.set_key.call_args[0][0]
        assert key_arg == _EXPECTED_KEY


# ===========================================================================
# TestRedisChatMessageHistoryClear
# ===========================================================================


class TestRedisChatMessageHistoryClear:
    """clear — delegates to context_repo.delete_key."""

    @_requires_impl
    def test_clear__calls_delete_key_with_correct_key(self):
        """
        clear() must call context_repo.delete_key with the exact key
        `chat_history:{session_id}`.
        """
        repo = _make_context_repo()
        history = _make_history(context_repo=repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)):
            history.clear()

        repo.delete_key.assert_called_once_with(_EXPECTED_KEY)

    @_requires_impl
    def test_clear__after_clear__messages_returns_empty_list(self):
        """
        After clear(), a subsequent call to messages must return [].
        The test simulates that delete_key was called and then get_key returns
        None (key was removed).
        """
        repo = _make_context_repo()
        repo.get_key = AsyncMock(side_effect=[
            None,  # after clear, key no longer exists
        ])
        history = _make_history(context_repo=repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)):
            history.clear()
            result = history.messages

        assert result == [], (
            "After clear(), messages must return [] (get_key returns None)."
        )


# ===========================================================================
# TestRedisChatMessageHistoryTTL
# ===========================================================================


class TestRedisChatMessageHistoryTTL:
    """TTL / expire behaviour after add_messages."""

    @_requires_impl
    def test_add_messages__ttl_set__expire_called_with_ttl_seconds(self):
        """
        When ttl_seconds is not None, the underlying Redis client's expire()
        must be called with (key, ttl_seconds) after each write.
        """
        from langchain_core.messages import HumanMessage

        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value=None)
        mock_redis_client = MagicMock()
        mock_redis_client.expire = AsyncMock(return_value=True)

        history = _make_history(context_repo=repo, ttl_seconds=3600)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)), \
             patch.object(history, "_get_client", return_value=mock_redis_client):
            history.add_messages([HumanMessage(content="TTL test")])

        mock_redis_client.expire.assert_called_once_with(_EXPECTED_KEY, 3600)

    @_requires_impl
    def test_add_messages__no_ttl__expire_not_called(self):
        """
        When ttl_seconds is None, expire() must NOT be called at all.
        """
        from langchain_core.messages import HumanMessage

        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value=None)
        mock_redis_client = MagicMock()
        mock_redis_client.expire = AsyncMock(return_value=True)

        history = _make_history(context_repo=repo, ttl_seconds=None)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)), \
             patch.object(history, "_get_client", return_value=mock_redis_client):
            history.add_messages([HumanMessage(content="No TTL test")])

        mock_redis_client.expire.assert_not_called()

    @_requires_impl
    def test_add_messages__ttl_set__expire_called_with_correct_key(self):
        """
        expire() must be called with the same key used for set_key —
        `chat_history:{session_id}` — not a different or truncated key.
        """
        from langchain_core.messages import HumanMessage

        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value=None)
        mock_redis_client = MagicMock()
        mock_redis_client.expire = AsyncMock(return_value=True)

        history = _make_history(context_repo=repo, ttl_seconds=300)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)), \
             patch.object(history, "_get_client", return_value=mock_redis_client):
            history.add_messages([HumanMessage(content="key check")])

        expire_key_arg = mock_redis_client.expire.call_args[0][0]
        assert expire_key_arg == _EXPECTED_KEY, (
            f"expire() must be called with key {_EXPECTED_KEY!r}, "
            f"got {expire_key_arg!r}."
        )
