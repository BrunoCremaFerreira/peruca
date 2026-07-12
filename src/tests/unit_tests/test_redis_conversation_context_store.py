"""
RedisConversationContextStore unit tests — Phase B / F2 (TDD RED phase).

Drives the Redis implementation of the `ConversationContextStore` ABC (plan §3.2),
built on top of the existing `ContextRepository` and sharing both the history key
and the per-user lock registry with `RedisChatMessageHistory`:

    infra/user_lock_registry.py
        class UserLockRegistry:
            def get(self, user_id: str) -> threading.Lock
        def get_user_lock_registry() -> UserLockRegistry      # process-wide default

    infra/data/external/redis/redis_conversation_context_store.py
        class RedisConversationContextStore(ConversationContextStore):
            def __init__(self, context_repo: ContextRepository,
                         ttl_seconds: Optional[int] = None,
                         lock_registry: Optional[UserLockRegistry] = None)

Keys (plan §3.3):
    chat_history:{user_id}  -> JSON array [{"type": "human"|"ai", "content": str}]
                               (the SAME key RedisChatMessageHistory writes)
    chat_summary:{user_id}  -> JSON {"summary": str, "covers": int, "updated_at": iso}
                               (same TTL as chat_history_ttl_seconds)

The CAS (plan §3.4 step 5 / §3.5). `apply_compaction` is called SECONDS after the
prefix was snapshotted (the LLM ran in between, with no lock held), so it must:
  - take the per-user lock — the SAME object `RedisChatMessageHistory.add_messages`
    takes, so a turn cannot be appended in the middle of the swap;
  - RE-READ the array from Redis inside the lock (never trust the snapshot);
  - verify `expected_count` + `expected_digest` against the CURRENT prefix;
  - on match: write the summary AND rewrite the history with the CURRENT tail
    (including turns appended while the LLM was running) in ONE pipeline/MULTI —
    the intermediate state "truncated but no summary yet" is real data loss;
  - on mismatch: return False and touch NOTHING. Never write the summary on abort.

Fail-safe reads (plan §6.6 — the failure mode is always "not compacted yet", never
"lost the history"): corrupt JSON yields None / [] rather than raising.

Mock strategy (mirrors tests/unit_tests/test_redis_chat_message_history.py):
- ContextRepository get_key/set_key/delete_key are AsyncMocks over a dict.
- `infra.async_runner.run` is patched so coroutines run on the test-thread loop.
- The Redis client and its pipeline are MagicMocks; the pipeline's `execute`
  applies the queued SETs to the backing dict, so round-trips are observable.

Written BEFORE the implementation: expected to FAIL RED with ImportError.
"""

import asyncio
import json
import threading
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from domain.services.conversation_digest import conversation_digest
from domain.interfaces.data_repository import ConversationContextStore
from infra.data.external.redis.redis_chat_message_history import RedisChatMessageHistory
from infra.data.external.redis.redis_conversation_context_store import (
    RedisConversationContextStore,
)
from infra.user_lock_registry import UserLockRegistry, get_user_lock_registry


# ===========================================================================
# Helpers
# ===========================================================================

_USER_ID = "user-redis-1"
_OTHER_USER_ID = "user-redis-2"
_HISTORY_KEY = f"chat_history:{_USER_ID}"
_SUMMARY_KEY = f"chat_summary:{_USER_ID}"

_ASYNC_RUNNER_PATCH = "infra.async_runner.run"


def _sync(coro):
    """Drive a coroutine on the test-thread event loop (no pytest-asyncio)."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _human(content: str) -> dict:
    return {"type": "human", "content": content}


def _ai(content: str) -> dict:
    return {"type": "ai", "content": content}


def _sample_history() -> list[dict]:
    """Six messages = three complete human/ai turns."""
    return [
        _human("oi"),
        _ai("Olá! Tudo bem?"),
        _human("me lembra de comprar leite"),
        _ai("Anotado: leite."),
        _human("e o que falamos ontem?"),
        _ai("Falamos sobre a viagem."),
    ]


def _prefix_of(history: list[dict], count: int) -> tuple[int, str]:
    """Snapshot a prefix the way ContextCompactionAppService will: count + digest."""
    return count, conversation_digest(history[:count])


def _make_pipeline(data: dict) -> MagicMock:
    """
    A Redis pipeline (MULTI) mock. Commands are queued synchronously (redis-py
    returns the pipeline itself) and applied to `data` only when `execute()` is
    awaited — so a test can assert that BOTH writes land in a single round-trip.
    """
    pipe = MagicMock()
    queued: list[tuple] = []

    def _set(key, value):
        queued.append(("set", key, value))
        return pipe

    def _expire(key, ttl):
        queued.append(("expire", key, ttl))
        return pipe

    async def _execute(*_args, **_kwargs):
        results = []
        for command in queued:
            if command[0] == "set":
                data[command[1]] = command[2]
            results.append(True)
        queued.clear()
        return results

    pipe.set = MagicMock(side_effect=_set)
    pipe.expire = MagicMock(side_effect=_expire)
    pipe.execute = AsyncMock(side_effect=_execute)
    # Support an `async with client.pipeline() as pipe:` implementation too.
    pipe.__aenter__.return_value = pipe
    pipe.__aexit__.return_value = False
    return pipe


def _make_context_repo(data: dict | None = None, probe=None) -> MagicMock:
    """
    A ContextRepository MagicMock backed by a plain dict.

    `probe(operation, key)` — when given, is called on every repository/pipeline
    operation, letting a test record WHEN each call happened (e.g. whether the
    per-user lock was held at that moment).
    """
    data = {} if data is None else data

    def _record(operation: str, key):
        if probe is not None:
            probe(operation, key)

    def _get(key):
        _record("get_key", key)
        return data.get(key)

    def _set(key, value):
        _record("set_key", key)
        data[key] = value
        return True

    def _delete(key):
        _record("delete_key", key)
        return data.pop(key, None) is not None

    repo = MagicMock()
    repo.data = data
    repo.get_key = AsyncMock(side_effect=_get)
    repo.set_key = AsyncMock(side_effect=_set)
    repo.delete_key = AsyncMock(side_effect=_delete)

    pipe = _make_pipeline(data)
    original_execute = pipe.execute.side_effect

    async def _execute_with_probe(*args, **kwargs):
        _record("pipeline_execute", None)
        return await original_execute(*args, **kwargs)

    pipe.execute = AsyncMock(side_effect=_execute_with_probe)

    client = MagicMock()
    client.pipeline = MagicMock(return_value=pipe)
    repo._get_client = MagicMock(return_value=client)
    repo.redis_client = client
    repo.redis_pipeline = pipe
    return repo


def _make_store(
    context_repo=None,
    ttl_seconds=None,
    lock_registry=None,
) -> RedisConversationContextStore:
    if context_repo is None:
        context_repo = _make_context_repo()
    return RedisConversationContextStore(
        context_repo=context_repo,
        ttl_seconds=ttl_seconds,
        lock_registry=lock_registry,
    )


def _stored_history(repo: MagicMock) -> list[dict]:
    return json.loads(repo.data[_HISTORY_KEY])


def _stored_summary(repo: MagicMock) -> dict:
    return json.loads(repo.data[_SUMMARY_KEY])


class _RecordingLock:
    """A threading.Lock proxy that records every acquire/release."""

    def __init__(self, events: list, user_id: str):
        self._lock = threading.Lock()
        self._events = events
        self._user_id = user_id

    def acquire(self, *args, **kwargs):
        acquired = self._lock.acquire(*args, **kwargs)
        if acquired:
            self._events.append(("acquire", self._user_id))
        return acquired

    def release(self):
        self._lock.release()
        self._events.append(("release", self._user_id))

    def locked(self) -> bool:
        return self._lock.locked()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc_info):
        self.release()
        return False


class _RecordingLockRegistry:
    """Duck-types UserLockRegistry: one recording lock per user_id."""

    def __init__(self, events: list):
        self._events = events
        self._locks: dict[str, _RecordingLock] = {}

    def get(self, user_id: str) -> _RecordingLock:
        if user_id not in self._locks:
            self._locks[user_id] = _RecordingLock(self._events, user_id)
        return self._locks[user_id]


# ===========================================================================
# ABC contract and keys
# ===========================================================================


class TestRedisConversationContextStoreContract:
    def test_redis_store__is_a_conversation_context_store(self):
        assert isinstance(_make_store(), ConversationContextStore)

    def test_read_history__uses_the_chat_history_key(self):
        repo = _make_context_repo()
        store = _make_store(repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.read_history(_USER_ID)

        repo.get_key.assert_called_once_with(_HISTORY_KEY)

    def test_get_summary__uses_the_chat_summary_key(self):
        repo = _make_context_repo()
        store = _make_store(repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.get_summary(_USER_ID)

        repo.get_key.assert_called_once_with(_SUMMARY_KEY)

    def test_read_history__shares_the_key_with_redis_chat_message_history(self):
        # The store reads exactly the array RedisChatMessageHistory writes —
        # a divergent key would make the compaction read an empty history.
        repo = _make_context_repo()
        history = RedisChatMessageHistory(_USER_ID, repo)
        store = _make_store(repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            history.add_messages(
                [HumanMessage(content="acenda a luz"), AIMessage(content="Pronto!")]
            )
            result = store.read_history(_USER_ID)

        assert result == [_human("acenda a luz"), _ai("Pronto!")]


# ===========================================================================
# read_history
# ===========================================================================


class TestRedisConversationContextStoreReadHistory:
    def test_read_history__missing_key__returns_empty_list(self):
        store = _make_store(_make_context_repo())

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            assert store.read_history(_USER_ID) == []

    def test_read_history__string_none__returns_empty_list(self):
        # RedisContextRepository.get_key wraps a missing value in str() -> "None".
        repo = _make_context_repo({_HISTORY_KEY: "None"})
        store = _make_store(repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            assert store.read_history(_USER_ID) == []

    def test_read_history__stored_array__returns_dicts_in_order(self):
        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            assert store.read_history(_USER_ID) == history

    def test_read_history__corrupt_json__returns_empty_list(self):
        # Fail-safe: a corrupt array must degrade to "no history to compact",
        # never crash the background task.
        repo = _make_context_repo({_HISTORY_KEY: "{not json"})
        store = _make_store(repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            assert store.read_history(_USER_ID) == []

    def test_read_history__json_that_is_not_a_list__returns_empty_list(self):
        repo = _make_context_repo({_HISTORY_KEY: json.dumps({"type": "human"})})
        store = _make_store(repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            assert store.read_history(_USER_ID) == []

    def test_read_history__does_not_acquire_the_user_lock(self):
        # Deadlock guard: apply_compaction re-reads the history INSIDE the
        # per-user lock. A non-reentrant threading.Lock taken by read_history
        # would deadlock the CAS against itself.
        events: list = []
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(_sample_history())})
        store = _make_store(repo, lock_registry=_RecordingLockRegistry(events))

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.read_history(_USER_ID)

        assert events == []


# ===========================================================================
# get_summary
# ===========================================================================


class TestRedisConversationContextStoreGetSummary:
    def test_get_summary__missing_key__returns_none(self):
        store = _make_store(_make_context_repo())

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            assert store.get_summary(_USER_ID) is None

    def test_get_summary__string_none__returns_none(self):
        repo = _make_context_repo({_SUMMARY_KEY: "None"})
        store = _make_store(repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            assert store.get_summary(_USER_ID) is None

    def test_get_summary__stored_envelope__returns_it(self):
        envelope = {
            "summary": "### Assuntos em andamento\n- Viagem para a praia.",
            "covers": 14,
            "updated_at": "2026-07-08T19:24:00",
        }
        repo = _make_context_repo({_SUMMARY_KEY: json.dumps(envelope)})
        store = _make_store(repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            result = store.get_summary(_USER_ID)

        assert result["summary"] == envelope["summary"]
        assert result["covers"] == 14
        assert result["updated_at"] == "2026-07-08T19:24:00"

    def test_get_summary__corrupt_json__returns_none(self):
        # Fail-safe (plan §6.4): OnlyTalkGraph must simply run without a summary.
        repo = _make_context_repo({_SUMMARY_KEY: "### não é json"})
        store = _make_store(repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            assert store.get_summary(_USER_ID) is None

    def test_get_summary__json_that_is_not_an_object__returns_none(self):
        repo = _make_context_repo({_SUMMARY_KEY: json.dumps(["resumo"])})
        store = _make_store(repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            assert store.get_summary(_USER_ID) is None

    def test_get_summary__envelope_without_summary_text__returns_none(self):
        repo = _make_context_repo({_SUMMARY_KEY: json.dumps({"covers": 4})})
        store = _make_store(repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            assert store.get_summary(_USER_ID) is None

    def test_get_summary__does_not_acquire_the_user_lock(self):
        events: list = []
        store = _make_store(lock_registry=_RecordingLockRegistry(events))

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.get_summary(_USER_ID)

        assert events == []


# ===========================================================================
# apply_compaction — the logical CAS
# ===========================================================================


class TestRedisConversationContextStoreApplyCompaction:
    def test_apply_compaction__prefix_matches__returns_true(self):
        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo)
        count, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            applied = store.apply_compaction(_USER_ID, count, digest, "### R\n- a")

        assert applied is True

    def test_apply_compaction__prefix_matches__history_becomes_the_tail(self):
        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo)
        count, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, count, digest, "### R\n- a")

        assert _stored_history(repo) == history[4:]

    def test_apply_compaction__prefix_matches__writes_the_summary_envelope(self):
        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo)
        count, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, count, digest, "### R\n- leite")

        envelope = _stored_summary(repo)
        assert envelope["summary"] == "### R\n- leite"
        assert envelope["covers"] == 4
        # An ISO-8601 timestamp the operator (and a future TTL policy) can read.
        datetime.fromisoformat(envelope["updated_at"])

    def test_apply_compaction__turns_appended_during_the_llm_call__are_kept_in_the_tail(
        self,
    ):
        # The snapshot is taken BEFORE the (slow) LLM call and the lock is NOT
        # held during it, so `_persist_turn` keeps appending. The CAS must
        # rewrite the history with the tail AS IT IS NOW, not as it was then.
        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo)
        count, digest = _prefix_of(history, 4)

        redis_history = RedisChatMessageHistory(_USER_ID, repo)
        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            # ... LLM is summarising; the user sends another turn ...
            redis_history.add_messages(
                [HumanMessage(content="mais uma"), AIMessage(content="claro!")]
            )
            applied = store.apply_compaction(_USER_ID, count, digest, "### R\n- a")

        assert applied is True
        assert _stored_history(repo) == history[4:] + [_human("mais uma"), _ai("claro!")]

    def test_apply_compaction__rereads_the_history_inside_the_lock(self):
        # The CAS must NOT trust a snapshot read before the lock was taken: the
        # read that feeds the verification has to happen while the lock is held.
        events: list = []
        registry = _RecordingLockRegistry(events)
        lock_holder = {}

        def _probe(operation, key):
            lock = lock_holder.get("lock")
            events.append((operation, key, lock.locked() if lock else False))

        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)}, probe=_probe)
        store = _make_store(repo, lock_registry=registry)
        lock_holder["lock"] = registry.get(_USER_ID)
        count, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, count, digest, "### R\n- a")

        history_reads = [
            event
            for event in events
            if event[0] == "get_key" and event[1] == _HISTORY_KEY
        ]
        assert history_reads, "apply_compaction must re-read the history array."
        assert all(held for _, _, held in history_reads), (
            "The history re-read must happen INSIDE the per-user lock, otherwise "
            f"a turn can be appended between the read and the swap. Events: {events}"
        )

    def test_apply_compaction__writes_happen_inside_the_lock(self):
        events: list = []
        registry = _RecordingLockRegistry(events)
        lock_holder = {}

        def _probe(operation, key):
            lock = lock_holder.get("lock")
            events.append((operation, key, lock.locked() if lock else False))

        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)}, probe=_probe)
        store = _make_store(repo, lock_registry=registry)
        lock_holder["lock"] = registry.get(_USER_ID)
        count, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, count, digest, "### R\n- a")

        writes = [
            event
            for event in events
            if event[0] in ("pipeline_execute", "set_key", "delete_key")
        ]
        assert writes, "apply_compaction must write something on a matching CAS."
        assert all(held for _, _, held in writes), (
            f"Every write must happen while the per-user lock is held. Events: {events}"
        )

    def test_apply_compaction__summary_and_tail__in_a_single_lock_acquisition(self):
        events: list = []
        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo, lock_registry=_RecordingLockRegistry(events))
        count, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, count, digest, "### R\n- a")

        assert events == [("acquire", _USER_ID), ("release", _USER_ID)], (
            "Read-verify-write must be a SINGLE acquisition of the per-user lock "
            f"(microseconds, never around the LLM call). Recorded: {events}"
        )

    def test_apply_compaction__summary_and_tail__written_in_one_pipeline(self):
        # Both keys go out in one MULTI: the intermediate state "history
        # truncated but summary not written yet" is unrecoverable context loss.
        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo)
        count, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, count, digest, "### R\n- a")

        pipe = repo.redis_pipeline
        assert repo.redis_client.pipeline.call_count == 1
        assert pipe.execute.await_count == 1, (
            "The summary write and the history rewrite must be executed as ONE "
            "transaction, not as two independent round-trips."
        )
        keys_written = [call.args[0] for call in pipe.set.call_args_list]
        assert sorted(keys_written) == sorted([_HISTORY_KEY, _SUMMARY_KEY])

    def test_apply_compaction__does_not_write_the_history_outside_the_pipeline(self):
        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo)
        count, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, count, digest, "### R\n- a")

        repo.set_key.assert_not_awaited()

    def test_apply_compaction__returns_a_bool(self):
        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo)
        count, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            result = store.apply_compaction(_USER_ID, count, digest, "### R\n- a")

        assert isinstance(result, bool)


class TestRedisConversationContextStoreApplyCompactionAborts:
    """Every abort path: return False and touch NOTHING (never write the summary)."""

    def test_apply_compaction__count_mismatch__returns_false(self):
        history = _sample_history()  # 6 messages
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo)
        _, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            # The array is SHORTER than the prefix that was summarised: another
            # compaction (or a reset + fresh turns) got there first.
            applied = store.apply_compaction(_USER_ID, 8, digest, "### R\n- a")

        assert applied is False

    def test_apply_compaction__count_mismatch__touches_nothing(self):
        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo)
        _, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, 8, digest, "### R\n- a")

        assert _stored_history(repo) == history
        assert _SUMMARY_KEY not in repo.data
        repo.redis_client.pipeline.assert_not_called()
        repo.set_key.assert_not_awaited()
        repo.delete_key.assert_not_awaited()

    def test_apply_compaction__digest_mismatch__returns_false(self):
        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo)
        # Same length, different content: the user reset and started over.
        stale_digest = conversation_digest([_human("outra conversa")] * 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            applied = store.apply_compaction(_USER_ID, 4, stale_digest, "### R\n- a")

        assert applied is False

    def test_apply_compaction__digest_mismatch__touches_nothing(self):
        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo)
        stale_digest = conversation_digest([_human("outra conversa")] * 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, 4, stale_digest, "### R\n- a")

        assert _stored_history(repo) == history
        assert _SUMMARY_KEY not in repo.data
        repo.redis_client.pipeline.assert_not_called()

    def test_apply_compaction__history_cleared_concurrently__returns_false(self):
        # reset_context deleted chat_history while the LLM was summarising.
        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo)
        count, digest = _prefix_of(history, 4)

        redis_history = RedisChatMessageHistory(_USER_ID, repo)
        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            redis_history.clear()
            applied = store.apply_compaction(_USER_ID, count, digest, "### R\n- a")

        assert applied is False
        assert _HISTORY_KEY not in repo.data, (
            "An aborted CAS must not resurrect the history the user just reset."
        )
        assert _SUMMARY_KEY not in repo.data, (
            "An aborted CAS must NEVER write the summary — it would resurrect "
            "turns the user explicitly deleted."
        )

    def test_apply_compaction__missing_history_key__returns_false(self):
        repo = _make_context_repo()
        store = _make_store(repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            applied = store.apply_compaction(
                _USER_ID, 4, conversation_digest(_sample_history()[:4]), "### R\n- a"
            )

        assert applied is False
        assert _SUMMARY_KEY not in repo.data

    def test_apply_compaction__corrupt_history__returns_false_and_writes_nothing(self):
        repo = _make_context_repo({_HISTORY_KEY: "{not json"})
        store = _make_store(repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            applied = store.apply_compaction(
                _USER_ID, 4, conversation_digest(_sample_history()[:4]), "### R\n- a"
            )

        assert applied is False
        assert _SUMMARY_KEY not in repo.data

    def test_apply_compaction__abort__does_not_overwrite_a_previous_summary(self):
        history = _sample_history()
        previous = {
            "summary": "### R\n- resumo em vigor",
            "covers": 4,
            "updated_at": "2026-07-08T19:00:00",
        }
        repo = _make_context_repo(
            {_HISTORY_KEY: json.dumps(history), _SUMMARY_KEY: json.dumps(previous)}
        )
        store = _make_store(repo)
        stale_digest = conversation_digest([_human("outra conversa")] * 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, 4, stale_digest, "### R\n- resumo obsoleto")

        assert _stored_summary(repo)["summary"] == "### R\n- resumo em vigor"

    def test_apply_compaction__abort__still_releases_the_lock(self):
        events: list = []
        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo, lock_registry=_RecordingLockRegistry(events))

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, 99, "deadbeef", "### R\n- a")

        assert events == [("acquire", _USER_ID), ("release", _USER_ID)]


class TestRedisConversationContextStoreCovers:
    def test_apply_compaction__first_compaction__covers_is_the_prefix_length(self):
        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo)
        count, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, count, digest, "### R\n- a")

        assert _stored_summary(repo)["covers"] == 4

    def test_apply_compaction__incremental__covers_accumulates(self):
        # The summary is incremental (the raw prefix is physically dropped), so
        # `covers` is the TOTAL number of messages it now stands for.
        history = _sample_history()
        previous = {
            "summary": "### R\n- anterior",
            "covers": 10,
            "updated_at": "2026-07-08T19:00:00",
        }
        repo = _make_context_repo(
            {_HISTORY_KEY: json.dumps(history), _SUMMARY_KEY: json.dumps(previous)}
        )
        store = _make_store(repo)
        count, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, count, digest, "### R\n- anterior + novo")

        assert _stored_summary(repo)["covers"] == 14

    def test_apply_compaction__corrupt_previous_summary__covers_falls_back_to_prefix(
        self,
    ):
        history = _sample_history()
        repo = _make_context_repo(
            {_HISTORY_KEY: json.dumps(history), _SUMMARY_KEY: "{not json"}
        )
        store = _make_store(repo)
        count, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            applied = store.apply_compaction(_USER_ID, count, digest, "### R\n- a")

        assert applied is True
        assert _stored_summary(repo)["covers"] == 4


# ===========================================================================
# TTL — mirrors RedisChatMessageHistory (non-positive TTL = no expiry)
# ===========================================================================


class TestRedisConversationContextStoreTTL:
    def test_apply_compaction__ttl_set__expires_both_keys(self):
        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo, ttl_seconds=3600)
        count, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, count, digest, "### R\n- a")

        expired = {
            (call.args[0], call.args[1])
            for call in repo.redis_pipeline.expire.call_args_list
        }
        assert expired == {(_HISTORY_KEY, 3600), (_SUMMARY_KEY, 3600)}, (
            "The summary must carry the SAME TTL as the history (plan §3.3), "
            "otherwise it outlives the conversation it summarises."
        )

    @pytest.mark.parametrize("ttl", [None, 0, -1])
    def test_apply_compaction__non_positive_ttl__does_not_expire(self, ttl):
        # `EXPIRE key 0` deletes the key immediately in Redis — that would wipe
        # the history on every compaction.
        history = _sample_history()
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(history)})
        store = _make_store(repo, ttl_seconds=ttl)
        count, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, count, digest, "### R\n- a")

        repo.redis_pipeline.expire.assert_not_called()


# ===========================================================================
# clear
# ===========================================================================


class TestRedisConversationContextStoreClear:
    def test_clear__deletes_both_keys(self):
        repo = _make_context_repo(
            {
                _HISTORY_KEY: json.dumps(_sample_history()),
                _SUMMARY_KEY: json.dumps({"summary": "### R", "covers": 4}),
            }
        )
        store = _make_store(repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.clear(_USER_ID)

        deleted = {call.args[0] for call in repo.delete_key.call_args_list}
        assert deleted == {_HISTORY_KEY, _SUMMARY_KEY}, (
            "clear() must wipe history AND summary (plan §3.2) — a surviving "
            "summary would resurrect the context the user just reset."
        )
        assert repo.data == {}

    def test_clear__no_keys__does_not_raise(self):
        repo = _make_context_repo()
        store = _make_store(repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.clear(_USER_ID)

    def test_clear__holds_the_user_lock(self):
        # Without the lock, a concurrent CAS could land between clear()'s two
        # deletes and rewrite the history the user just reset.
        events: list = []
        repo = _make_context_repo({_HISTORY_KEY: json.dumps(_sample_history())})
        store = _make_store(repo, lock_registry=_RecordingLockRegistry(events))

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.clear(_USER_ID)

        assert events == [("acquire", _USER_ID), ("release", _USER_ID)]

    def test_clear__other_user__is_untouched(self):
        other_key = f"chat_history:{_OTHER_USER_ID}"
        repo = _make_context_repo(
            {
                _HISTORY_KEY: json.dumps(_sample_history()),
                other_key: json.dumps([_human("do outro")]),
            }
        )
        store = _make_store(repo)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.clear(_USER_ID)

        assert other_key in repo.data


# ===========================================================================
# UserLockRegistry — the shared per-user lock registry (plan §3.5)
# ===========================================================================


class TestUserLockRegistry:
    def test_get__same_user_id__returns_the_same_lock_object(self):
        registry = UserLockRegistry()

        assert registry.get(_USER_ID) is registry.get(_USER_ID), (
            "The registry must hand out ONE lock per user_id — a fresh lock per "
            "call would serialise nothing."
        )

    def test_get__different_user_ids__returns_different_locks(self):
        registry = UserLockRegistry()

        assert registry.get(_USER_ID) is not registry.get(_OTHER_USER_ID), (
            "Locks are per user: one user's compaction must not block another "
            "user's turn from being persisted."
        )

    def test_get__returns_something_usable_as_a_context_manager(self):
        lock = UserLockRegistry().get(_USER_ID)

        with lock:
            assert lock.locked() is True
        assert lock.locked() is False

    def test_get_user_lock_registry__is_a_process_wide_singleton(self):
        # The default registry is what makes components that were NOT given an
        # explicit registry still share the same locks.
        assert get_user_lock_registry() is get_user_lock_registry()
        assert isinstance(get_user_lock_registry(), UserLockRegistry)


class TestRedisConversationContextStoreLockRegistry:
    def test_apply_compaction__uses_the_lock_from_the_injected_registry(self):
        registry = UserLockRegistry()
        lock = registry.get(_USER_ID)
        observed: list[bool] = []

        history = _sample_history()
        repo = _make_context_repo(
            {_HISTORY_KEY: json.dumps(history)},
            probe=lambda _operation, _key: observed.append(lock.locked()),
        )
        store = _make_store(repo, lock_registry=registry)
        count, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, count, digest, "### R\n- a")

        assert observed and all(observed), (
            "The store must take the lock the INJECTED registry hands out for "
            "this user_id — a private lock of its own would serialise nothing "
            "against RedisChatMessageHistory.add_messages."
        )

    def test_apply_compaction__no_registry_injected__uses_the_default_registry(self):
        lock = get_user_lock_registry().get(_USER_ID)
        observed: list[bool] = []

        history = _sample_history()
        repo = _make_context_repo(
            {_HISTORY_KEY: json.dumps(history)},
            probe=lambda _operation, _key: observed.append(lock.locked()),
        )
        store = _make_store(repo)  # no lock_registry
        count, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, count, digest, "### R\n- a")

        assert observed and all(observed)

    def test_apply_compaction__other_users_lock__is_not_held(self):
        registry = UserLockRegistry()
        other_lock = registry.get(_OTHER_USER_ID)
        observed: list[bool] = []

        history = _sample_history()
        repo = _make_context_repo(
            {_HISTORY_KEY: json.dumps(history)},
            probe=lambda _operation, _key: observed.append(other_lock.locked()),
        )
        store = _make_store(repo, lock_registry=registry)
        count, digest = _prefix_of(history, 4)

        with patch(_ASYNC_RUNNER_PATCH, side_effect=_sync):
            store.apply_compaction(_USER_ID, count, digest, "### R\n- a")

        assert observed and not any(observed)
