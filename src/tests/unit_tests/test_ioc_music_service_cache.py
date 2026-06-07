"""
IoC get_music_service caching unit tests — Change #8 / Contract B (TDD RED).

Desired contract:
  - `get_music_service()` in infra/ioc.py must cache its instance in the shared
    `_repo_cache` dict (like the graph and repository factories), returning the
    SAME MusicService instance on repeated calls.
  - When the os.environ snapshot changes, `_get_settings()` clears `_repo_cache`,
    so the next call must return a NEW instance.

These tests are written BEFORE the implementation and are expected to FAIL today,
because `get_music_service()` builds a brand-new MusicService on every call.

External IO is avoided by patching `infra.ioc.Settings` and the
`MusicAssistantMusicRepository` class. `_repo_cache` and the settings cache are
reset before each test for isolation.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

import infra.ioc as ioc_module


_BASE_ENV = {
    "MUSIC_ASSISTANT_URL": "http://ma-host:8095",
    "MUSIC_ASSISTANT_TOKEN": "",
}


def _reset_ioc_caches():
    ioc_module._real_settings = None
    ioc_module._settings_cls = None
    ioc_module._settings_env_snapshot = None
    ioc_module._repo_cache.clear()


def _make_settings(url="http://ma-host:8095", token=""):
    """A lightweight stand-in for Settings exposing only the music fields used."""
    settings = MagicMock()
    settings.music_assistant_url = url
    settings.music_assistant_token = token
    return settings


@pytest.fixture
def patched_ioc():
    """
    Patch Settings and the music repository class so get_music_service can build
    real MusicService objects without network/DB access. Yields within a clean
    cache state and a base music environment.
    """
    settings_factory = MagicMock(side_effect=lambda: _make_settings())
    patches = [
        patch.dict(os.environ, _BASE_ENV, clear=True),
        patch("infra.ioc.Settings", settings_factory),
        patch("infra.ioc.MusicAssistantMusicRepository", MagicMock()),
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
# Same-instance (identity) caching
# ===========================================================================


class TestMusicServiceFactoryIsCached:
    def test_get_music_service__called_twice__returns_same_instance(self, patched_ioc):
        first = ioc_module.get_music_service()
        second = ioc_module.get_music_service()
        assert first is second, (
            "get_music_service() must cache its instance in _repo_cache and "
            "return the same object on repeated calls."
        )


# ===========================================================================
# Cache invalidation on env-snapshot change
# ===========================================================================


class TestMusicServiceCacheInvalidation:
    def test_get_music_service__env_changed__returns_new_instance(self, patched_ioc):
        first = ioc_module.get_music_service()

        # Mutate the environment so the snapshot hash changes; _get_settings()
        # must rebuild Settings and clear _repo_cache on the next factory call.
        with patch.dict(os.environ, {"MUSIC_ASSISTANT_URL": "http://other-ma:8095"}):
            second = ioc_module.get_music_service()

        assert first is not second, (
            "After the env snapshot changed, get_music_service() must return a "
            "NEW instance (cache invalidated by _get_settings())."
        )
