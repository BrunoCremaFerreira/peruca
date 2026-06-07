"""
IoC SQLite repository-factory cache unit tests (TDD RED phase).

Contract:
  - get_user_repository / get_user_memory_repository /
    get_shopping_list_repository / get_smart_home_entity_alias_repository /
    get_smart_home_area_repository must each return the SAME instance on
    repeated calls within the same env snapshot (identity check).
  - When os.environ changes (snapshot hash differs), _get_settings() clears
    _repo_cache, so the next factory call must return a NEW instance.

These tests are written BEFORE the implementation and are expected to FAIL:
today every SQLite repository factory builds a brand-new instance on each call
because none of them consult _repo_cache.

External IO is avoided by patching all SQLite repository classes (and every
other heavy dependency ioc.py imports) so no real DB file is touched.
_repo_cache and the settings caches are reset before and after each test for
full isolation.
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


def _factory_mock():
    """
    Return a MagicMock class whose each call produces a NEW MagicMock instance.
    This is essential for testing caching: without this, MagicMock() always
    returns the same `return_value` sentinel, making uncached factories appear
    to be cached (false positive).
    """
    cls = MagicMock()
    cls.side_effect = lambda *a, **kw: MagicMock()
    return cls


@pytest.fixture
def patched_ioc():
    """
    Patch all SQLite repositories and other heavy/IO dependencies so factory
    functions can be exercised without touching the filesystem or network.
    Each SQLite class mock uses side_effect so that every instantiation returns
    a DISTINCT object — this is what makes identity assertions meaningful.
    Yields within a clean cache state and a base OLLAMA environment.
    """
    patches = [
        patch.dict(os.environ, _BASE_ENV, clear=True),
        patch("infra.ioc.ChatOllama", _factory_mock()),
        patch("infra.ioc.ChatOpenAI", _factory_mock()),
        patch("infra.ioc.SqliteUserRepository", _factory_mock()),
        patch("infra.ioc.SqliteUserMemoryRepository", _factory_mock()),
        patch("infra.ioc.SqliteShoppingListRepository", _factory_mock()),
        patch("infra.ioc.SqliteSmartHomeEntityAliasRepository", _factory_mock()),
        patch("infra.ioc.SqliteSmartHomeAreaRepository", _factory_mock()),
        patch("infra.ioc.HomeAssistantSmartHomeConfigurationRepository", _factory_mock()),
        patch("infra.ioc.HomeAssistantSmartHomeLightRepository", _factory_mock()),
        patch("infra.ioc.HomeAssistantSmartHomeClimateRepository", _factory_mock()),
        patch("infra.ioc.HomeAssistantSmartHomeSensorRepository", _factory_mock()),
        patch("infra.ioc.HomeAssistantSmartHomeCameraRepository", _factory_mock()),
        patch("infra.ioc.MusicAssistantMusicRepository", _factory_mock()),
        patch("infra.ioc.RedisContextRepository", _factory_mock()),
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


class TestSqliteRepositoryFactoriesAreCached:
    """Repeated calls to a SQLite repository factory must return the SAME instance."""

    def test_get_user_repository__called_twice__returns_same_instance(
        self, patched_ioc
    ):
        first = ioc_module.get_user_repository()
        second = ioc_module.get_user_repository()
        assert first is second, (
            "get_user_repository() must cache its instance in _repo_cache and "
            "return the same object on repeated calls."
        )

    def test_get_user_memory_repository__called_twice__returns_same_instance(
        self, patched_ioc
    ):
        first = ioc_module.get_user_memory_repository()
        second = ioc_module.get_user_memory_repository()
        assert first is second, (
            "get_user_memory_repository() must cache its instance in _repo_cache "
            "and return the same object on repeated calls."
        )

    def test_get_shopping_list_repository__called_twice__returns_same_instance(
        self, patched_ioc
    ):
        first = ioc_module.get_shopping_list_repository()
        second = ioc_module.get_shopping_list_repository()
        assert first is second, (
            "get_shopping_list_repository() must cache its instance in _repo_cache "
            "and return the same object on repeated calls."
        )

    def test_get_smart_home_entity_alias_repository__called_twice__returns_same_instance(
        self, patched_ioc
    ):
        first = ioc_module.get_smart_home_entity_alias_repository()
        second = ioc_module.get_smart_home_entity_alias_repository()
        assert first is second, (
            "get_smart_home_entity_alias_repository() must cache its instance in "
            "_repo_cache and return the same object on repeated calls."
        )

    def test_get_smart_home_area_repository__called_twice__returns_same_instance(
        self, patched_ioc
    ):
        first = ioc_module.get_smart_home_area_repository()
        second = ioc_module.get_smart_home_area_repository()
        assert first is second, (
            "get_smart_home_area_repository() must cache its instance in "
            "_repo_cache and return the same object on repeated calls."
        )


# ===========================================================================
# Cache invalidation on env-snapshot change
# ===========================================================================


class TestSqliteRepositoryCacheInvalidation:
    """
    When os.environ changes, _get_settings() must clear _repo_cache, so the
    next factory call must return a NEW instance (not the stale cached one).
    """

    def test_get_user_repository__env_changed__returns_new_instance(
        self, patched_ioc
    ):
        first = ioc_module.get_user_repository()

        # Mutate the environment so the snapshot hash changes; _get_settings()
        # must rebuild Settings and clear _repo_cache on the next factory call.
        with patch.dict(
            os.environ, {"PERUCA_DB_CONNECTION_STRING": "sqlite:///tmp/other.db"}
        ):
            second = ioc_module.get_user_repository()

        assert first is not second, (
            "After the env snapshot changed, get_user_repository() must return a "
            "NEW instance (cache invalidated by _get_settings())."
        )

    def test_get_shopping_list_repository__env_changed__returns_new_instance(
        self, patched_ioc
    ):
        first = ioc_module.get_shopping_list_repository()

        with patch.dict(
            os.environ, {"PERUCA_DB_CONNECTION_STRING": "sqlite:///tmp/other.db"}
        ):
            second = ioc_module.get_shopping_list_repository()

        assert first is not second, (
            "After the env snapshot changed, get_shopping_list_repository() must "
            "return a NEW instance (cache invalidated by _get_settings())."
        )
