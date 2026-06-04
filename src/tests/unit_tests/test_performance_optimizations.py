"""
Performance Optimization Unit Tests — Milestone 1 (TDD RED phase)

Covers three infrastructure optimizations that must not alter any business
behaviour.  All tests are written BEFORE the implementation exists, so they
are expected to FAIL with the current codebase.

1.1 — Settings singleton in infra/ioc.py
    Verifies that Settings() is NOT instantiated multiple times across factory
    function calls.  After the optimization, a single module-level `_settings`
    object must be reused by every factory.

1.2 — Compiled graph cache (lazy init)
    Verifies that Graph._compile() is called exactly once even when invoke() is
    called multiple times on the same graph instance.

1.3 — Prompt file cache
    Verifies that Path.read_text() is called exactly once per unique prompt
    name, even when load_prompt() is called multiple times with the same name.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import infra.ioc as ioc_module
from application.graphs.graph import Graph
from application.graphs.music_graph import MusicGraph
from application.graphs.shopping_list_graph import ShoppingListGraph
from domain.entities import GraphInvokeRequest


# ===========================================================================
# Helpers
# ===========================================================================


def _make_concrete_graph(provider: str = "OLLAMA") -> Graph:
    """Instantiate a minimal anonymous concrete subclass of Graph."""

    class _ConcreteGraph(Graph):
        def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
            return {}

    return _ConcreteGraph(provider=provider)


def _make_shopping_list_graph() -> ShoppingListGraph:
    """
    Build a ShoppingListGraph with all external dependencies mocked.
    load_prompt is patched at construction time to avoid filesystem access.
    """
    llm_chat = MagicMock()
    shopping_list_service = MagicMock()

    with patch.object(ShoppingListGraph, "load_prompt", return_value="{input}"):
        graph = ShoppingListGraph(
            llm_chat=llm_chat,
            shopping_list_service=shopping_list_service,
        )
    return graph


def _make_music_graph() -> MusicGraph:
    """
    Build a MusicGraph with all external dependencies mocked.
    load_prompt is patched at construction time to avoid filesystem access.
    """
    llm_chat = MagicMock()
    music_service = MagicMock()
    music_service.get_players = MagicMock(return_value=[])

    with patch.object(MusicGraph, "load_prompt", return_value="{input}"):
        graph = MusicGraph(
            llm_chat=llm_chat,
            music_service=music_service,
        )
    return graph


def _make_invoke_request() -> GraphInvokeRequest:
    """Return a minimal GraphInvokeRequest that satisfies graph node contracts."""
    user = MagicMock()
    user.id = "test-user-id"
    return GraphInvokeRequest(message="test message", user=user)


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


# ===========================================================================
# 1.1 — Settings singleton in ioc.py
# ===========================================================================


class TestSettingsSingleton:
    """
    Verify that infra/ioc.py exposes a module-level `_settings` singleton and
    that factory functions reuse it instead of calling Settings() each time.

    RED: Currently ioc.py calls Settings() inside every factory function.
    GREEN: After the optimization, `_settings` is instantiated once at module
           level and referenced by all factories.
    """

    def test_settings_singleton__module_has_settings_attribute__attribute_exists(self):
        """
        After the optimization, ioc.py must expose a module-level `_settings`
        attribute holding the shared Settings instance.

        FAILS today because the module-level variable does not exist yet.
        """
        assert hasattr(ioc_module, "_settings"), (
            "infra/ioc.py must expose a module-level `_settings` singleton. "
            "Currently Settings() is instantiated inside each factory function."
        )

    def test_settings_singleton__two_factory_calls__settings_instantiated_once(self):
        """
        Calling two different factory functions must result in Settings() being
        constructed exactly once, not twice.

        FAILS today because each factory function calls Settings() independently,
        resulting in at least 2 constructions per pair of factory calls.
        """
        with patch.dict(os.environ, _BASE_ENV), patch(
            "infra.ioc.Settings"
        ) as mock_settings_cls, patch(
            "infra.ioc.ChatOllama"
        ), patch(
            "infra.ioc.SqliteUserRepository"
        ), patch(
            "infra.ioc.SqliteShoppingListRepository"
        ):
            mock_settings_cls.return_value = MagicMock(
                llm_provider_type="OLLAMA",
                llm_provider_url="http://ollama-host:11434",
                llm_provider_api_key="",
                llm_shopping_list_graph_chat_model="qwen3:14b",
                llm_shopping_list_graph_chat_temperature=0.5,
                peruca_db_connection_string="sqlite:///tmp/test.db",
            )

            ioc_module.get_user_repository()
            ioc_module.get_shopping_list_repository()

        # After the optimization, Settings() must be called exactly once
        # (the module-level singleton) rather than once per factory call.
        assert mock_settings_cls.call_count == 1, (
            f"Settings() was instantiated {mock_settings_cls.call_count} time(s). "
            "Expected exactly 1 call after singleton optimization. "
            "Currently each factory calls Settings() independently."
        )

    def test_settings_singleton__module_level_settings__is_settings_instance(self):
        """
        The `_settings` attribute on the ioc module must be an instance of
        the Settings class, not None or any other type.

        FAILS today because `_settings` does not exist on the module.
        """
        from infra.settings import Settings

        assert hasattr(ioc_module, "_settings"), (
            "infra/ioc.py must expose `_settings` at module level."
        )
        assert isinstance(ioc_module._settings, Settings), (
            f"`ioc._settings` must be an instance of Settings, "
            f"got {type(ioc_module._settings)!r}."
        )


# ===========================================================================
# 1.2 — Compiled graph cache (lazy init)
# ===========================================================================


class TestCompiledGraphCache:
    """
    Verify that Graph._compile() is called exactly once even when invoke() is
    executed multiple times on the same graph instance.

    RED: Currently invoke() calls self._compile() on every invocation.
    GREEN: After the optimization, _compile() is called once and its result is
           stored in self._compiled_graph (or equivalent).
    """

    def test_shopping_list_graph__compile_called_once__on_multiple_invocations(self):
        """
        Calling ShoppingListGraph.invoke() three times must trigger _compile()
        only once (first call). Subsequent calls must reuse the cached compiled
        graph.

        FAILS today because invoke() calls self._compile() unconditionally on
        every invocation.
        """
        graph = _make_shopping_list_graph()
        fake_compiled = MagicMock()
        fake_compiled.invoke.return_value = {"output": "ok"}

        with patch.object(graph, "_compile", return_value=fake_compiled) as mock_compile:
            request = _make_invoke_request()
            graph.invoke(request)
            graph.invoke(request)
            graph.invoke(request)

        assert mock_compile.call_count == 1, (
            f"_compile() was called {mock_compile.call_count} time(s) across "
            "3 invocations. Expected exactly 1 call after lazy-init optimization. "
            "Currently _compile() is called on every invoke()."
        )

    def test_shopping_list_graph__compiled_graph_cached__attribute_set_after_first_invoke(self):
        """
        After the first invoke(), the graph instance must expose a
        `_compiled_graph` attribute holding the compiled workflow.

        FAILS today because the compiled result is a local variable inside
        invoke() and is never stored on self.
        """
        graph = _make_shopping_list_graph()
        fake_compiled = MagicMock()
        fake_compiled.invoke.return_value = {"output": "ok"}

        with patch.object(graph, "_compile", return_value=fake_compiled):
            graph.invoke(_make_invoke_request())

        assert hasattr(graph, "_compiled_graph"), (
            "After invoke(), the graph must store the compiled workflow in "
            "`self._compiled_graph`. Currently the result is discarded after "
            "each invocation."
        )
        assert graph._compiled_graph is fake_compiled, (
            "`self._compiled_graph` must reference the object returned by "
            "_compile(), but it holds a different object."
        )

    def test_music_graph__compile_called_once__on_multiple_invocations(self):
        """
        Calling MusicGraph.invoke() twice must trigger _compile() only once.

        FAILS today for the same reason as ShoppingListGraph.
        """
        graph = _make_music_graph()
        fake_compiled = MagicMock()
        fake_compiled.invoke.return_value = {"output": "ok"}

        with patch.object(graph, "_compile", return_value=fake_compiled) as mock_compile:
            request = _make_invoke_request()
            graph.invoke(request)
            graph.invoke(request)

        assert mock_compile.call_count == 1, (
            f"MusicGraph._compile() was called {mock_compile.call_count} time(s) "
            "across 2 invocations. Expected exactly 1 after lazy-init optimization."
        )

    def test_shopping_list_graph__second_invoke__uses_cached_compiled_graph(self):
        """
        On the second invoke(), the cached compiled graph must be used and
        _compile() must NOT be called again.

        This test distinguishes between a lazy-init that compiles once and an
        implementation that naively replaces the cached value on each call.

        FAILS today because _compile() is called on every invocation.
        """
        graph = _make_shopping_list_graph()
        first_compiled = MagicMock()
        first_compiled.invoke.return_value = {"output": "first"}
        second_compiled = MagicMock()
        second_compiled.invoke.return_value = {"output": "second"}

        compile_results = [first_compiled, second_compiled]

        with patch.object(graph, "_compile", side_effect=compile_results) as mock_compile:
            graph.invoke(_make_invoke_request())
            graph.invoke(_make_invoke_request())

        # _compile() must have been called exactly once regardless of how many
        # invocations occurred.
        assert mock_compile.call_count == 1, (
            f"Expected _compile() to be called once (lazy init), "
            f"but it was called {mock_compile.call_count} time(s)."
        )
        # The cached compiled graph must be the first one returned.
        assert graph._compiled_graph is first_compiled, (
            "The compiled graph stored in `_compiled_graph` must be the one "
            "returned on the first _compile() call."
        )


# ===========================================================================
# 1.3 — Prompt file cache
# ===========================================================================


class TestPromptCache:
    """
    Verify that Graph.load_prompt() reads the prompt file from disk exactly
    once per unique name, regardless of how many times it is called.

    RED: Currently load_prompt() calls Path.read_text() on every invocation.
    GREEN: After the optimization, a module-level `_prompt_cache` dict in
           graph.py is populated on the first call and returned on subsequent
           calls without touching the filesystem.
    """

    def test_load_prompt__same_name_called_twice__reads_file_once(self):
        """
        Calling load_prompt("main_graph.md") twice must result in exactly one
        Path.read_text() call.

        FAILS today because load_prompt() calls read_text() unconditionally on
        every invocation.
        """
        graph = _make_concrete_graph("OLLAMA")
        raw_content = "/no_think\nConteúdo do prompt."

        with patch("pathlib.Path.read_text", return_value=raw_content) as mock_read:
            graph.load_prompt("main_graph.md")
            graph.load_prompt("main_graph.md")

        assert mock_read.call_count == 1, (
            f"Path.read_text() was called {mock_read.call_count} time(s) for "
            "the same prompt name. Expected exactly 1 call after cache optimization. "
            "Currently load_prompt() reads the file on every call."
        )

    def test_load_prompt__same_name_called_five_times__reads_file_once(self):
        """
        Even with 5 calls using the same prompt name, read_text() must be
        invoked only once.

        FAILS today for the same reason as the two-call variant.
        """
        graph = _make_concrete_graph("OLLAMA")
        raw_content = "Prompt content here."

        with patch("pathlib.Path.read_text", return_value=raw_content) as mock_read:
            for _ in range(5):
                graph.load_prompt("shopping_list_graph.md")

        assert mock_read.call_count == 1, (
            f"Path.read_text() was called {mock_read.call_count} time(s) across "
            "5 calls to load_prompt(). Expected 1 after cache optimization."
        )

    def test_load_prompt__different_names__reads_each_file_once(self):
        """
        Calling load_prompt() with two distinct names must read each file
        exactly once (total of 2 read_text() calls), even if each is called
        multiple times.

        Verifies that the cache keys on the prompt name, not on a single shared
        value.

        FAILS today because read_text() is called on every load_prompt() call
        regardless of caching.
        """
        graph = _make_concrete_graph("OLLAMA")

        call_results = {
            "main_graph.md": "/no_think\nMain prompt.",
            "shopping_list_graph.md": "/no_thinking\nShopping prompt.",
        }

        def fake_read_text(encoding="utf-8"):
            # Determine which file is being read via the call args on Path
            # This side_effect is attached to Path.read_text, so 'self' is the
            # Path instance.  We cannot inspect it here, so we just return a
            # distinct string per call order.
            return "some content"

        with patch("pathlib.Path.read_text", return_value="some content") as mock_read:
            graph.load_prompt("main_graph.md")
            graph.load_prompt("main_graph.md")
            graph.load_prompt("shopping_list_graph.md")
            graph.load_prompt("shopping_list_graph.md")

        assert mock_read.call_count == 2, (
            f"Path.read_text() was called {mock_read.call_count} time(s) for "
            "2 distinct prompt names called twice each. Expected exactly 2 calls "
            "(one per unique name) after cache optimization."
        )

    def test_load_prompt__module_level_cache__exists_in_graph_module(self):
        """
        After the optimization, graph.py must expose a module-level
        `_prompt_cache` dict that holds previously loaded prompts.

        FAILS today because no such cache variable exists in graph.py.
        """
        import application.graphs.graph as graph_module

        assert hasattr(graph_module, "_prompt_cache"), (
            "application/graphs/graph.py must expose a module-level "
            "`_prompt_cache` dict for caching loaded prompts. "
            "Currently no such cache exists."
        )
        assert isinstance(graph_module._prompt_cache, dict), (
            f"`_prompt_cache` must be a dict, got {type(graph_module._prompt_cache)!r}."
        )

    def test_load_prompt__cached_value__returns_same_content_as_first_call(self):
        """
        The content returned by load_prompt() on the second call must be
        identical to the content returned on the first call (the cached value
        must not be corrupted or mutated).

        This test verifies correctness of the cache, not just the number of
        disk reads.

        FAILS today indirectly: because there is no cache, there is no risk of
        corruption yet — but the test documents the contract that the cache must
        preserve.
        """
        graph = _make_concrete_graph("OLLAMA")
        raw_content = "/no_think\nConteúdo esperado do prompt."

        with patch("pathlib.Path.read_text", return_value=raw_content):
            first_result = graph.load_prompt("main_graph.md")
            second_result = graph.load_prompt("main_graph.md")

        assert first_result == second_result, (
            "load_prompt() returned different content on the second call. "
            "The cache must return the same value as the first read."
        )

    def test_load_prompt__cache_populated__after_first_call(self):
        """
        After calling load_prompt("main_graph.md") once, the module-level
        `_prompt_cache` must contain an entry for that prompt name.

        FAILS today because `_prompt_cache` does not exist.
        """
        import application.graphs.graph as graph_module

        graph = _make_concrete_graph("OLLAMA")
        raw_content = "Prompt content."

        # Clear any previously populated cache to ensure a clean state.
        if hasattr(graph_module, "_prompt_cache"):
            graph_module._prompt_cache.clear()

        with patch("pathlib.Path.read_text", return_value=raw_content):
            graph.load_prompt("main_graph.md")

        assert hasattr(graph_module, "_prompt_cache"), (
            "graph.py must expose `_prompt_cache` at module level."
        )
        # The cache key is the prompt name (e.g. "main_graph.md")
        assert "main_graph.md" in graph_module._prompt_cache, (
            "After calling load_prompt('main_graph.md'), the key 'main_graph.md' "
            "must exist in `_prompt_cache`. Currently no caching is implemented."
        )
