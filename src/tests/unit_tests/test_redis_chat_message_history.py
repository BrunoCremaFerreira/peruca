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

        (Phase G / P2: the summary key is renewed on the same write — see
        TestRedisChatMessageHistorySummaryTTL — so this only pins the history
        key's renewal, not the number of expire() calls.)
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

        assert call(_EXPECTED_KEY, 3600) in mock_redis_client.expire.call_args_list

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
    def test_add_messages__ttl_zero__expire_not_called(self):
        """
        ttl_seconds == 0 must be treated as "no expiry".

        Redis `EXPIRE key 0` deletes the key immediately, so calling expire
        with 0 after every write would wipe the conversation history on each
        turn — the bot would always "forget" the previous message.
        """
        from langchain_core.messages import HumanMessage

        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value=None)
        mock_redis_client = MagicMock()
        mock_redis_client.expire = AsyncMock(return_value=True)

        history = _make_history(context_repo=repo, ttl_seconds=0)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)), \
             patch.object(history, "_get_client", return_value=mock_redis_client):
            history.add_messages([HumanMessage(content="zero ttl")])

        mock_redis_client.expire.assert_not_called()

    @_requires_impl
    def test_add_messages__ttl_negative__expire_not_called(self):
        """
        A negative ttl_seconds must also be treated as "no expiry" — Redis
        deletes the key for any non-positive expiry, which would erase history.
        """
        from langchain_core.messages import HumanMessage

        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value=None)
        mock_redis_client = MagicMock()
        mock_redis_client.expire = AsyncMock(return_value=True)

        history = _make_history(context_repo=repo, ttl_seconds=-1)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)), \
             patch.object(history, "_get_client", return_value=mock_redis_client):
            history.add_messages([HumanMessage(content="negative ttl")])

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

        expired_keys = [
            call_args[0][0] for call_args in mock_redis_client.expire.call_args_list
        ]
        assert _EXPECTED_KEY in expired_keys, (
            f"expire() must be called with key {_EXPECTED_KEY!r}, "
            f"got {expired_keys!r}."
        )


# ===========================================================================
# TestRedisChatMessageHistoryLocking — Phase B / F2 (TDD RED phase)
# ===========================================================================
#
# Chat context compaction (plan §3.5) turns `add_messages` into one half of a
# read-verify-write race:
#
#   thread A (request):     add_messages  = GET array -> append -> SET array
#   thread B (background):  apply_compaction = GET array -> verify -> SET tail
#
# Both are read-modify-write cycles over the SAME `chat_history:{user_id}` key.
# Interleaved, thread B's SET can clobber the turn thread A just appended (real,
# permanent data loss). The fix is a `threading.Lock` per user_id, taken from a
# registry SHARED by both components — so this file now also pins that
# `RedisChatMessageHistory` takes it.
#
# Two invariants worth stating, because getting them wrong is subtle:
#
#  - the lock must be THE SAME OBJECT `RedisConversationContextStore` takes for
#    the same user_id (two different locks serialise nothing);
#  - the `messages` PROPERTY must NOT take it. `add_messages` reads through
#    `self.messages` while holding the lock, and `threading.Lock` is not
#    reentrant — locking the property would deadlock the writer against itself.
#
# Written BEFORE `infra/user_lock_registry.py` exists: the lazy import below
# makes these tests (and only these) fail RED with ImportError, leaving the
# already-green tests above collectible.

import threading


def _lock_registry_module():
    """Import the (not yet written) lock registry; RED = ImportError here."""
    import infra.user_lock_registry as module

    return module


def _conversation_context_store_class():
    """Import the (not yet written) Redis conversation context store."""
    from infra.data.external.redis.redis_conversation_context_store import (
        RedisConversationContextStore,
    )

    return RedisConversationContextStore


def _make_dict_backed_repo(data: dict | None = None) -> MagicMock:
    """A ContextRepository MagicMock backed by a real dict (round-trips work)."""
    data = {} if data is None else data

    def _get(key):
        return data.get(key)

    def _set(key, value):
        data[key] = value
        return True

    def _delete(key):
        return data.pop(key, None) is not None

    repo = MagicMock()
    repo.data = data
    repo.get_key = AsyncMock(side_effect=_get)
    repo.set_key = AsyncMock(side_effect=_set)
    repo.delete_key = AsyncMock(side_effect=_delete)

    pipe = MagicMock()
    pipe.set = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)

    async def _execute(*_args, **_kwargs):
        for command in pipe.set.call_args_list:
            data[command.args[0]] = command.args[1]
        return [True]

    pipe.execute = AsyncMock(side_effect=_execute)
    pipe.__aenter__.return_value = pipe
    pipe.__aexit__.return_value = False

    client = MagicMock()
    client.pipeline = MagicMock(return_value=pipe)
    repo._get_client = MagicMock(return_value=client)
    repo.redis_client = client
    repo.redis_pipeline = pipe
    return repo


def _sample_history_dicts() -> list[dict]:
    return [
        {"type": "human", "content": "oi"},
        {"type": "ai", "content": "Olá!"},
        {"type": "human", "content": "tudo bem?"},
        {"type": "ai", "content": "Tudo ótimo!"},
    ]


class TestRedisChatMessageHistoryLocking:
    """add_messages / clear must take the shared per-user lock."""

    def test_add_messages__acquires_the_user_lock_once(self):
        from langchain_core.messages import HumanMessage

        registry = _lock_registry_module().UserLockRegistry()
        lock = registry.get(_SESSION_ID)
        observed = []

        repo = _make_dict_backed_repo()
        repo.get_key = AsyncMock(side_effect=lambda key: observed.append(lock.locked()))
        repo.set_key = AsyncMock(side_effect=lambda key, value: observed.append(lock.locked()))

        history = RedisChatMessageHistory(
            session_id=_SESSION_ID,
            context_repo=repo,
            ttl_seconds=None,
            lock_registry=registry,
        )

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)):
            history.add_messages([HumanMessage(content="novo turno")])

        assert observed and all(observed), (
            "The whole read-modify-write of add_messages must run while the "
            "per-user lock from the registry is held, otherwise a concurrent "
            "compaction can clobber the turn just appended."
        )
        assert lock.locked() is False, "The lock must be released afterwards."

    def test_messages_property__does_not_acquire_the_user_lock(self):
        # Deadlock guard: add_messages reads through `self.messages` WHILE
        # holding the (non-reentrant) lock. If the property locked too, every
        # single write would deadlock.
        registry = _lock_registry_module().UserLockRegistry()
        lock = registry.get(_SESSION_ID)
        observed = []

        repo = _make_dict_backed_repo()
        repo.get_key = AsyncMock(side_effect=lambda key: observed.append(lock.locked()))

        history = RedisChatMessageHistory(
            session_id=_SESSION_ID,
            context_repo=repo,
            ttl_seconds=None,
            lock_registry=registry,
        )

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)):
            _ = history.messages

        assert observed == [False], (
            "The `messages` property must NOT take the per-user lock — "
            "threading.Lock is not reentrant and add_messages reads through it."
        )

    def test_add_messages__does_not_deadlock(self):
        # The regression this whole design is exposed to: a naive implementation
        # that locks both `add_messages` and the `messages` property hangs here.
        from langchain_core.messages import HumanMessage

        registry = _lock_registry_module().UserLockRegistry()
        repo = _make_dict_backed_repo()
        history = RedisChatMessageHistory(
            session_id=_SESSION_ID,
            context_repo=repo,
            ttl_seconds=None,
            lock_registry=registry,
        )

        done = threading.Event()
        error: list = []

        def _write():
            # A worker thread has no event loop of its own; give it one so the
            # patched async_runner can drive the repository coroutines.
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                with patch(
                    _ASYNC_RUNNER_PATCH,
                    side_effect=lambda coro: loop.run_until_complete(coro),
                ):
                    history.add_messages([HumanMessage(content="sem deadlock")])
            except BaseException as exc:  # pragma: no cover - diagnostic only
                error.append(exc)
            finally:
                loop.close()
                done.set()

        worker = threading.Thread(target=_write, daemon=True)
        worker.start()
        finished = done.wait(timeout=5)

        assert finished, "add_messages deadlocked (it locked the messages property)."
        assert not error, f"add_messages raised: {error}"

    def test_clear__acquires_the_user_lock(self):
        registry = _lock_registry_module().UserLockRegistry()
        lock = registry.get(_SESSION_ID)
        observed = []

        repo = _make_dict_backed_repo({_EXPECTED_KEY: "[]"})
        repo.delete_key = AsyncMock(side_effect=lambda key: observed.append(lock.locked()))

        history = RedisChatMessageHistory(
            session_id=_SESSION_ID,
            context_repo=repo,
            ttl_seconds=None,
            lock_registry=registry,
        )

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)):
            history.clear()

        assert observed == [True], (
            "clear() must delete the key under the per-user lock, so it cannot "
            "land in the middle of a compaction's read-verify-write."
        )
        assert lock.locked() is False


class TestRedisChatMessageHistorySharedLockRegistry:
    """
    The history writer and the compaction CAS must take THE SAME lock object
    for the same user_id (plan §3.5: "num registro compartilhado").
    """

    def test_add_messages_and_apply_compaction__take_the_same_lock_object(self):
        from langchain_core.messages import HumanMessage

        from domain.services.conversation_digest import conversation_digest

        registry = _lock_registry_module().UserLockRegistry()
        expected_lock = registry.get(_SESSION_ID)

        handed_out = []
        original_get = registry.get

        def _spy_get(user_id):
            lock = original_get(user_id)
            handed_out.append((user_id, lock))
            return lock

        registry.get = _spy_get

        history_dicts = _sample_history_dicts()
        repo = _make_dict_backed_repo({_EXPECTED_KEY: json.dumps(history_dicts)})

        history = RedisChatMessageHistory(
            session_id=_SESSION_ID,
            context_repo=repo,
            ttl_seconds=None,
            lock_registry=registry,
        )
        store = _conversation_context_store_class()(
            context_repo=repo,
            ttl_seconds=None,
            lock_registry=registry,
        )

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)):
            history.add_messages([HumanMessage(content="turno concorrente")])
            store.apply_compaction(
                _SESSION_ID,
                2,
                conversation_digest(history_dicts[:2]),
                "### Resumo\n- assunto",
            )

        locks = [lock for _user_id, lock in handed_out]
        assert len(locks) >= 2, (
            "Both RedisChatMessageHistory and RedisConversationContextStore must "
            f"ask the shared registry for the user's lock. Got: {handed_out}"
        )
        assert all(lock is expected_lock for lock in locks), (
            "add_messages and apply_compaction must take the SAME threading.Lock "
            "OBJECT for the same user_id — two distinct locks serialise nothing."
        )
        assert {user_id for user_id, _lock in handed_out} == {_SESSION_ID}

    def test_different_user_ids__take_different_locks(self):
        registry = _lock_registry_module().UserLockRegistry()

        assert registry.get(_SESSION_ID) is not registry.get("another-user"), (
            "Locks are per user_id: one user's compaction must never block "
            "another user's turn from being persisted."
        )

    def test_no_registry_injected__falls_back_to_the_process_wide_registry(self):
        # Without an explicit registry, the history and the store must STILL end
        # up on the same lock — otherwise the default (IoC-free) wiring races.
        from langchain_core.messages import HumanMessage

        module = _lock_registry_module()
        default_lock = module.get_user_lock_registry().get(_SESSION_ID)
        observed = []

        repo = _make_dict_backed_repo()
        repo.get_key = AsyncMock(side_effect=lambda key: observed.append(default_lock.locked()))
        repo.set_key = AsyncMock(side_effect=lambda key, value: observed.append(default_lock.locked()))

        history = RedisChatMessageHistory(session_id=_SESSION_ID, context_repo=repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)):
            history.add_messages([HumanMessage(content="padrão")])

        assert observed and all(observed), (
            "With no lock_registry injected, RedisChatMessageHistory must use the "
            "process-wide default registry (infra.user_lock_registry)."
        )


# ===========================================================================
# TestRedisChatMessageHistorySummaryTTL — Phase G / P2 (TDD RED phase)
# ===========================================================================
#
# Security review, P2 (permanent context loss): with CHAT_HISTORY_TTL_SECONDS set,
# `add_messages` renews the TTL of `chat_history:{id}` on EVERY turn, but the TTL of
# `chat_summary:{id}` is only (re)set inside `apply_compaction` — roughly once every
# 7 turns, and never at all for a user who stopped triggering compactions.
#
# So the SUMMARY expires BEFORE the history. And because the compaction already
# DROPPED the raw prefix the summary stands for, that expiry is unrecoverable loss of
# everything older than the window — precisely the failure mode plan §6.6 forbids
# ("nunca perdeu histórico"). An active conversation must keep BOTH keys alive.
#
# Contract:
#     RedisChatMessageHistory.summary_key == f"chat_summary:{session_id}"  (same key
#         RedisConversationContextStore._summary_key builds)
#     add_messages(), when ttl > 0, expires BOTH keys with the same TTL.
#     A non-positive / None TTL still expires NOTHING (Redis EXPIRE with 0 or a
#         negative value DELETES the key — it would wipe history AND summary).
#
# EXPIRE on a key that does not exist is a harmless no-op (returns 0), so a user who
# was never compacted costs one extra pipeline-less command per turn and nothing more.

_EXPECTED_SUMMARY_KEY = f"chat_summary:{_SESSION_ID}"


def _expire_calls(client) -> list[tuple]:
    return [call_args[0] for call_args in client.expire.call_args_list]


def _make_client_with_expire() -> MagicMock:
    client = MagicMock()
    client.expire = AsyncMock(return_value=True)
    return client


class TestRedisChatMessageHistorySummaryTTL:

    def test_summary_key__matches_the_conversation_context_store_key(self):
        history = _make_history()
        assert history.summary_key == _EXPECTED_SUMMARY_KEY, (
            "The history must renew the very key the compaction store writes "
            "(`chat_summary:{user_id}`)."
        )

    def test_add_messages__ttl_set__renews_the_summary_key_too(self):
        from langchain_core.messages import HumanMessage

        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value=None)
        client = _make_client_with_expire()
        history = _make_history(context_repo=repo, ttl_seconds=3600)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)), \
             patch.object(history, "_get_client", return_value=client):
            history.add_messages([HumanMessage(content="mais um turno")])

        calls = _expire_calls(client)
        assert (_EXPECTED_KEY, 3600) in calls
        assert (_EXPECTED_SUMMARY_KEY, 3600) in calls, (
            "The summary must be renewed on every turn: it expiring before the "
            "history means the compacted (and already deleted) prefix is gone "
            "for good."
        )

    def test_add_messages__ttl_set__both_keys_get_the_same_ttl(self):
        from langchain_core.messages import HumanMessage

        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value=None)
        client = _make_client_with_expire()
        history = _make_history(context_repo=repo, ttl_seconds=120)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)), \
             patch.object(history, "_get_client", return_value=client):
            history.add_messages([HumanMessage(content="x")])

        ttls = {ttl for _key, ttl in _expire_calls(client)}
        assert ttls == {120}, (
            "History and summary share one TTL (plan §3.3); a summary that "
            "outlives or under-lives the history is a bug either way."
        )

    def test_add_messages__ttl_set__expires_exactly_the_two_keys(self):
        from langchain_core.messages import HumanMessage

        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value=None)
        client = _make_client_with_expire()
        history = _make_history(context_repo=repo, ttl_seconds=60)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)), \
             patch.object(history, "_get_client", return_value=client):
            history.add_messages([HumanMessage(content="x")])

        assert {key for key, _ttl in _expire_calls(client)} == {
            _EXPECTED_KEY,
            _EXPECTED_SUMMARY_KEY,
        }

    def test_add_messages__no_ttl__does_not_touch_the_summary_key(self):
        from langchain_core.messages import HumanMessage

        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value=None)
        client = _make_client_with_expire()
        history = _make_history(context_repo=repo, ttl_seconds=None)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)), \
             patch.object(history, "_get_client", return_value=client):
            history.add_messages([HumanMessage(content="x")])

        client.expire.assert_not_called()

    @pytest.mark.parametrize("ttl", [0, -1])
    def test_add_messages__non_positive_ttl__expires_neither_key(self, ttl):
        # `EXPIRE key 0` (or negative) DELETES the key: the existing rule must
        # cover the summary key as well, or a misconfigured TTL would wipe the
        # compacted context on the very next turn.
        from langchain_core.messages import HumanMessage

        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value=None)
        client = _make_client_with_expire()
        history = _make_history(context_repo=repo, ttl_seconds=ttl)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)), \
             patch.object(history, "_get_client", return_value=client):
            history.add_messages([HumanMessage(content="x")])

        client.expire.assert_not_called()

    def test_add_messages__ttl_set__still_persists_the_messages(self):
        # The TTL renewal must not get in the way of the write itself.
        from langchain_core.messages import HumanMessage

        repo = _make_context_repo()
        repo.get_key = AsyncMock(return_value=None)
        client = _make_client_with_expire()
        history = _make_history(context_repo=repo, ttl_seconds=60)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=lambda coro: _sync(coro)), \
             patch.object(history, "_get_client", return_value=client):
            history.add_messages([HumanMessage(content="persistido")])

        _key, value = repo.set_key.call_args[0]
        assert json.loads(value)[0]["content"] == "persistido"
