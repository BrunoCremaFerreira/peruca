"""
Performance Optimization Unit Tests — Milestone 3 (TDD RED phase)

Three infrastructure fixes that must not alter any business behaviour.
All tests are written BEFORE the implementation exists and are expected to
FAIL with the current codebase, producing clear assertion errors (not import
errors or tracebacks).

3.1 — aiohttp session reuse in HTTP adapters
    Each HTTP adapter (HomeAssistant REST and MusicAssistant) currently opens
    a fresh aiohttp.ClientSession on every request.  The fix introduces a
    lazy _get_session() method that creates the session once and reuses it,
    and makes the IoC factory functions return a singleton per adapter type.

3.2 — WebSocket timeout configuration
    websockets.connect() in HomeAssistantSmartHomeConfigurationRepository is
    called without ping_interval / ping_timeout / close_timeout.  The fix
    passes explicit values for all three parameters.

3.3 — RedisContextRepository lazy connection
    RedisContextRepository.__init__ declares `self._client: Redis` as a type
    annotation only; `connect()` is never called automatically, so any call to
    set_key / get_key / delete_key raises AttributeError.  The fix adds lazy
    connection initialisation so that _client is ready before the first use.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Base environment — satisfies Settings() validation for all tests
# ---------------------------------------------------------------------------

_BASE_ENV = {
    "LLM_PROVIDER_TYPE": "OLLAMA",
    "LLM_PROVIDER_URL": "http://ollama-host:11434",
    "LLM_PROVIDER_API_KEY": "",
    "PERUCA_DB_CONNECTION_STRING": "/tmp/test_m3.db",
    "HOME_ASSISTANT_URL": "http://ha-host:8123",
    "HOME_ASSISTANT_TOKEN": "test-token",
    "MUSIC_ASSISTANT_URL": "http://ma-host:8095",
    "MUSIC_ASSISTANT_TOKEN": "",
    "CACHE_DB_CONNECTION_STRING": "redis://localhost:6379/0",
}


# ===========================================================================
# 3.1 — IoC singleton: same instance returned on consecutive factory calls
# ===========================================================================


class TestIocSingletonRepositories:
    """
    Verify that the HTTP-adapter factory functions in infra/ioc.py return the
    same object instance on consecutive calls within the same process run.

    RED: currently each factory call constructs and returns a brand-new
         repository instance, making session reuse impossible at the IoC level.
    GREEN: after the fix, a module-level registry (e.g. dict or per-factory
           variable) caches the first instance and returns it on subsequent
           calls.
    """

    def test_get_smart_home_light_repository__called_twice__returns_same_instance(self):
        """
        Two consecutive calls to get_smart_home_light_repository() must return
        the identical object (is-check), not two separate instances.

        FAILS today because the factory always calls
        HomeAssistantSmartHomeLightRepository(...) and returns a new object.
        """
        import infra.ioc as ioc_module

        with patch.dict(os.environ, _BASE_ENV):
            first = ioc_module.get_smart_home_light_repository()
            second = ioc_module.get_smart_home_light_repository()

        assert first is second, (
            "get_smart_home_light_repository() must return the same singleton "
            "instance on consecutive calls. Currently a new object is created "
            "on every call, preventing aiohttp session reuse."
        )

    def test_get_smart_home_climate_repository__called_twice__returns_same_instance(self):
        """
        Two consecutive calls to get_smart_home_climate_repository() must
        return the same object.

        FAILS today for the same reason as the lights repository factory.
        """
        import infra.ioc as ioc_module

        with patch.dict(os.environ, _BASE_ENV):
            first = ioc_module.get_smart_home_climate_repository()
            second = ioc_module.get_smart_home_climate_repository()

        assert first is second, (
            "get_smart_home_climate_repository() must return the same singleton "
            "instance on consecutive calls."
        )

    def test_get_music_repository__called_twice__returns_same_instance(self):
        """
        Two consecutive calls to get_music_repository() must return the same
        MusicAssistantMusicRepository instance.

        FAILS today because get_music_repository() constructs a new
        MusicAssistantMusicRepository on every invocation.
        """
        import infra.ioc as ioc_module

        with patch.dict(os.environ, _BASE_ENV):
            first = ioc_module.get_music_repository()
            second = ioc_module.get_music_repository()

        assert first is second, (
            "get_music_repository() must return the same singleton instance on "
            "consecutive calls. Currently a new object is created on every call."
        )

    def test_get_smart_home_light_repository__env_unchanged__constructor_called_once(self):
        """
        When the environment does not change between calls, the underlying
        HomeAssistantSmartHomeLightRepository constructor must be invoked
        exactly once across two factory calls.

        FAILS today because the factory calls the constructor on every
        invocation.
        """
        import infra.ioc as ioc_module

        with patch.dict(os.environ, _BASE_ENV), patch(
            "infra.ioc.HomeAssistantSmartHomeLightRepository"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            ioc_module.get_smart_home_light_repository()
            ioc_module.get_smart_home_light_repository()

        assert mock_cls.call_count == 1, (
            f"HomeAssistantSmartHomeLightRepository was constructed "
            f"{mock_cls.call_count} time(s). Expected exactly 1 construction "
            "when the environment does not change between factory calls."
        )


# ===========================================================================
# 3.1 — Adapter session reuse: _get_session() / _session attribute
# ===========================================================================


class TestAdapterSessionReuse:
    """
    Verify that each HTTP adapter exposes a _get_session() method (or a
    _session attribute) that enables internal session reuse.

    The IoC singleton (previous class) handles process-level reuse; this class
    verifies the per-instance pattern that allows the adapter itself to reuse
    one session across multiple method calls on the same instance.

    RED: none of the adapters currently have _get_session() or _session.
    GREEN: after the fix, _get_session() returns a cached aiohttp.ClientSession.
    """

    def test_light_repository__has_get_session_method_or_session_attr__session_reuse_pattern_exists(self):
        """
        HomeAssistantSmartHomeLightRepository must expose either a _get_session
        callable or a _session attribute that holds a reusable ClientSession.

        FAILS today because the adapter creates sessions with `async with
        aiohttp.ClientSession()` inside each method — no reuse mechanism exists.
        """
        from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_light_repository import (
            HomeAssistantSmartHomeLightRepository,
        )

        repo = HomeAssistantSmartHomeLightRepository(
            base_url="http://ha:8123", token="tok"
        )

        has_pattern = hasattr(repo, "_get_session") or hasattr(repo, "_session")
        assert has_pattern, (
            "HomeAssistantSmartHomeLightRepository must expose either a "
            "_get_session() method or a _session attribute for session reuse. "
            "Currently every HTTP method opens a fresh aiohttp.ClientSession."
        )

    def test_climate_repository__has_get_session_method_or_session_attr__session_reuse_pattern_exists(self):
        """
        HomeAssistantSmartHomeClimateRepository must expose the session-reuse
        pattern.

        FAILS today for the same reason as the lights repository.
        """
        from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_climate_repository import (
            HomeAssistantSmartHomeClimateRepository,
        )

        repo = HomeAssistantSmartHomeClimateRepository(
            base_url="http://ha:8123", token="tok"
        )

        has_pattern = hasattr(repo, "_get_session") or hasattr(repo, "_session")
        assert has_pattern, (
            "HomeAssistantSmartHomeClimateRepository must expose either "
            "_get_session() or _session for session reuse."
        )

    def test_sensor_repository__has_get_session_method_or_session_attr__session_reuse_pattern_exists(self):
        """
        HomeAssistantSmartHomeSensorRepository must expose the session-reuse
        pattern.

        FAILS today because no session-reuse mechanism exists.
        """
        from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_sensor_repository import (
            HomeAssistantSmartHomeSensorRepository,
        )

        repo = HomeAssistantSmartHomeSensorRepository(
            base_url="http://ha:8123", token="tok"
        )

        has_pattern = hasattr(repo, "_get_session") or hasattr(repo, "_session")
        assert has_pattern, (
            "HomeAssistantSmartHomeSensorRepository must expose either "
            "_get_session() or _session for session reuse."
        )

    def test_camera_repository__has_get_session_method_or_session_attr__session_reuse_pattern_exists(self):
        """
        HomeAssistantSmartHomeCameraRepository must expose the session-reuse
        pattern.

        FAILS today because no session-reuse mechanism exists.
        """
        from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_camera_repository import (
            HomeAssistantSmartHomeCameraRepository,
        )

        repo = HomeAssistantSmartHomeCameraRepository(
            base_url="http://ha:8123", token="tok"
        )

        has_pattern = hasattr(repo, "_get_session") or hasattr(repo, "_session")
        assert has_pattern, (
            "HomeAssistantSmartHomeCameraRepository must expose either "
            "_get_session() or _session for session reuse."
        )

    def test_music_repository__has_get_session_method_or_session_attr__session_reuse_pattern_exists(self):
        """
        MusicAssistantMusicRepository must expose the session-reuse pattern.

        FAILS today because no session-reuse mechanism exists.
        """
        from infra.data.external.music.music_assistant.music_assistant_music_repository import (
            MusicAssistantMusicRepository,
        )

        repo = MusicAssistantMusicRepository(base_url="http://ma:8095")

        has_pattern = hasattr(repo, "_get_session") or hasattr(repo, "_session")
        assert has_pattern, (
            "MusicAssistantMusicRepository must expose either _get_session() "
            "or _session for session reuse."
        )

    def test_light_repository__get_session_called_twice__returns_same_session_object(self):
        """
        Calling _get_session() (if it exists) twice on the same adapter
        instance must return the same aiohttp.ClientSession object.

        This test is skipped when _get_session does not yet exist — the
        previous test already documents that failure.  When _get_session IS
        present, this test verifies the lazy-init contract.

        FAILS today either because _get_session does not exist or because it
        creates a new session on every call.
        """
        from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_light_repository import (
            HomeAssistantSmartHomeLightRepository,
        )

        repo = HomeAssistantSmartHomeLightRepository(
            base_url="http://ha:8123", token="tok"
        )

        if not hasattr(repo, "_get_session"):
            pytest.fail(
                "HomeAssistantSmartHomeLightRepository._get_session() does not "
                "exist. Implement the method before verifying session identity."
            )

        # _get_session() may be a coroutine (async) or a sync helper.
        # We patch aiohttp.ClientSession to avoid real network connections.
        mock_session = MagicMock()
        with patch(
            "infra.data.external.smart_home.home_assistant"
            ".home_assistant_smart_home_light_repository.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            s1 = repo._get_session()
            s2 = repo._get_session()

        assert s1 is s2, (
            "_get_session() must return the same ClientSession object on "
            "consecutive calls to the same repository instance. "
            "Currently a new session is created on every HTTP method call."
        )


# ===========================================================================
# 3.2 — WebSocket timeout configuration
# ===========================================================================


class TestWebSocketTimeoutConfig:
    """
    Verify that websockets.connect() inside
    HomeAssistantSmartHomeConfigurationRepository._connect() is called with
    explicit ping_interval, ping_timeout, and close_timeout parameters.

    RED: currently websockets_connect() is called without these parameters,
         leaving the connection without keep-alive or teardown timeouts.
    GREEN: after the fix, all three parameters are supplied with sensible
           values (e.g. ping_interval=20, ping_timeout=10, close_timeout=5).
    """

    def _make_ws_mock(self) -> MagicMock:
        """Build a websocket mock that passes the _authenticate() handshake."""
        ws = AsyncMock()
        # _authenticate() reads two messages: auth_required, then auth_ok
        ws.recv.side_effect = [
            '{"type": "auth_required"}',
            '{"type": "auth_ok"}',
        ]
        return ws

    def test_connect__http_url__websockets_connect_receives_ping_interval(self):
        """
        When _connect() is called with an http:// URL, websockets_connect must
        be called with a non-None ping_interval keyword argument.

        FAILS today because the current call is:
            websockets_connect(ws_url, max_size=None)
        with no ping_interval parameter.
        """
        from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_configuration_repository import (
            HomeAssistantSmartHomeConfigurationRepository,
        )

        repo = HomeAssistantSmartHomeConfigurationRepository(
            websocket_url="http://ha:8123", token="tok"
        )

        ws_mock = self._make_ws_mock()

        with patch(
            "infra.data.external.smart_home.home_assistant"
            ".home_assistant_smart_home_configuration_repository.websockets_connect",
            new_callable=AsyncMock,
            return_value=ws_mock,
        ) as mock_connect:
            asyncio.get_event_loop().run_until_complete(repo._connect())

        _assert_kwarg_present(
            mock_connect,
            kwarg="ping_interval",
            test_description=(
                "websockets_connect() must be called with ping_interval set to "
                "a non-None value. Currently it is not passed at all, leaving "
                "the connection without keep-alive pings."
            ),
        )

    def test_connect__http_url__websockets_connect_receives_ping_timeout(self):
        """
        websockets_connect() must receive a non-None ping_timeout argument.

        FAILS today for the same reason as the ping_interval test.
        """
        from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_configuration_repository import (
            HomeAssistantSmartHomeConfigurationRepository,
        )

        repo = HomeAssistantSmartHomeConfigurationRepository(
            websocket_url="http://ha:8123", token="tok"
        )

        ws_mock = self._make_ws_mock()

        with patch(
            "infra.data.external.smart_home.home_assistant"
            ".home_assistant_smart_home_configuration_repository.websockets_connect",
            new_callable=AsyncMock,
            return_value=ws_mock,
        ) as mock_connect:
            asyncio.get_event_loop().run_until_complete(repo._connect())

        _assert_kwarg_present(
            mock_connect,
            kwarg="ping_timeout",
            test_description=(
                "websockets_connect() must be called with ping_timeout set to "
                "a non-None value."
            ),
        )

    def test_connect__http_url__websockets_connect_receives_close_timeout(self):
        """
        websockets_connect() must receive a non-None close_timeout argument.

        FAILS today because close_timeout is not passed to websockets_connect().
        """
        from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_configuration_repository import (
            HomeAssistantSmartHomeConfigurationRepository,
        )

        repo = HomeAssistantSmartHomeConfigurationRepository(
            websocket_url="http://ha:8123", token="tok"
        )

        ws_mock = self._make_ws_mock()

        with patch(
            "infra.data.external.smart_home.home_assistant"
            ".home_assistant_smart_home_configuration_repository.websockets_connect",
            new_callable=AsyncMock,
            return_value=ws_mock,
        ) as mock_connect:
            asyncio.get_event_loop().run_until_complete(repo._connect())

        _assert_kwarg_present(
            mock_connect,
            kwarg="close_timeout",
            test_description=(
                "websockets_connect() must be called with close_timeout set to "
                "a non-None value."
            ),
        )

    def test_connect__http_url__ping_interval_is_positive_integer(self):
        """
        The ping_interval value passed to websockets_connect() must be a
        positive integer (greater than zero).

        FAILS today because ping_interval is not passed at all.
        """
        from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_configuration_repository import (
            HomeAssistantSmartHomeConfigurationRepository,
        )

        repo = HomeAssistantSmartHomeConfigurationRepository(
            websocket_url="http://ha:8123", token="tok"
        )

        ws_mock = self._make_ws_mock()

        with patch(
            "infra.data.external.smart_home.home_assistant"
            ".home_assistant_smart_home_configuration_repository.websockets_connect",
            new_callable=AsyncMock,
            return_value=ws_mock,
        ) as mock_connect:
            asyncio.get_event_loop().run_until_complete(repo._connect())

        _, kwargs = mock_connect.call_args
        value = kwargs.get("ping_interval")
        assert isinstance(value, (int, float)) and value > 0, (
            f"ping_interval must be a positive number, got {value!r}. "
            "A common default is 20 seconds."
        )

    def test_connect__https_url__all_timeout_params_present(self):
        """
        For wss:// (HTTPS) URLs, the SSL branch must also pass all three
        timeout parameters to websockets_connect().

        FAILS today because the SSL branch does not include these parameters.
        """
        from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_configuration_repository import (
            HomeAssistantSmartHomeConfigurationRepository,
        )

        repo = HomeAssistantSmartHomeConfigurationRepository(
            websocket_url="https://ha:8123", token="tok"
        )

        ws_mock = self._make_ws_mock()

        with patch(
            "infra.data.external.smart_home.home_assistant"
            ".home_assistant_smart_home_configuration_repository.websockets_connect",
            new_callable=AsyncMock,
            return_value=ws_mock,
        ) as mock_connect, patch("ssl.create_default_context"):
            asyncio.get_event_loop().run_until_complete(repo._connect())

        _, kwargs = mock_connect.call_args
        missing = [
            k for k in ("ping_interval", "ping_timeout", "close_timeout")
            if kwargs.get(k) is None
        ]
        assert not missing, (
            f"websockets_connect() (SSL branch) is missing timeout kwargs: "
            f"{missing}. All three must be non-None."
        )


# ===========================================================================
# 3.3 — RedisContextRepository lazy connection
# ===========================================================================


class TestRedisContextRepositoryLazyConnection:
    """
    Verify that RedisContextRepository initialises its Redis client lazily —
    before the first use — so that set_key, get_key, and delete_key never
    raise AttributeError due to an uninitialised _client.

    RED: currently __init__ declares `self._client: Redis` as a type
         annotation only; connect() is never called automatically.
         Any call to set_key / get_key / delete_key raises:
             AttributeError: 'RedisContextRepository' object has no attribute '_client'
    GREEN: after the fix, _client is initialised (lazily or eagerly) before
           any method that uses it is invoked.
    """

    def _make_repo_with_mock_client(self):
        """
        Build a RedisContextRepository whose underlying Redis client is a
        MagicMock, avoiding any real network connection.
        """
        from infra.data.sqlite.context_repository_redis import RedisContextRepository

        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=True)
        mock_client.get = AsyncMock(return_value=b"value")
        mock_client.delete = AsyncMock(return_value=1)

        with patch(
            "infra.data.sqlite.context_repository_redis.from_url",
            return_value=mock_client,
        ):
            repo = RedisContextRepository("redis://localhost:6379/0")
        return repo, mock_client

    def test_init__no_connect_called__client_attribute_accessible(self):
        """
        After __init__, `_client` must be accessible (i.e. the attribute must
        exist on the instance) even if connect() was not called explicitly.

        FAILS today because `self._client: Redis` is a bare annotation — no
        value is ever assigned in __init__, so `hasattr(repo, '_client')`
        returns False and any access raises AttributeError.
        """
        from infra.data.sqlite.context_repository_redis import RedisContextRepository

        with patch("infra.data.sqlite.context_repository_redis.from_url"):
            repo = RedisContextRepository("redis://localhost:6379/0")

        assert hasattr(repo, "_client"), (
            "RedisContextRepository.__init__ must initialise `_client` (even "
            "lazily) so that the attribute exists before any method call. "
            "Currently `self._client: Redis` is only a type annotation — no "
            "value is assigned, causing AttributeError on first use."
        )

    def test_set_key__without_explicit_connect__does_not_raise_attribute_error(self):
        """
        Calling set_key() without a prior explicit connect() must not raise
        AttributeError.

        FAILS today because _client is never assigned, so the coroutine body
        `await self._client.set(key, value)` raises:
            AttributeError: 'RedisContextRepository' object has no attribute '_client'
        """
        repo, _ = self._make_repo_with_mock_client()

        try:
            asyncio.get_event_loop().run_until_complete(
                repo.set_key("test-key", "test-value")
            )
        except AttributeError as exc:
            pytest.fail(
                f"set_key() raised AttributeError before reaching the Redis "
                f"call: {exc}. Implement lazy connection in __init__ or in "
                f"_get_client()."
            )

    def test_get_key__without_explicit_connect__does_not_raise_attribute_error(self):
        """
        Calling get_key() without a prior explicit connect() must not raise
        AttributeError.

        FAILS today for the same reason as test_set_key.
        """
        repo, _ = self._make_repo_with_mock_client()

        try:
            asyncio.get_event_loop().run_until_complete(repo.get_key("test-key"))
        except AttributeError as exc:
            pytest.fail(
                f"get_key() raised AttributeError before reaching the Redis "
                f"call: {exc}."
            )

    def test_delete_key__without_explicit_connect__does_not_raise_attribute_error(self):
        """
        Calling delete_key() without a prior explicit connect() must not raise
        AttributeError.

        FAILS today for the same reason as test_set_key.
        """
        repo, _ = self._make_repo_with_mock_client()

        try:
            asyncio.get_event_loop().run_until_complete(repo.delete_key("test-key"))
        except AttributeError as exc:
            pytest.fail(
                f"delete_key() raised AttributeError before reaching the Redis "
                f"call: {exc}."
            )

    def test_set_key__lazy_connect__underlying_client_set_called(self):
        """
        After the lazy-connection fix, set_key() must reach the underlying
        Redis client and call client.set() with the correct arguments.

        This test doubles as a regression check: even with lazy init, the
        actual Redis operation must still be performed.

        FAILS today because _client is not initialised, so the call never
        reaches the Redis mock.
        """
        repo, mock_client = self._make_repo_with_mock_client()

        asyncio.get_event_loop().run_until_complete(
            repo.set_key("my-key", "my-value")
        )

        mock_client.set.assert_called_once_with("my-key", "my-value")

    def test_get_key__lazy_connect__underlying_client_get_called(self):
        """
        After the lazy-connection fix, get_key() must reach the underlying
        Redis client and call client.get() with the correct key.

        FAILS today because _client is never initialised.
        """
        repo, mock_client = self._make_repo_with_mock_client()

        asyncio.get_event_loop().run_until_complete(repo.get_key("my-key"))

        mock_client.get.assert_called_once_with("my-key")

    def test_delete_key__lazy_connect__underlying_client_delete_called(self):
        """
        After the lazy-connection fix, delete_key() must reach the underlying
        Redis client and call client.delete() with the correct key.

        FAILS today because _client is never initialised.
        """
        repo, mock_client = self._make_repo_with_mock_client()

        asyncio.get_event_loop().run_until_complete(repo.delete_key("my-key"))

        mock_client.delete.assert_called_once_with("my-key")

    def test_connect__when_called_explicitly__does_not_raise(self):
        """
        The existing explicit connect() method must still work correctly after
        the lazy-connection refactor.

        This test ensures backward compatibility: code that calls
        connect() manually (e.g. health checks) must not break.
        """
        from infra.data.sqlite.context_repository_redis import RedisContextRepository

        mock_client = MagicMock()

        with patch(
            "infra.data.sqlite.context_repository_redis.from_url",
            return_value=mock_client,
        ) as mock_from_url:
            repo = RedisContextRepository("redis://localhost:6379/0")
            repo.connect()

        mock_from_url.assert_called_with("redis://localhost:6379/0")
        assert repo._client is mock_client


# ===========================================================================
# Private helpers
# ===========================================================================


def _assert_kwarg_present(mock_obj: MagicMock, kwarg: str, test_description: str):
    """
    Assert that `mock_obj` was called with keyword argument `kwarg` whose
    value is not None.  Produces a clear failure message using `test_description`.
    """
    assert mock_obj.call_count >= 1, (
        f"Expected the mock to be called at least once, but it was never called."
    )
    _, kwargs = mock_obj.call_args
    assert kwarg in kwargs and kwargs[kwarg] is not None, (
        f"Keyword argument `{kwarg}` was not passed (or was None) to the mock. "
        f"{test_description}"
    )
