"""
IoC graph-factory cache unit tests — Phase 1 / Change #2 (TDD RED phase).

The graph factory functions in infra/ioc.py must cache the constructed graph
instance in the shared `_repo_cache` dict (the same dict the external repository
factories already use). That dict is cleared by `_get_settings()` whenever the
os.environ snapshot changes, so a configuration change must produce a fresh graph
instance.

Contract:
  - get_main_graph / get_only_talk_graph / get_shopping_list_graph /
    get_smart_home_lights_graph / get_smart_home_climate_graph /
    get_smart_home_sensors_graph / get_smart_home_cameras_graph /
    get_music_graph / get_memory_graph
    must each return the SAME instance on repeated calls (identity).
  - After the env snapshot changes (cache invalidated), a NEW instance must be
    produced.
  - App-service factories (get_llm_app_service, ...) must NOT be cached — they
    remain per-request.

These tests are written BEFORE the implementation, so they are expected to FAIL:
today every graph factory builds a brand-new instance on each call.

External IO is avoided by patching ChatOllama and every SQLite repository class
referenced by ioc. Real graph objects are still constructed (load_prompt reads
real, already-existing prompt files and is cached by graph.py — acceptable).
`_repo_cache` and the settings cache are reset before each test for isolation.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

import infra.ioc as ioc_module


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


def _reset_ioc_caches():
    ioc_module._real_settings = None
    ioc_module._settings_cls = None
    ioc_module._settings_env_snapshot = None
    ioc_module._repo_cache.clear()


@pytest.fixture
def patched_ioc():
    """
    Patch all heavy/IO dependencies the graph factories touch so real graph
    objects can be constructed without network or DB access. Yields within a
    clean cache state and a base OLLAMA environment.
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


# ===========================================================================
# Same-instance (identity) caching per factory
# ===========================================================================


class TestGraphFactoriesAreCached:
    """Repeated calls to a graph factory must return the SAME instance."""

    def test_get_main_graph__called_twice__returns_same_instance(self, patched_ioc):
        first = ioc_module.get_main_graph()
        second = ioc_module.get_main_graph()
        assert first is second, (
            "get_main_graph() must cache its instance in _repo_cache and return "
            "the same object on repeated calls."
        )

    def test_get_only_talk_graph__called_twice__returns_same_instance(self, patched_ioc):
        first = ioc_module.get_only_talk_graph()
        second = ioc_module.get_only_talk_graph()
        assert first is second, (
            "get_only_talk_graph() must return a cached instance on repeated calls."
        )

    def test_get_smart_home_lights_graph__called_twice__returns_same_instance(
        self, patched_ioc
    ):
        first = ioc_module.get_smart_home_lights_graph()
        second = ioc_module.get_smart_home_lights_graph()
        assert first is second, (
            "get_smart_home_lights_graph() must return a cached instance on "
            "repeated calls."
        )

    def test_get_shopping_list_graph__called_twice__returns_same_instance(
        self, patched_ioc
    ):
        first = ioc_module.get_shopping_list_graph()
        second = ioc_module.get_shopping_list_graph()
        assert first is second

    def test_get_smart_home_climate_graph__called_twice__returns_same_instance(
        self, patched_ioc
    ):
        first = ioc_module.get_smart_home_climate_graph()
        second = ioc_module.get_smart_home_climate_graph()
        assert first is second

    def test_get_smart_home_sensors_graph__called_twice__returns_same_instance(
        self, patched_ioc
    ):
        first = ioc_module.get_smart_home_sensors_graph()
        second = ioc_module.get_smart_home_sensors_graph()
        assert first is second

    def test_get_smart_home_cameras_graph__called_twice__returns_same_instance(
        self, patched_ioc
    ):
        first = ioc_module.get_smart_home_cameras_graph()
        second = ioc_module.get_smart_home_cameras_graph()
        assert first is second

    def test_get_music_graph__called_twice__returns_same_instance(self, patched_ioc):
        first = ioc_module.get_music_graph()
        second = ioc_module.get_music_graph()
        assert first is second

    def test_get_memory_graph__called_twice__returns_same_instance(self, patched_ioc):
        first = ioc_module.get_memory_graph()
        second = ioc_module.get_memory_graph()
        assert first is second


# ===========================================================================
# Cache invalidation on env-snapshot change
# ===========================================================================


class TestGraphCacheInvalidation:
    """
    Changing the os.environ snapshot must invalidate the cache (via
    _get_settings() clearing _repo_cache), producing a fresh graph instance.
    """

    def test_get_main_graph__env_changed__returns_new_instance(self, patched_ioc):
        first = ioc_module.get_main_graph()

        # Mutate the environment so the snapshot hash changes; _get_settings()
        # must rebuild Settings and clear _repo_cache on the next factory call.
        with patch.dict(os.environ, {"LLM_PROVIDER_URL": "http://other-host:11434"}):
            second = ioc_module.get_main_graph()

        assert first is not second, (
            "After the env snapshot changed, get_main_graph() must return a NEW "
            "instance (cache invalidated by _get_settings())."
        )

    def test_get_smart_home_lights_graph__env_changed__returns_new_instance(
        self, patched_ioc
    ):
        first = ioc_module.get_smart_home_lights_graph()

        with patch.dict(os.environ, {"HOME_ASSISTANT_URL": "http://other-ha:8123"}):
            second = ioc_module.get_smart_home_lights_graph()

        assert first is not second, (
            "After the env snapshot changed, get_smart_home_lights_graph() must "
            "return a NEW instance."
        )


# ===========================================================================
# App-services must NOT be cached
# ===========================================================================


class TestAppServicesAreNotCached:
    """
    App-service factories must remain per-request: two calls must return two
    DIFFERENT instances even with no env change.
    """

    def test_get_llm_app_service__called_twice__returns_different_instances(
        self, patched_ioc
    ):
        first = ioc_module.get_llm_app_service()
        second = ioc_module.get_llm_app_service()
        assert first is not second, (
            "get_llm_app_service() must NOT be cached — app-services stay "
            "per-request. Two calls must yield two distinct instances."
        )
