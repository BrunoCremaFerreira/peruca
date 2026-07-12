"""
InMemoryConversationContextStore unit tests — Phase B / F2 (TDD RED phase).

Drives the in-memory implementation of the `ConversationContextStore` ABC
(plan §3.2), the fallback used when no Redis (CACHE_DB_CONNECTION_STRING) is
configured:

    domain/interfaces/data_repository.py
        class ConversationContextStore(ABC):
            def get_summary(self, user_id: str) -> Optional[dict]
            def read_history(self, user_id: str) -> list[dict]
            def apply_compaction(self, user_id: str, expected_count: int,
                                 expected_digest: str, summary: str) -> bool
            def clear(self, user_id: str) -> None

    infra/data/cache/in_memory_conversation_context_store.py
        class InMemoryConversationContextStore(ConversationContextStore):
            def __init__(self, history_store: dict[str, InMemoryChatMessageHistory],
                         lock_registry: Optional[UserLockRegistry] = None)

THE central requirement pinned here (plan §3.1, table row "InMemoryConversationContextStore"):
the store operates on the **same dict** that `ioc._get_session_history_factory()`
hands to `OnlyTalkGraph` / `LlmAppService` — it receives that registry by
INJECTION and never builds one of its own. If someone gives the store a parallel
dict, the compaction truncates a history nobody reads and `OnlyTalkGraph` keeps
seeing the full (uncompacted) array. `TestInMemoryConversationContextStoreSharesSessionDict`
fails loudly in that case: it writes through the session-history factory and reads
through the store, and vice-versa.

CAS semantics (plan §3.4 step 5 / §3.5), identical to the Redis store:
  - under the per-user lock, RE-READ the history (never trust the snapshot taken
    before the LLM call);
  - apply only when the prefix still matches `expected_count` + `expected_digest`;
  - on match: write the summary AND rewrite the history with the CURRENT tail
    (which includes turns appended while the LLM was running);
  - on mismatch (reset / concurrent compaction / cleared history): return False
    and touch NOTHING — most importantly, NEVER write the summary (a summary
    written without truncating is benign duplication; truncating without the
    summary is real data loss).

Written BEFORE the implementation: expected to FAIL RED with ImportError.
"""

import threading

import pytest
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage

from domain.services.conversation_digest import conversation_digest
from domain.interfaces.data_repository import ConversationContextStore
from infra.data.cache.in_memory_conversation_context_store import (
    InMemoryConversationContextStore,
)


# ===========================================================================
# Helpers
# ===========================================================================

_USER_ID = "user-in-memory-1"
_OTHER_USER_ID = "user-in-memory-2"


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


def _to_messages(dicts: list[dict]) -> list:
    """Serialized dicts -> langchain BaseMessage objects."""
    return [
        HumanMessage(content=item["content"])
        if item["type"] == "human"
        else AIMessage(content=item["content"])
        for item in dicts
    ]


def _make_session_store(
    history: dict[str, list[dict]] | None = None,
) -> dict[str, InMemoryChatMessageHistory]:
    """
    Build the dict that `ioc._get_session_history_factory()` closes over in its
    in-memory branch: {session_id: InMemoryChatMessageHistory}.
    """
    session_store: dict[str, InMemoryChatMessageHistory] = {}
    for session_id, dicts in (history or {}).items():
        chat_history = InMemoryChatMessageHistory()
        chat_history.add_messages(_to_messages(dicts))
        session_store[session_id] = chat_history
    return session_store


def _make_get_session_history(session_store: dict):
    """
    Replica of the in-memory closure in `ioc._get_session_history_factory()` —
    the exact function `OnlyTalkGraph` and `LlmAppService._persist_turn()` use.
    The store under test MUST share this very dict.
    """

    def _get_session_history(session_id: str) -> InMemoryChatMessageHistory:
        if session_id not in session_store:
            session_store[session_id] = InMemoryChatMessageHistory()
        return session_store[session_id]

    return _get_session_history


def _make_store(
    session_store: dict | None = None,
    lock_registry=None,
) -> InMemoryConversationContextStore:
    if session_store is None:
        session_store = _make_session_store()
    return InMemoryConversationContextStore(
        history_store=session_store,
        lock_registry=lock_registry,
    )


def _prefix_of(history: list[dict], count: int) -> tuple[int, str]:
    """Snapshot a prefix the way ContextCompactionAppService will: count + digest."""
    return count, conversation_digest(history[:count])


# ===========================================================================
# ABC contract
# ===========================================================================


class TestInMemoryConversationContextStoreContract:
    def test_in_memory_store__is_a_conversation_context_store(self):
        assert isinstance(_make_store(), ConversationContextStore), (
            "InMemoryConversationContextStore must implement the "
            "ConversationContextStore ABC (domain/interfaces/data_repository.py)."
        )


# ===========================================================================
# read_history
# ===========================================================================


class TestInMemoryConversationContextStoreReadHistory:
    def test_read_history__unknown_user__returns_empty_list(self):
        store = _make_store()
        assert store.read_history(_USER_ID) == []

    def test_read_history__existing_history__returns_serialized_dicts_in_order(self):
        history = _sample_history()
        store = _make_store(_make_session_store({_USER_ID: history}))

        assert store.read_history(_USER_ID) == history

    def test_read_history__human_and_ai__maps_message_types(self):
        session_store = _make_session_store()
        chat_history = InMemoryChatMessageHistory()
        chat_history.add_messages([HumanMessage(content="pergunta"), AIMessage(content="resposta")])
        session_store[_USER_ID] = chat_history

        result = _make_store(session_store).read_history(_USER_ID)

        assert result == [_human("pergunta"), _ai("resposta")], (
            "read_history must return the SERIALIZED form used by the Redis "
            'history array: [{"type": "human"|"ai", "content": str}].'
        )

    def test_read_history__other_user__is_isolated(self):
        session_store = _make_session_store(
            {_USER_ID: [_human("meu")], _OTHER_USER_ID: [_human("do outro")]}
        )
        store = _make_store(session_store)

        assert store.read_history(_USER_ID) == [_human("meu")]
        assert store.read_history(_OTHER_USER_ID) == [_human("do outro")]

    def test_read_history__does_not_acquire_the_user_lock(self):
        # Deadlock guard: apply_compaction re-reads the history INSIDE the
        # per-user lock. If read_history acquired the same non-reentrant
        # threading.Lock, the CAS would deadlock on itself.
        events: list = []
        registry = _RecordingLockRegistry(events)
        store = _make_store(
            _make_session_store({_USER_ID: _sample_history()}),
            lock_registry=registry,
        )

        store.read_history(_USER_ID)

        assert events == [], (
            "read_history must NOT acquire the per-user lock — apply_compaction "
            "re-reads the history while holding it (non-reentrant Lock = deadlock)."
        )


# ===========================================================================
# get_summary
# ===========================================================================


class TestInMemoryConversationContextStoreGetSummary:
    def test_get_summary__never_compacted__returns_none(self):
        assert _make_store().get_summary(_USER_ID) is None

    def test_get_summary__after_compaction__returns_summary_envelope(self):
        history = _sample_history()
        store = _make_store(_make_session_store({_USER_ID: history}))
        count, digest = _prefix_of(history, 4)

        store.apply_compaction(
            user_id=_USER_ID,
            expected_count=count,
            expected_digest=digest,
            summary="### Assuntos em andamento\n- Compra de leite.",
        )
        result = store.get_summary(_USER_ID)

        assert result is not None
        assert result["summary"] == "### Assuntos em andamento\n- Compra de leite."
        assert result["covers"] == 4
        assert isinstance(result["updated_at"], str) and result["updated_at"]

    def test_get_summary__other_user__is_isolated(self):
        history = _sample_history()
        store = _make_store(_make_session_store({_USER_ID: history}))
        count, digest = _prefix_of(history, 4)
        store.apply_compaction(_USER_ID, count, digest, "### Resumo\n- x")

        assert store.get_summary(_OTHER_USER_ID) is None

    def test_get_summary__does_not_acquire_the_user_lock(self):
        events: list = []
        store = _make_store(lock_registry=_RecordingLockRegistry(events))

        store.get_summary(_USER_ID)

        assert events == []


# ===========================================================================
# apply_compaction — the logical CAS
# ===========================================================================


class TestInMemoryConversationContextStoreApplyCompaction:
    def test_apply_compaction__prefix_matches__returns_true(self):
        history = _sample_history()
        store = _make_store(_make_session_store({_USER_ID: history}))
        count, digest = _prefix_of(history, 4)

        assert store.apply_compaction(_USER_ID, count, digest, "### Resumo\n- a") is True

    def test_apply_compaction__prefix_matches__history_becomes_the_tail(self):
        history = _sample_history()
        session_store = _make_session_store({_USER_ID: history})
        store = _make_store(session_store)
        count, digest = _prefix_of(history, 4)

        store.apply_compaction(_USER_ID, count, digest, "### Resumo\n- a")

        assert store.read_history(_USER_ID) == history[4:], (
            "On a matching CAS the history must be rewritten with the tail "
            "(everything after the compacted prefix)."
        )

    def test_apply_compaction__prefix_matches__stores_the_summary(self):
        history = _sample_history()
        store = _make_store(_make_session_store({_USER_ID: history}))
        count, digest = _prefix_of(history, 4)

        store.apply_compaction(_USER_ID, count, digest, "### Resumo\n- a")

        assert store.get_summary(_USER_ID)["summary"] == "### Resumo\n- a"

    def test_apply_compaction__turns_appended_during_the_llm_call__are_kept_in_the_tail(
        self,
    ):
        # The compaction snapshots the prefix, then calls the LLM for SECONDS
        # with NO lock held. New turns land in the history meanwhile. The CAS
        # must re-read and keep them — writing the tail as it was at snapshot
        # time would silently drop the turns made during the summarisation.
        history = _sample_history()
        session_store = _make_session_store({_USER_ID: history})
        get_session_history = _make_get_session_history(session_store)
        store = _make_store(session_store)

        count, digest = _prefix_of(history, 4)  # snapshot BEFORE the LLM call

        # ... LLM runs; the user keeps chatting (LlmAppService._persist_turn) ...
        get_session_history(_USER_ID).add_messages(
            [HumanMessage(content="mais uma"), AIMessage(content="claro!")]
        )

        applied = store.apply_compaction(_USER_ID, count, digest, "### Resumo\n- a")

        assert applied is True
        assert store.read_history(_USER_ID) == history[4:] + [
            _human("mais uma"),
            _ai("claro!"),
        ]

    def test_apply_compaction__count_mismatch__returns_false(self):
        history = _sample_history()  # 6 messages
        store = _make_store(_make_session_store({_USER_ID: history}))
        _, digest = _prefix_of(history, 4)

        # A prefix longer than the whole history: the array shrank under us
        # (another compaction ran) — never compact what is no longer there.
        assert store.apply_compaction(_USER_ID, 8, digest, "### Resumo\n- a") is False

    def test_apply_compaction__count_mismatch__touches_nothing(self):
        history = _sample_history()
        store = _make_store(_make_session_store({_USER_ID: history}))
        _, digest = _prefix_of(history, 4)

        store.apply_compaction(_USER_ID, 8, digest, "### Resumo\n- a")

        assert store.read_history(_USER_ID) == history
        assert store.get_summary(_USER_ID) is None

    def test_apply_compaction__digest_mismatch__returns_false(self):
        history = _sample_history()
        store = _make_store(_make_session_store({_USER_ID: history}))

        # The digest was taken over a DIFFERENT prefix (a reset + new
        # conversation of the same length is the realistic case).
        stale_digest = conversation_digest([_human("outra conversa")] * 4)

        assert (
            store.apply_compaction(_USER_ID, 4, stale_digest, "### Resumo\n- a") is False
        )

    def test_apply_compaction__digest_mismatch__touches_nothing(self):
        history = _sample_history()
        store = _make_store(_make_session_store({_USER_ID: history}))
        stale_digest = conversation_digest([_human("outra conversa")] * 4)

        store.apply_compaction(_USER_ID, 4, stale_digest, "### Resumo\n- a")

        assert store.read_history(_USER_ID) == history
        assert store.get_summary(_USER_ID) is None

    def test_apply_compaction__history_cleared_concurrently__returns_false(self):
        # reset_context ran while the LLM was summarising.
        history = _sample_history()
        session_store = _make_session_store({_USER_ID: history})
        get_session_history = _make_get_session_history(session_store)
        store = _make_store(session_store)
        count, digest = _prefix_of(history, 4)

        get_session_history(_USER_ID).clear()

        applied = store.apply_compaction(_USER_ID, count, digest, "### Resumo\n- a")

        assert applied is False
        assert store.read_history(_USER_ID) == []
        assert store.get_summary(_USER_ID) is None, (
            "An aborted CAS must NEVER write the summary — a summary of turns "
            "the user just reset would resurrect deleted context."
        )

    def test_apply_compaction__unknown_user__returns_false_and_writes_no_summary(self):
        store = _make_store()

        applied = store.apply_compaction(
            _USER_ID, 4, conversation_digest(_sample_history()[:4]), "### Resumo\n- a"
        )

        assert applied is False
        assert store.get_summary(_USER_ID) is None

    def test_apply_compaction__abort__never_writes_the_summary_over_a_previous_one(self):
        history = _sample_history()
        session_store = _make_session_store({_USER_ID: history})
        store = _make_store(session_store)

        count, digest = _prefix_of(history, 4)
        store.apply_compaction(_USER_ID, count, digest, "### Resumo\n- primeiro")

        # A second, STALE compaction (its snapshot predates the first one).
        store.apply_compaction(_USER_ID, count, digest, "### Resumo\n- segundo")

        assert store.get_summary(_USER_ID)["summary"] == "### Resumo\n- primeiro", (
            "A stale compaction must not overwrite the summary that is actually "
            "in force for the current history."
        )

    def test_apply_compaction__mutates_the_same_history_object(self):
        # The compaction must truncate the SAME InMemoryChatMessageHistory that
        # `get_session_history` returns — not swap in a fresh object in a dict
        # nobody else reads.
        history = _sample_history()
        session_store = _make_session_store({_USER_ID: history})
        original = session_store[_USER_ID]
        store = _make_store(session_store)
        count, digest = _prefix_of(history, 4)

        store.apply_compaction(_USER_ID, count, digest, "### Resumo\n- a")

        assert session_store[_USER_ID] is original, (
            "apply_compaction must not replace the InMemoryChatMessageHistory "
            "object — OnlyTalkGraph may already hold a reference to it."
        )
        assert len(original.messages) == 2


class TestInMemoryConversationContextStoreCovers:
    def test_apply_compaction__first_compaction__covers_is_the_prefix_length(self):
        history = _sample_history()
        store = _make_store(_make_session_store({_USER_ID: history}))
        count, digest = _prefix_of(history, 4)

        store.apply_compaction(_USER_ID, count, digest, "### Resumo\n- a")

        assert store.get_summary(_USER_ID)["covers"] == 4

    def test_apply_compaction__incremental__covers_accumulates(self):
        # The summary is incremental (the raw prefix is physically dropped), so
        # `covers` is the TOTAL number of messages the summary now stands for.
        history = _sample_history()
        session_store = _make_session_store({_USER_ID: history})
        get_session_history = _make_get_session_history(session_store)
        store = _make_store(session_store)

        count, digest = _prefix_of(history, 4)
        store.apply_compaction(_USER_ID, count, digest, "### Resumo\n- a")

        # New turns arrive; a second cycle compacts the new prefix.
        get_session_history(_USER_ID).add_messages(
            [HumanMessage(content="nova"), AIMessage(content="ok")]
        )
        current = store.read_history(_USER_ID)
        count2, digest2 = _prefix_of(current, 2)
        store.apply_compaction(_USER_ID, count2, digest2, "### Resumo\n- a e b")

        assert store.get_summary(_USER_ID)["covers"] == 6, (
            "covers must accumulate across incremental cycles (4 + 2), since the "
            "new summary also stands for everything the previous one covered."
        )


# ===========================================================================
# clear
# ===========================================================================


class TestInMemoryConversationContextStoreClear:
    def test_clear__removes_the_history(self):
        history = _sample_history()
        session_store = _make_session_store({_USER_ID: history})
        store = _make_store(session_store)

        store.clear(_USER_ID)

        assert store.read_history(_USER_ID) == []

    def test_clear__removes_the_summary(self):
        history = _sample_history()
        session_store = _make_session_store({_USER_ID: history})
        store = _make_store(session_store)
        count, digest = _prefix_of(history, 4)
        store.apply_compaction(_USER_ID, count, digest, "### Resumo\n- a")

        store.clear(_USER_ID)

        assert store.get_summary(_USER_ID) is None, (
            "clear() must wipe history AND summary in one place (plan §3.2) — "
            "a surviving summary would resurrect the context the user just reset."
        )

    def test_clear__unknown_user__does_not_raise(self):
        _make_store().clear(_USER_ID)

    def test_clear__other_user__is_untouched(self):
        session_store = _make_session_store(
            {_USER_ID: _sample_history(), _OTHER_USER_ID: [_human("do outro")]}
        )
        store = _make_store(session_store)

        store.clear(_USER_ID)

        assert store.read_history(_OTHER_USER_ID) == [_human("do outro")]


# ===========================================================================
# THE shared-dict requirement (plan §3.1)
# ===========================================================================


class TestInMemoryConversationContextStoreSharesSessionDict:
    """
    These tests fail if anyone gives the store a dict of its own instead of the
    one `ioc._get_session_history_factory()` hands to OnlyTalkGraph /
    LlmAppService. Writes made through the session-history factory MUST be
    visible to the store, and truncations made by the store MUST be visible on
    the very `.messages` list the graph reads.
    """

    def test_store__reads_what_get_session_history_wrote(self):
        session_store = _make_session_store()
        get_session_history = _make_get_session_history(session_store)
        store = _make_store(session_store)

        # LlmAppService._persist_turn() writes through the factory.
        get_session_history(_USER_ID).add_messages(
            [HumanMessage(content="acenda a luz"), AIMessage(content="Pronto!")]
        )

        assert store.read_history(_USER_ID) == [_human("acenda a luz"), _ai("Pronto!")], (
            "The store must read the SAME dict used by get_session_history. A "
            "parallel dict would make it read an empty history forever."
        )

    def test_apply_compaction__truncation_is_visible_through_get_session_history(self):
        history = _sample_history()
        session_store = _make_session_store({_USER_ID: history})
        get_session_history = _make_get_session_history(session_store)
        store = _make_store(session_store)
        count, digest = _prefix_of(history, 4)

        store.apply_compaction(_USER_ID, count, digest, "### Resumo\n- a")

        messages = get_session_history(_USER_ID).messages
        assert [m.content for m in messages] == [
            "e o que falamos ontem?",
            "Falamos sobre a viagem.",
        ], (
            "The truncation must be visible on the history object OnlyTalkGraph "
            "reads — otherwise the compaction shrinks nothing the graph sees."
        )

    def test_clear__is_visible_through_get_session_history(self):
        session_store = _make_session_store({_USER_ID: _sample_history()})
        get_session_history = _make_get_session_history(session_store)
        store = _make_store(session_store)

        store.clear(_USER_ID)

        assert get_session_history(_USER_ID).messages == []

    def test_store__does_not_build_its_own_history_registry(self):
        # The dict is INJECTED: a history created by the factory after the store
        # was constructed must still be visible to it.
        session_store = _make_session_store()
        store = _make_store(session_store)
        get_session_history = _make_get_session_history(session_store)

        get_session_history(_USER_ID).add_messages([HumanMessage(content="depois")])

        assert store.read_history(_USER_ID) == [_human("depois")]


# ===========================================================================
# Locking
# ===========================================================================


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


class TestInMemoryConversationContextStoreLocking:
    def test_apply_compaction__holds_the_user_lock_for_a_single_acquisition(self):
        events: list = []
        registry = _RecordingLockRegistry(events)
        history = _sample_history()
        store = _make_store(
            _make_session_store({_USER_ID: history}), lock_registry=registry
        )
        count, digest = _prefix_of(history, 4)

        store.apply_compaction(_USER_ID, count, digest, "### Resumo\n- a")

        assert events == [("acquire", _USER_ID), ("release", _USER_ID)], (
            "The re-read, the summary write and the tail rewrite must happen in "
            f"ONE lock acquisition. Recorded: {events}."
        )

    def test_apply_compaction__abort__still_releases_the_lock(self):
        events: list = []
        registry = _RecordingLockRegistry(events)
        history = _sample_history()
        store = _make_store(
            _make_session_store({_USER_ID: history}), lock_registry=registry
        )

        store.apply_compaction(_USER_ID, 99, "deadbeef", "### Resumo\n- a")

        assert events == [("acquire", _USER_ID), ("release", _USER_ID)]

    def test_clear__holds_the_user_lock(self):
        # clear() mutates history + summary; it must not race a concurrent CAS
        # (which would otherwise resurrect the history it just wiped).
        events: list = []
        registry = _RecordingLockRegistry(events)
        store = _make_store(
            _make_session_store({_USER_ID: _sample_history()}), lock_registry=registry
        )

        store.clear(_USER_ID)

        assert ("acquire", _USER_ID) in events
        assert events.count(("acquire", _USER_ID)) == 1

    def test_apply_compaction__different_users__use_different_locks(self):
        events: list = []
        registry = _RecordingLockRegistry(events)
        history = _sample_history()
        session_store = _make_session_store(
            {_USER_ID: history, _OTHER_USER_ID: history}
        )
        store = _make_store(session_store, lock_registry=registry)
        count, digest = _prefix_of(history, 4)

        store.apply_compaction(_USER_ID, count, digest, "### Resumo\n- a")
        store.apply_compaction(_OTHER_USER_ID, count, digest, "### Resumo\n- b")

        assert registry.get(_USER_ID) is not registry.get(_OTHER_USER_ID)
        assert ("acquire", _USER_ID) in events
        assert ("acquire", _OTHER_USER_ID) in events

    def test_apply_compaction__no_registry_injected__still_works(self):
        # The lock registry is optional: without one, the store falls back to the
        # process-wide default (so it still shares locks with the history writer).
        history = _sample_history()
        store = _make_store(_make_session_store({_USER_ID: history}))
        count, digest = _prefix_of(history, 4)

        assert store.apply_compaction(_USER_ID, count, digest, "### R\n- a") is True


# ===========================================================================
# TestInMemoryStoreWithALockedHistory — Phase G / P0 (TDD RED phase)
# ===========================================================================
#
# Security review, P0: `ioc` hands out LangChain's RAW InMemoryChatMessageHistory,
# whose `add_messages` takes NO lock. This store, holding the per-user lock, does
#
#       tail = history.messages[expected_count:]
#       history.clear()               # <-- a turn appended here ...
#       history.add_messages(tail)    # ... is gone forever
#
# so a request thread persisting a turn can have it erased. The fix is
# `LockedInMemoryChatMessageHistory` (infra/data/cache/), whose add_messages/clear
# take the SAME per-user lock this store takes.
#
# That creates a reentrancy trap for THIS class: it is ALREADY inside
# `with self._lock_registry.get(user_id)` when it truncates, and `threading.Lock`
# is not reentrant — calling `history.clear()` / `history.add_messages()` there
# would deadlock the compaction against itself. Hence the lock-free primitives
# `replace_all_unlocked()` / `clear_unlocked()`, which the store must prefer when
# the history exposes them (a plain InMemoryChatMessageHistory keeps working:
# it locks nothing, so its public methods are safe to call).

from infra.user_lock_registry import UserLockRegistry  # noqa: E402


def _locked_history_class():
    """
    Import the (not yet written) locked history. LAZY on purpose: RED must be an
    ImportError inside the new tests, without taking the whole file down with a
    collection error (precedent: test_redis_chat_message_history.py).
    """
    from infra.data.cache.locked_in_memory_chat_message_history import (
        LockedInMemoryChatMessageHistory,
    )

    return LockedInMemoryChatMessageHistory


def _make_locked_session_store(
    registry: UserLockRegistry,
    history: dict[str, list[dict]] | None = None,
) -> dict:
    """The dict ioc's in-memory branch will now close over: LOCKED histories."""
    locked_history_class = _locked_history_class()
    session_store: dict = {}
    for session_id, dicts in (history or {}).items():
        chat_history = locked_history_class(
            session_id=session_id, lock_registry=registry
        )
        chat_history.add_messages(_to_messages(dicts))
        session_store[session_id] = chat_history
    return session_store


def _call_with_timeout(callable_, timeout: float = 5.0):
    """Run `callable_` in a thread; returns (finished, result)."""
    outcome: list = []

    def _target():
        outcome.append(callable_())

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(timeout=timeout)
    finished = not worker.is_alive()
    return finished, (outcome[0] if outcome else None)


class TestInMemoryStoreWithALockedHistory:

    def test_apply_compaction__locked_history__does_not_deadlock(self):
        # The store already holds the user's (non-reentrant) lock when it
        # truncates: it must NOT go through the history's locking methods.
        registry = UserLockRegistry()
        history = _sample_history()
        session_store = _make_locked_session_store(registry, {_USER_ID: history})
        store = _make_store(session_store, lock_registry=registry)
        count, digest = _prefix_of(history, 4)

        finished, applied = _call_with_timeout(
            lambda: store.apply_compaction(_USER_ID, count, digest, "### R\n- a")
        )

        assert finished, (
            "apply_compaction deadlocked: it called the LOCKING clear()/"
            "add_messages() of the history while already holding that same lock."
        )
        assert applied is True

    def test_apply_compaction__locked_history__truncates_the_same_object(self):
        registry = UserLockRegistry()
        history = _sample_history()
        session_store = _make_locked_session_store(registry, {_USER_ID: history})
        original = session_store[_USER_ID]
        store = _make_store(session_store, lock_registry=registry)
        count, digest = _prefix_of(history, 4)

        _call_with_timeout(
            lambda: store.apply_compaction(_USER_ID, count, digest, "### R\n- a")
        )

        assert session_store[_USER_ID] is original
        assert [m.content for m in original.messages] == [
            item["content"] for item in history[4:]
        ]

    def test_clear__locked_history__does_not_deadlock_and_wipes_it(self):
        registry = UserLockRegistry()
        session_store = _make_locked_session_store(
            registry, {_USER_ID: _sample_history()}
        )
        store = _make_store(session_store, lock_registry=registry)

        finished, _ = _call_with_timeout(lambda: store.clear(_USER_ID))

        assert finished, "clear() deadlocked on the history's own lock."
        assert session_store[_USER_ID].messages == []
        assert store.get_summary(_USER_ID) is None

    def test_apply_compaction__concurrent_turn__is_not_lost(self):
        # THE P0 scenario, end to end: while the compaction holds the lock, a
        # request thread persists a turn. It must WAIT and land after the tail —
        # never inside the clear()/add_messages() window.
        registry = UserLockRegistry()
        history = _sample_history()
        session_store = _make_locked_session_store(registry, {_USER_ID: history})
        store = _make_store(session_store, lock_registry=registry)
        get_session_history = _make_get_session_history(session_store)
        count, digest = _prefix_of(history, 4)

        persisted = threading.Event()

        def _persist_turn():
            get_session_history(_USER_ID).add_messages(
                [HumanMessage(content="turno novo"), AIMessage(content="resposta nova")]
            )
            persisted.set()

        # Act — hold the user's lock exactly as apply_compaction does, start the
        # concurrent turn, then run the compaction.
        with registry.get(_USER_ID):
            writer = threading.Thread(target=_persist_turn, daemon=True)
            writer.start()
            landed_during_compaction = persisted.wait(timeout=0.3)

        assert landed_during_compaction is False, (
            "The request thread appended INSIDE the compaction's window — this "
            "is the turn the clear() would erase (plan §6.6)."
        )

        finished, applied = _call_with_timeout(
            lambda: store.apply_compaction(_USER_ID, count, digest, "### R\n- a")
        )
        writer.join(timeout=5)

        # Assert — nothing was lost: the tail plus the new turn.
        assert finished and applied is True
        contents = [m.content for m in session_store[_USER_ID].messages]
        assert "turno novo" in contents and "resposta nova" in contents
        assert contents[: len(history) - 4] == [
            item["content"] for item in history[4:]
        ]

    def test_apply_compaction__plain_in_memory_history__still_supported(self):
        # Retro-compat: a raw InMemoryChatMessageHistory (no locking) must keep
        # working — the store's unlocked-primitive path is an optimisation, not a
        # hard dependency.
        history = _sample_history()
        session_store = _make_session_store({_USER_ID: history})
        store = _make_store(session_store)
        count, digest = _prefix_of(history, 4)

        assert store.apply_compaction(_USER_ID, count, digest, "### R\n- a") is True
        assert len(session_store[_USER_ID].messages) == len(history) - 4
