"""
LockedInMemoryChatMessageHistory unit tests — Phase G / P0 (TDD RED phase).

Drives the class that does not exist yet at:

    infra/data/cache/locked_in_memory_chat_message_history.py

        class LockedInMemoryChatMessageHistory(BaseChatMessageHistory):
            def __init__(self, session_id: str,
                         lock_registry: Optional[UserLockRegistry] = None)

WHY IT MUST EXIST (security review, P0 — data loss on the DEFAULT backend)
-------------------------------------------------------------------------
`ioc._get_session_history_bundle()` hands out LangChain's RAW
`InMemoryChatMessageHistory`, which takes NO lock. Meanwhile
`InMemoryConversationContextStore.apply_compaction` runs, under the per-user
lock, a read-verify-write over that same object:

        tail = history.messages[expected_count:]
        history.clear()                 # <-- window
        history.add_messages(tail)      # <-- window

A request thread persisting a turn (`LlmAppService._persist_turn` ->
`history.add_messages([...])`) does NOT take the lock, so it can append INSIDE
that window and have its turn erased by `clear()`. That is permanent loss of a
conversation turn — exactly what plan §6.6 forbids ("never lost the history").

The Redis path is already correct (`RedisChatMessageHistory.add_messages` takes
the lock from the SAME process-wide registry the CAS uses). The in-memory path
is the asymmetric one; this class closes the gap.

Contract pinned here
--------------------
  - `add_messages()` and `clear()` run under `lock_registry.get(session_id)` —
    THE SAME lock object `InMemoryConversationContextStore.apply_compaction`
    takes for that user (two different locks serialise nothing);
  - with no registry injected it falls back to the process-wide registry
    (`infra.user_lock_registry.get_user_lock_registry()`), which is the very
    registry the store defaults to;
  - the `messages` PROPERTY must NOT take the lock — `threading.Lock` is not
    reentrant and the store re-reads `history.messages` while holding it
    (precedent: `RedisChatMessageHistory.messages`);
  - `messages` returns a SNAPSHOT (a new list), never the internal array: a
    caller (OnlyTalkGraph) that kept a live reference would otherwise observe a
    compaction mutating its list mid-turn;
  - lock-free primitives `replace_all_unlocked()` / `clear_unlocked()` exist for
    the store, which ALREADY holds the lock when it truncates — calling the
    public (locking) methods from there would deadlock on a non-reentrant Lock.

Expected RED: ImportError (module does not exist).
"""

import threading

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from infra.user_lock_registry import UserLockRegistry, get_user_lock_registry


_SESSION_ID = "user-locked-1"


# ===========================================================================
# Helpers
# ===========================================================================


def _locked_history_class():
    """
    Import the (not yet written) class. LAZY on purpose: an ImportError at module
    level would abort the WHOLE pytest session with a collection error; here each
    new test fails RED on its own while the rest of the suite still runs.
    """
    from infra.data.cache.locked_in_memory_chat_message_history import (
        LockedInMemoryChatMessageHistory,
    )

    return LockedInMemoryChatMessageHistory


def _make_registry() -> UserLockRegistry:
    """An isolated registry, so one test never blocks another."""
    return UserLockRegistry()


def _make_history(session_id: str = _SESSION_ID, lock_registry=None):
    return _locked_history_class()(
        session_id=session_id,
        lock_registry=lock_registry if lock_registry is not None else _make_registry(),
    )


def _turn(index: int) -> list[BaseMessage]:
    return [
        HumanMessage(content=f"pergunta {index}"),
        AIMessage(content=f"resposta {index}"),
    ]


def _run_in_thread(target) -> threading.Thread:
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread


class _RecordingLock:
    """A real lock that records every acquire/release made through `with`."""

    def __init__(self):
        self._lock = threading.Lock()
        self.events: list[str] = []

    def __enter__(self):
        self._lock.acquire()
        self.events.append("acquire")
        return self

    def __exit__(self, *_exc):
        self.events.append("release")
        self._lock.release()
        return False

    def locked(self) -> bool:
        return self._lock.locked()


class _RecordingRegistry:
    """A UserLockRegistry look-alike handing out `_RecordingLock`s."""

    def __init__(self):
        self._locks: dict[str, _RecordingLock] = {}

    def get(self, user_id: str) -> _RecordingLock:
        return self._locks.setdefault(user_id, _RecordingLock())

    def lock_for(self, user_id: str) -> _RecordingLock:
        return self.get(user_id)


# ===========================================================================
# TestLockedInMemoryChatMessageHistoryBehavesLikeAHistory
# ===========================================================================


class TestLockedInMemoryChatMessageHistoryBehavesLikeAHistory:
    """It is a drop-in replacement for LangChain's InMemoryChatMessageHistory."""

    def test_is_a_base_chat_message_history(self):
        # OnlyTalkGraph / LlmAppService consume it through this interface.
        assert isinstance(_make_history(), BaseChatMessageHistory)

    def test_messages__new_history__is_empty(self):
        assert _make_history().messages == []

    def test_add_messages__appends_in_order(self):
        # Arrange
        history = _make_history()
        # Act
        history.add_messages(_turn(0))
        history.add_messages(_turn(1))
        # Assert
        assert [m.content for m in history.messages] == [
            "pergunta 0",
            "resposta 0",
            "pergunta 1",
            "resposta 1",
        ]

    def test_clear__empties_the_history(self):
        # Arrange
        history = _make_history()
        history.add_messages(_turn(0))
        # Act
        history.clear()
        # Assert
        assert history.messages == []

    def test_messages__returns_a_snapshot_not_the_internal_list(self):
        # A caller that kept the live array would watch a background compaction
        # mutate it mid-turn.
        history = _make_history()
        history.add_messages(_turn(0))
        # Act
        snapshot = history.messages
        snapshot.append(HumanMessage(content="intruso"))
        # Assert
        assert [m.content for m in history.messages] == ["pergunta 0", "resposta 0"]

    def test_two_histories__do_not_share_messages(self):
        registry = _make_registry()
        first = _make_history("user-a", registry)
        second = _make_history("user-b", registry)
        first.add_messages(_turn(0))
        assert second.messages == []


# ===========================================================================
# TestLockedInMemoryChatMessageHistoryLocking — the P0 fix
# ===========================================================================


class TestLockedInMemoryChatMessageHistoryLocking:

    def test_add_messages__acquires_and_releases_the_user_lock(self):
        # Arrange — a registry handing out a lock that records its own usage.
        registry = _RecordingRegistry()
        history = _make_history(lock_registry=registry)
        # Act
        history.add_messages(_turn(0))
        # Assert — the whole append ran inside `with lock:`.
        assert registry.lock_for(_SESSION_ID).events == ["acquire", "release"]
        assert len(history.messages) == 2

    def test_clear__acquires_and_releases_the_user_lock(self):
        registry = _RecordingRegistry()
        history = _make_history(lock_registry=registry)
        history.clear()
        assert registry.lock_for(_SESSION_ID).events == ["acquire", "release"]

    def test_messages__records_no_lock_usage(self):
        registry = _RecordingRegistry()
        history = _make_history(lock_registry=registry)
        _ = history.messages
        assert registry.lock_for(_SESSION_ID).events == []

    def test_add_messages__blocks_while_the_user_lock_is_held(self):
        # THE regression this class exists for: while the compaction holds the
        # user's lock (it is mid read-verify-write over this very object), a
        # request thread persisting a turn must WAIT, not slip in and get its
        # turn wiped by the compaction's clear().
        registry = _make_registry()
        history = _make_history(lock_registry=registry)
        wrote = threading.Event()

        def _persist_turn():
            history.add_messages(_turn(9))
            wrote.set()

        # Act — simulate the compaction holding the lock.
        with registry.get(_SESSION_ID):
            worker = _run_in_thread(_persist_turn)
            appended_while_locked = wrote.wait(timeout=0.3)
            messages_while_locked = history.messages

        worker.join(timeout=5)

        # Assert
        assert appended_while_locked is False, (
            "add_messages must block while the per-user lock is held: appending "
            "inside the compaction's window is how the turn gets erased."
        )
        assert messages_while_locked == []
        assert wrote.is_set(), "add_messages must proceed once the lock is released."
        assert [m.content for m in history.messages] == ["pergunta 9", "resposta 9"]

    def test_clear__blocks_while_the_user_lock_is_held(self):
        # reset_context must not land in the middle of a compaction either.
        registry = _make_registry()
        history = _make_history(lock_registry=registry)
        history.add_messages(_turn(0))
        cleared = threading.Event()

        def _clear():
            history.clear()
            cleared.set()

        with registry.get(_SESSION_ID):
            worker = _run_in_thread(_clear)
            cleared_while_locked = cleared.wait(timeout=0.3)

        worker.join(timeout=5)

        assert cleared_while_locked is False
        assert history.messages == []

    def test_messages__does_not_acquire_the_user_lock(self):
        # Deadlock guard (precedent: RedisChatMessageHistory.messages). The store
        # re-reads `history.messages` WHILE holding the non-reentrant lock.
        registry = _make_registry()
        history = _make_history(lock_registry=registry)
        history.add_messages(_turn(0))
        read = threading.Event()
        result = []

        def _read():
            result.append(len(history.messages))
            read.set()

        with registry.get(_SESSION_ID):
            worker = _run_in_thread(_read)
            read_while_locked = read.wait(timeout=1)

        worker.join(timeout=5)

        assert read_while_locked is True, (
            "The `messages` property must NOT take the per-user lock — the "
            "compaction reads it while holding that same lock."
        )
        assert result == [2]

    def test_add_messages__does_not_deadlock_against_its_own_read(self):
        # A naive implementation that locks the property too hangs forever here.
        history = _make_history()
        done = threading.Event()

        def _write():
            history.add_messages(_turn(0))
            done.set()

        worker = _run_in_thread(_write)
        assert done.wait(timeout=5), "add_messages deadlocked against its own read."
        worker.join(timeout=5)

    def test_concurrent_writers__no_turn_is_lost(self):
        # Arrange — 8 threads persisting a turn each, on the same session.
        registry = _make_registry()
        history = _make_history(lock_registry=registry)
        barrier = threading.Barrier(8)

        def _write(index):
            def _target():
                barrier.wait()
                history.add_messages(_turn(index))

            return _target

        # Act
        workers = [_run_in_thread(_write(i)) for i in range(8)]
        for worker in workers:
            worker.join(timeout=5)

        # Assert
        assert len(history.messages) == 16


# ===========================================================================
# TestLockedInMemoryChatMessageHistorySharedRegistry (§3.5)
# ===========================================================================


class TestLockedInMemoryChatMessageHistorySharedRegistry:

    def test_takes_the_lock_of_its_own_session_id(self):
        registry = _make_registry()
        history = _make_history("user-x", registry)
        taken = []
        original_get = registry.get
        registry.get = lambda user_id: (taken.append(user_id), original_get(user_id))[1]

        history.add_messages(_turn(0))

        assert taken == ["user-x"]

    def test_no_registry_injected__uses_the_process_wide_registry(self):
        # Without this, the default (Redis-less) wiring would have the history
        # and the compaction store on DIFFERENT locks — i.e. no lock at all.
        history = _locked_history_class()(session_id="user-default")
        assert history._lock_registry is get_user_lock_registry()

    def test_two_histories_of_the_same_user__take_the_same_lock(self):
        registry = _make_registry()
        first = _make_history("user-same", registry)
        second = _make_history("user-same", registry)
        assert first._lock_registry.get("user-same") is second._lock_registry.get(
            "user-same"
        )

    def test_different_sessions__do_not_block_each_other(self):
        # Locks are per user: one user's compaction must never stall another
        # user's turn.
        registry = _make_registry()
        other = _make_history("user-other", registry)
        wrote = threading.Event()

        def _write():
            other.add_messages(_turn(0))
            wrote.set()

        with registry.get(_SESSION_ID):
            worker = _run_in_thread(_write)
            assert wrote.wait(timeout=1) is True

        worker.join(timeout=5)


# ===========================================================================
# TestLockedInMemoryChatMessageHistoryUnlockedPrimitives
# ===========================================================================


class TestLockedInMemoryChatMessageHistoryUnlockedPrimitives:
    """
    The store truncates the history while ALREADY holding the user's lock.
    `threading.Lock` is not reentrant, so it needs lock-free primitives —
    calling `clear()` / `add_messages()` from there would deadlock.
    """

    def test_replace_all_unlocked__replaces_the_whole_array(self):
        history = _make_history()
        history.add_messages(_turn(0) + _turn(1))
        history.replace_all_unlocked(_turn(1))
        assert [m.content for m in history.messages] == ["pergunta 1", "resposta 1"]

    def test_replace_all_unlocked__does_not_take_the_lock(self):
        registry = _make_registry()
        history = _make_history(lock_registry=registry)
        done = threading.Event()

        def _replace():
            history.replace_all_unlocked(_turn(0))
            done.set()

        with registry.get(_SESSION_ID):
            worker = _run_in_thread(_replace)
            replaced_under_lock = done.wait(timeout=1)

        worker.join(timeout=5)

        assert replaced_under_lock is True, (
            "replace_all_unlocked must NOT take the lock: its only caller "
            "(apply_compaction) already holds it."
        )
        assert len(history.messages) == 2

    def test_replace_all_unlocked__snapshots_the_given_list(self):
        history = _make_history()
        tail = _turn(1)
        history.replace_all_unlocked(tail)
        tail.append(HumanMessage(content="intruso"))
        assert len(history.messages) == 2

    def test_clear_unlocked__empties_without_taking_the_lock(self):
        registry = _make_registry()
        history = _make_history(lock_registry=registry)
        history.add_messages(_turn(0))
        done = threading.Event()

        def _clear():
            history.clear_unlocked()
            done.set()

        with registry.get(_SESSION_ID):
            worker = _run_in_thread(_clear)
            cleared_under_lock = done.wait(timeout=1)

        worker.join(timeout=5)

        assert cleared_under_lock is True
        assert history.messages == []
