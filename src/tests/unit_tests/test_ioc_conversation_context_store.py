"""
IoC wiring for the conversation context store Unit Tests (TDD - RED phase, Fase E/F8).

Target contract (plan §3.1, §3.2, §9 Fase E):

  - `get_conversation_context_store()`:
      * CACHE_DB_CONNECTION_STRING set   → RedisConversationContextStore, over the
        SAME cached ContextRepository `get_context_repository()` hands out, with
        the chat-history TTL.
      * unset                            → InMemoryConversationContextStore.
      * cached in `_repo_cache` (a singleton): the in-memory backend keeps the
        summaries in its own dict — a per-request instance would forget every
        summary it ever wrote.

  - CRITICAL — the in-memory store must share the VERY dict
    `_get_session_history_factory()` closes over. Today that factory is NOT
    memoized: each call returns a fresh closure over a BRAND-NEW dict, so
    `OnlyTalkGraph` and `LlmAppService` already read/write DIFFERENT in-memory
    histories (latent bug). Compaction makes it fatal: the store would truncate a
    history nobody reads. These tests REQUIRE the memoization.

  - `RedisChatMessageHistory` (history) and `RedisConversationContextStore` (CAS)
    must draw their per-user locks from the SAME registry
    (`infra.user_lock_registry.get_user_lock_registry()`), otherwise a compaction
    can clobber a turn appended meanwhile (§3.5).

  - `get_context_compaction_app_service()` exists, is cached, and is wired with
    the summary graph, the user repository, the store and the four compaction
    thresholds from Settings.

  - `get_only_talk_graph()` and `get_llm_app_service()` pass the store along.

Expected to FAIL until ioc gains get_conversation_context_store /
get_context_compaction_app_service and memoizes _get_session_history_factory:
    ImportError / AttributeError: module 'infra.ioc' has no attribute
    'get_conversation_context_store'.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

import infra.ioc as ioc_module
from application.appservices.context_compaction_app_service import (
    ContextCompactionAppService,
)
from domain.services.conversation_digest import conversation_digest
from infra.data.cache.in_memory_conversation_context_store import (
    InMemoryConversationContextStore,
)
from infra.data.external.redis.redis_conversation_context_store import (
    RedisConversationContextStore,
)
from infra.user_lock_registry import get_user_lock_registry


_BASE_ENV = {
    "LLM_PROVIDER_TYPE": "OLLAMA",
    "LLM_PROVIDER_URL": "http://ollama-host:11434",
    "LLM_PROVIDER_API_KEY": "",
    "PERUCA_DB_CONNECTION_STRING": "sqlite:///tmp/test.db",
    "HOME_ASSISTANT_URL": "http://ha-host:8123",
    "HOME_ASSISTANT_TOKEN": "test-token",
    "MUSIC_ASSISTANT_URL": "http://ma-host:8095",
    "MUSIC_ASSISTANT_TOKEN": "",
    "CACHE_DB_CONNECTION_STRING": "",
}

_REDIS_ENV = {"CACHE_DB_CONNECTION_STRING": "redis://localhost:6379/0"}


def _reset_ioc_caches():
    ioc_module._real_settings = None
    ioc_module._settings_cls = None
    ioc_module._settings_env_snapshot = None
    ioc_module._repo_cache.clear()


@pytest.fixture
def patched_ioc():
    """
    Patch every heavy/IO dependency the factories touch so real objects can be
    constructed without network or DB access, on a clean cache state and a base
    (in-memory cache) OLLAMA environment.
    """
    patches = [
        patch.dict(os.environ, _BASE_ENV, clear=True),
        patch("infra.ioc.ChatOllama", MagicMock()),
        patch("infra.ioc.ChatOpenAI", MagicMock()),
        patch("infra.ioc.SqliteUserRepository", MagicMock()),
        patch("infra.ioc.SqliteUserMemoryRepository", MagicMock()),
        patch("infra.ioc.SqliteShoppingListRepository", MagicMock()),
        patch("infra.ioc.SqliteSmartHomeEntityAliasRepository", MagicMock()),
        patch("infra.ioc.SqliteSmartHomeAreaRepository", MagicMock()),
        patch("infra.ioc.SqliteVehicleRepository", MagicMock()),
        patch("infra.ioc.SqliteMaintenanceRecordRepository", MagicMock()),
        patch("infra.ioc.SqlitePetRepository", MagicMock()),
        patch("infra.ioc.SqlitePetHealthEventRepository", MagicMock()),
        patch("infra.ioc.HomeAssistantSmartHomeConfigurationRepository", MagicMock()),
        patch("infra.ioc.HomeAssistantSmartHomeLightRepository", MagicMock()),
        patch("infra.ioc.HomeAssistantSmartHomeClimateRepository", MagicMock()),
        patch("infra.ioc.HomeAssistantSmartHomeSensorRepository", MagicMock()),
        patch("infra.ioc.HomeAssistantSmartHomeCameraRepository", MagicMock()),
        patch("infra.ioc.MusicAssistantMusicRepository", MagicMock()),
        patch("infra.ioc.RedisContextRepository", MagicMock()),
    ]
    for p in patches:
        p.start()
    _reset_ioc_caches()
    try:
        yield
    finally:
        _reset_ioc_caches()
        for p in reversed(patches):
            p.stop()


def _turn(index):
    return [HumanMessage(content=f"pergunta {index}"), AIMessage(content=f"resposta {index}")]


# ===========================================================================
# TestGetConversationContextStore
# ===========================================================================


class TestGetConversationContextStore:
    def test_with_redis_configured__returns_redis_store(self, patched_ioc):
        with patch.dict(os.environ, _REDIS_ENV):
            store = ioc_module.get_conversation_context_store()
        assert isinstance(store, RedisConversationContextStore)

    def test_with_redis_configured__shares_the_cached_context_repository(
        self, patched_ioc
    ):
        # The history writer and the CAS must talk to the SAME Redis client
        # wrapper (the one get_context_repository caches).
        with patch.dict(os.environ, _REDIS_ENV):
            store = ioc_module.get_conversation_context_store()
            assert store._repo is ioc_module.get_context_repository()

    def test_with_redis_configured__uses_the_chat_history_ttl(self, patched_ioc):
        # Summary and history expire together (§3.3).
        env = dict(_REDIS_ENV, CHAT_HISTORY_TTL_SECONDS="3600")
        with patch.dict(os.environ, env):
            store = ioc_module.get_conversation_context_store()
        assert store._ttl == 3600

    def test_without_redis__returns_in_memory_store(self, patched_ioc):
        store = ioc_module.get_conversation_context_store()
        assert isinstance(store, InMemoryConversationContextStore)

    def test_called_twice__returns_the_same_instance(self, patched_ioc):
        # Must be cached: the in-memory backend holds the summaries in its own
        # dict, so a per-request instance would lose every summary it wrote.
        assert (
            ioc_module.get_conversation_context_store()
            is ioc_module.get_conversation_context_store()
        )

    def test_cached_in_repo_cache__cleared_when_the_env_changes(self, patched_ioc):
        first = ioc_module.get_conversation_context_store()
        with patch.dict(os.environ, _REDIS_ENV):
            second = ioc_module.get_conversation_context_store()
        assert first is not second


# ===========================================================================
# TestSessionHistoryFactoryIsMemoized
# ===========================================================================


class TestSessionHistoryFactoryIsMemoized:
    """
    `_get_session_history_factory()` is called by several factories
    (get_only_talk_graph, get_llm_app_service, get_pet_health_graph, ...). While
    it builds a new closure over a new dict on every call, each of those holds a
    DIFFERENT in-memory history — and the compaction store would truncate a dict
    nobody reads.
    """

    def test_called_twice__returns_the_same_factory(self, patched_ioc):
        assert (
            ioc_module._get_session_history_factory()
            is ioc_module._get_session_history_factory()
        )

    def test_in_memory__two_calls_share_the_same_history_object(self, patched_ioc):
        # Arrange
        first = ioc_module._get_session_history_factory()
        second = ioc_module._get_session_history_factory()
        # Act
        first("user-1").add_messages(_turn(0))
        # Assert — same user, same history.
        assert second("user-1") is first("user-1")
        assert len(second("user-1").messages) == 2

    def test_env_change__produces_a_new_factory(self, patched_ioc):
        # The memoization must live in _repo_cache (cleared on env change), not
        # in a module global that outlives a reconfiguration.
        first = ioc_module._get_session_history_factory()
        with patch.dict(os.environ, _REDIS_ENV):
            second = ioc_module._get_session_history_factory()
        assert first is not second


# ===========================================================================
# TestInMemoryStoreSharesTheSessionHistoryDict
# ===========================================================================


class TestInMemoryStoreSharesTheSessionHistoryDict:
    def test_message_written_via_session_history__is_read_by_the_store(
        self, patched_ioc
    ):
        # Arrange
        get_session_history = ioc_module._get_session_history_factory()
        store = ioc_module.get_conversation_context_store()
        # Act
        get_session_history("user-1").add_messages(_turn(0))
        # Assert
        assert store.read_history("user-1") == [
            {"type": "human", "content": "pergunta 0"},
            {"type": "ai", "content": "resposta 0"},
        ]

    def test_apply_compaction__truncates_what_session_history_returns(
        self, patched_ioc
    ):
        # Arrange — 3 turns (6 messages) written through the session history.
        get_session_history = ioc_module._get_session_history_factory()
        store = ioc_module.get_conversation_context_store()
        for i in range(3):
            get_session_history("user-1").add_messages(_turn(i))
        serialized = store.read_history("user-1")
        assert len(serialized) == 6  # guard: the store sees the same array
        digest = conversation_digest(serialized[:4])
        # Act — compact the first 2 turns.
        applied = store.apply_compaction("user-1", 4, digest, "### Assuntos\n- x")
        # Assert — the very object OnlyTalkGraph reads must have shrunk.
        assert applied is True
        remaining = get_session_history("user-1").messages
        assert [m.content for m in remaining] == ["pergunta 2", "resposta 2"]
        assert store.get_summary("user-1")["summary"] == "### Assuntos\n- x"

    def test_store_clear__wipes_the_session_history_too(self, patched_ioc):
        # Arrange
        get_session_history = ioc_module._get_session_history_factory()
        store = ioc_module.get_conversation_context_store()
        get_session_history("user-1").add_messages(_turn(0))
        # Act
        store.clear("user-1")
        # Assert — this is what reset_context relies on (§6.3).
        assert get_session_history("user-1").messages == []
        assert store.get_summary("user-1") is None


# ===========================================================================
# TestRedisHistoryAndStoreShareTheLockRegistry (§3.5)
# ===========================================================================


class TestRedisHistoryAndStoreShareTheLockRegistry:
    def test_history_and_store__use_the_same_lock_registry(self, patched_ioc):
        # Arrange
        with patch.dict(os.environ, _REDIS_ENV):
            history = ioc_module._get_session_history_factory()("user-1")
            store = ioc_module.get_conversation_context_store()
        # Assert — a per-object registry would serialise nothing between the
        # appending writer and the compacting CAS.
        assert history._lock_registry is store._lock_registry

    def test_history_and_store__use_the_process_wide_registry(self, patched_ioc):
        # Arrange
        with patch.dict(os.environ, _REDIS_ENV):
            history = ioc_module._get_session_history_factory()("user-1")
            store = ioc_module.get_conversation_context_store()
        # Assert
        registry = get_user_lock_registry()
        assert history._lock_registry is registry
        assert store._lock_registry is registry

    def test_same_user__history_and_store_get_the_same_lock(self, patched_ioc):
        # Arrange
        with patch.dict(os.environ, _REDIS_ENV):
            history = ioc_module._get_session_history_factory()("user-1")
            store = ioc_module.get_conversation_context_store()
        # Assert
        assert history._lock_registry.get("user-1") is store._lock_registry.get(
            "user-1"
        )


# ===========================================================================
# TestGetContextCompactionAppService
# ===========================================================================


class TestGetContextCompactionAppService:
    def test_returns_a_context_compaction_app_service(self, patched_ioc):
        assert isinstance(
            ioc_module.get_context_compaction_app_service(),
            ContextCompactionAppService,
        )

    def test_called_twice__returns_the_same_instance(self, patched_ioc):
        # Cached in _repo_cache like the graphs (it is a stateless orchestrator
        # over cached collaborators; rebuilding it per request is pure waste).
        assert (
            ioc_module.get_context_compaction_app_service()
            is ioc_module.get_context_compaction_app_service()
        )

    def test_wired_with_the_context_summary_graph(self, patched_ioc):
        service = ioc_module.get_context_compaction_app_service()
        assert service.context_summary_graph is ioc_module.get_context_summary_graph()

    def test_wired_with_the_user_repository(self, patched_ioc):
        service = ioc_module.get_context_compaction_app_service()
        assert service.user_repository is ioc_module.get_user_repository()

    def test_wired_with_the_conversation_context_store(self, patched_ioc):
        service = ioc_module.get_context_compaction_app_service()
        assert service.store is ioc_module.get_conversation_context_store()

    def test_uses_the_default_thresholds_from_settings(self, patched_ioc):
        service = ioc_module.get_context_compaction_app_service()
        assert service.enabled is True
        assert service.trigger_messages == 30
        assert service.trigger_chars == 24_000
        assert service.keep_tail_messages == 16

    def test_thresholds_come_from_the_environment(self, patched_ioc):
        env = {
            "CHAT_COMPACTION_ENABLED": "false",
            "CHAT_COMPACTION_TRIGGER_MESSAGES": "8",
            "CHAT_COMPACTION_TRIGGER_CHARS": "999",
            "CHAT_COMPACTION_KEEP_TAIL_MESSAGES": "4",
        }
        with patch.dict(os.environ, env):
            service = ioc_module.get_context_compaction_app_service()
        assert service.enabled is False
        assert service.trigger_messages == 8
        assert service.trigger_chars == 999
        assert service.keep_tail_messages == 4


# ===========================================================================
# TestStoreIsPassedToTheConsumers
# ===========================================================================


class TestStoreIsPassedToTheConsumers:
    def test_only_talk_graph__receives_the_store(self, patched_ioc):
        graph = ioc_module.get_only_talk_graph()
        assert (
            graph._conversation_context_store
            is ioc_module.get_conversation_context_store()
        )

    def test_llm_app_service__receives_the_store(self, patched_ioc):
        service = ioc_module.get_llm_app_service()
        assert (
            service.conversation_context_store
            is ioc_module.get_conversation_context_store()
        )

    def test_only_talk_graph_and_llm_app_service__share_the_same_store(
        self, patched_ioc
    ):
        # reset_context (LlmAppService) must clear the very summary
        # OnlyTalkGraph would read back on the next turn.
        graph = ioc_module.get_only_talk_graph()
        service = ioc_module.get_llm_app_service()
        assert graph._conversation_context_store is service.conversation_context_store

    def test_only_talk_graph_and_llm_app_service__share_the_session_history(
        self, patched_ioc
    ):
        # In-memory backend: the graph reads the history LlmAppService writes.
        graph = ioc_module.get_only_talk_graph()
        service = ioc_module.get_llm_app_service()
        assert graph._get_session_history is service.get_session_history


# ===========================================================================
# Phase G / P0 — the in-memory session history must take the per-user lock
# ===========================================================================
#
# Security review, P0 (data loss on the DEFAULT backend): `_get_session_history_bundle()`
# returns LangChain's RAW `InMemoryChatMessageHistory`, which takes NO lock, while
# `InMemoryConversationContextStore.apply_compaction` rewrites that very object under
# the per-user lock (`tail = messages[n:]` -> `clear()` -> `add_messages(tail)`).
# A request thread appending a turn (`LlmAppService._persist_turn`) can land inside
# that window and be erased by the `clear()` — permanent loss (plan §6.6 forbids it).
#
# The Redis branch is already symmetric (RedisChatMessageHistory.add_messages takes the
# lock from the same process-wide registry). These tests pin the in-memory branch:
#
#   1. the factory returns a `LockedInMemoryChatMessageHistory` drawing its lock from
#      the SAME registry the store uses (`get_user_lock_registry()`);
#   2. a write through the factory BLOCKS while that lock is held (i.e. while a
#      compaction is in flight);
#   3. the CREATION of `history_store[session_id]` is race-free — two threads racing
#      on a cold session must not end up with two different history objects (one of
#      them holding a turn nobody will ever read again).

import threading  # noqa: E402
import time  # noqa: E402

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


class TestInMemorySessionHistoryIsLocked:
    def test_in_memory__factory_returns_a_locked_history(self, patched_ioc):
        history = ioc_module._get_session_history_factory()("user-1")
        assert isinstance(history, _locked_history_class()), (
            "The in-memory branch must hand out a LockedInMemoryChatMessageHistory: "
            "the raw InMemoryChatMessageHistory takes no lock, so a compaction can "
            "erase a turn appended concurrently."
        )

    def test_in_memory__history_and_store_share_the_lock_registry(self, patched_ioc):
        history = ioc_module._get_session_history_factory()("user-1")
        store = ioc_module.get_conversation_context_store()
        assert history._lock_registry is store._lock_registry

    def test_in_memory__history_uses_the_process_wide_registry(self, patched_ioc):
        history = ioc_module._get_session_history_factory()("user-1")
        assert history._lock_registry is get_user_lock_registry()

    def test_in_memory__same_user__history_and_store_get_the_same_lock(
        self, patched_ioc
    ):
        history = ioc_module._get_session_history_factory()("user-1")
        store = ioc_module.get_conversation_context_store()
        assert history._lock_registry.get("user-1") is store._lock_registry.get(
            "user-1"
        )

    def test_in_memory__persisting_a_turn_blocks_while_the_user_lock_is_held(
        self, patched_ioc
    ):
        # The lock below is exactly the one apply_compaction holds while it
        # truncates. `_persist_turn` must wait for it.
        get_session_history = ioc_module._get_session_history_factory()
        store = ioc_module.get_conversation_context_store()
        lock = store._lock_registry.get("user-1")
        persisted = threading.Event()

        def _persist_turn():
            get_session_history("user-1").add_messages(_turn(0))
            persisted.set()

        with lock:
            worker = threading.Thread(target=_persist_turn, daemon=True)
            worker.start()
            landed_under_lock = persisted.wait(timeout=0.3)

        worker.join(timeout=5)

        assert landed_under_lock is False, (
            "A turn persisted while the compaction holds the user's lock lands "
            "inside the clear()/add_messages() window and is lost."
        )
        assert persisted.is_set()
        assert len(get_session_history("user-1").messages) == 2


class TestInMemorySessionHistoryCreationIsRaceFree:
    """
    `history_store[session_id]` is created lazily on first access. With a plain
    check-then-set, two threads racing on a cold session each build their OWN
    history: the loser's object (and the turn written into it) is dropped from
    the dict — a silently lost turn, and a store/graph reading a different array.
    """

    @staticmethod
    def _slow_locked_history(*args, **kwargs):
        # Widen the creation window so the race is deterministic.
        time.sleep(0.05)
        return _locked_history_class()(*args, **kwargs)

    def test_concurrent_first_access__every_thread_gets_the_same_object(
        self, patched_ioc
    ):
        get_session_history = ioc_module._get_session_history_factory()
        barrier = threading.Barrier(8)
        results: list = []

        def _worker():
            barrier.wait()
            results.append(get_session_history("user-race"))

        with patch(
            "infra.ioc.LockedInMemoryChatMessageHistory",
            side_effect=self._slow_locked_history,
        ):
            workers = [threading.Thread(target=_worker, daemon=True) for _ in range(8)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=5)

        assert len(results) == 8
        assert all(history is results[0] for history in results), (
            "Two threads created two histories for the same session: the turn "
            "written into the loser's object is lost."
        )

    def test_concurrent_first_write__no_turn_is_lost(self, patched_ioc):
        get_session_history = ioc_module._get_session_history_factory()
        barrier = threading.Barrier(2)

        def _worker(index):
            def _target():
                barrier.wait()
                get_session_history("user-race").add_messages(_turn(index))

            return _target

        with patch(
            "infra.ioc.LockedInMemoryChatMessageHistory",
            side_effect=self._slow_locked_history,
        ):
            workers = [
                threading.Thread(target=_worker(i), daemon=True) for i in range(2)
            ]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=5)

        assert len(get_session_history("user-race").messages) == 4, (
            "A turn was lost in the history-creation window (two threads created "
            "two different histories for the same session)."
        )

    def test_store_sees_the_history_created_by_a_concurrent_factory_call(
        self, patched_ioc
    ):
        # The compaction store reads `history_store[user_id]` directly: it must
        # find the very object the racing threads ended up writing into.
        get_session_history = ioc_module._get_session_history_factory()
        store = ioc_module.get_conversation_context_store()

        with patch(
            "infra.ioc.LockedInMemoryChatMessageHistory",
            side_effect=self._slow_locked_history,
        ):
            worker = threading.Thread(
                target=lambda: get_session_history("user-race").add_messages(_turn(0)),
                daemon=True,
            )
            worker.start()
            get_session_history("user-race").add_messages(_turn(1))
            worker.join(timeout=5)

        assert len(store.read_history("user-race")) == 4
