"""
LLM reasoning/thinking control unit tests — Phase 1 (TDD RED phase).

gemma4 is a "thinking" model that emits hundreds of reasoning tokens before each
answer, adding 40s+ of latency on /chat. The fix is to forward a `reasoning`
kwarg to `ChatOllama` (langchain-ollama==1.1.0 maps `reasoning: bool | None` onto
the Ollama `think` field).

Contract being driven by these tests (implementation comes LATER):

  1. infra/settings.py exposes:
       - a global field `llm_reasoning: bool | None = None`
       - a per-graph override for EACH of the 9 graphs, all default None:
           llm_main_graph_chat_reasoning
           llm_only_talk_graph_chat_reasoning
           llm_shopping_list_graph_chat_reasoning
           llm_smart_home_lights_graph_chat_reasoning
           llm_smart_home_climate_graph_chat_reasoning
           llm_smart_home_sensors_graph_chat_reasoning
           llm_smart_home_cameras_graph_chat_reasoning
           llm_memory_graph_chat_reasoning
           llm_music_graph_chat_reasoning
       Three-state semantics: None = do NOT send `think` to the API (safe
       default); False = thinking off; True = thinking on.

  2. infra/ioc.py:
       - get_llm_chat(model, temperature, reasoning=None): on the OLLAMA branch,
         forward reasoning=reasoning to ChatOllama ONLY when reasoning is not
         None. When None, the `reasoning` kwarg must be absent (so `think` is
         never sent to models that reject it). The OPENAI branch never receives
         `reasoning`.
       - a per-graph -> global resolver `_resolve_reasoning(per_graph_value)`:
         returns per_graph_value if not None, otherwise settings.llm_reasoning.
         Graph factories call
           get_llm_chat(..., reasoning=_resolve_reasoning(settings.llm_<graph>_chat_reasoning)).

These tests are written BEFORE the implementation, so they are expected to FAIL
against the current codebase:
  - Settings has no `llm_reasoning` / per-graph `*_reasoning` fields yet.
  - get_llm_chat() has no `reasoning` parameter and never forwards it.
  - _resolve_reasoning() does not exist.

Patterns mirror test_llm_chat_tuning.py (MagicMock Settings + patched
infra.ioc.Settings / infra.ioc.ChatOllama, ioc cache reset) and
test_ioc_graph_cache.py (graph factories driven through _repo_cache).
"""

import os
from unittest.mock import MagicMock, patch

import pytest

import infra.ioc as ioc_module


# ===========================================================================
# Helpers
# ===========================================================================


def _reset_ioc_settings_cache():
    """
    Force infra.ioc to rebuild its Settings singleton on the next
    _get_settings() call and drop any cached graph/repo instances.
    """
    ioc_module._real_settings = None
    ioc_module._settings_cls = None
    ioc_module._settings_env_snapshot = None
    ioc_module._repo_cache.clear()


def _make_ollama_settings(
    *,
    reasoning=None,
    keep_alive=-1,
    num_ctx=8192,
    num_predict=-1,
    url="http://ollama-host:11434",
):
    """Build a MagicMock Settings configured for the OLLAMA provider."""
    return MagicMock(
        llm_provider_type="OLLAMA",
        llm_provider_url=url,
        llm_provider_api_key="",
        llm_reasoning=reasoning,
        llm_keep_alive=keep_alive,
        llm_num_ctx=num_ctx,
        llm_num_predict=num_predict,
        llm_only_talk_history_max_messages=30,
    )


def _make_openai_settings(*, reasoning=None):
    """Build a MagicMock Settings configured for the OPENAI provider."""
    return MagicMock(
        llm_provider_type="OPENAI",
        llm_provider_url="http://ignored",
        llm_provider_api_key="sk-test-key",
        llm_reasoning=reasoning,
        llm_keep_alive=-1,
        llm_num_ctx=8192,
        llm_num_predict=-1,
    )


# ===========================================================================
# 1 — Settings exposes the new reasoning fields (global + per-graph)
# ===========================================================================


# All nine per-graph reasoning override fields, all expected to default to None.
_PER_GRAPH_REASONING_FIELDS = [
    "llm_main_graph_chat_reasoning",
    "llm_only_talk_graph_chat_reasoning",
    "llm_shopping_list_graph_chat_reasoning",
    "llm_smart_home_lights_graph_chat_reasoning",
    "llm_smart_home_climate_graph_chat_reasoning",
    "llm_smart_home_sensors_graph_chat_reasoning",
    "llm_smart_home_cameras_graph_chat_reasoning",
    "llm_memory_graph_chat_reasoning",
    "llm_music_graph_chat_reasoning",
]


class TestSettingsReasoningFields:
    """
    Settings must expose the global `llm_reasoning` field and one per-graph
    override for each of the nine graphs, all defaulting to None.

    RED: none of these attributes exist on Settings yet.
    """

    def test_settings__has_global_llm_reasoning_default_false(self):
        from infra.settings import Settings

        settings = Settings()
        assert hasattr(settings, "llm_reasoning"), (
            "Settings must expose the global `llm_reasoning` field."
        )
        assert settings.llm_reasoning is False, (
            f"Default llm_reasoning must be False (disable thinking by default so "
            f"the configured gemma4 model stops wasting reasoning tokens), got "
            f"{settings.llm_reasoning!r}."
        )

    @pytest.mark.parametrize("field_name", _PER_GRAPH_REASONING_FIELDS)
    def test_settings__has_per_graph_reasoning_default_none(self, field_name):
        from infra.settings import Settings

        settings = Settings()
        assert hasattr(settings, field_name), (
            f"Settings must expose the per-graph override `{field_name}`."
        )
        assert getattr(settings, field_name) is None, (
            f"Default {field_name} must be None, got "
            f"{getattr(settings, field_name)!r}."
        )


# ===========================================================================
# 2 — get_llm_chat forwards `reasoning` to ChatOllama (OLLAMA branch)
# ===========================================================================


class TestGetLlmChatOllamaReasoning:
    """
    On the OLLAMA branch, get_llm_chat() must forward `reasoning` to ChatOllama
    only when it is not None. When None (the default), the `reasoning` kwarg must
    be absent so `think` is never sent to models that reject it.

    RED: get_llm_chat() has no `reasoning` parameter and never forwards it.
    """

    def test_get_llm_chat__ollama__reasoning_false__forwarded_as_false(self):
        settings = _make_ollama_settings()

        with patch("infra.ioc.Settings", return_value=settings), patch(
            "infra.ioc.ChatOllama"
        ) as mock_ollama:
            _reset_ioc_settings_cache()
            ioc_module.get_llm_chat(
                model="gemma4:12b", temperature=0.1, reasoning=False
            )

        mock_ollama.assert_called_once()
        kwargs = mock_ollama.call_args.kwargs
        assert "reasoning" in kwargs, (
            "ChatOllama must receive the `reasoning` kwarg when reasoning is "
            "explicitly False."
        )
        assert kwargs["reasoning"] is False, (
            f"ChatOllama must receive reasoning=False; got "
            f"reasoning={kwargs.get('reasoning')!r}."
        )

    def test_get_llm_chat__ollama__reasoning_true__forwarded_as_true(self):
        settings = _make_ollama_settings()

        with patch("infra.ioc.Settings", return_value=settings), patch(
            "infra.ioc.ChatOllama"
        ) as mock_ollama:
            _reset_ioc_settings_cache()
            ioc_module.get_llm_chat(
                model="gemma4:12b", temperature=0.1, reasoning=True
            )

        mock_ollama.assert_called_once()
        kwargs = mock_ollama.call_args.kwargs
        assert "reasoning" in kwargs, (
            "ChatOllama must receive the `reasoning` kwarg when reasoning is "
            "explicitly True."
        )
        assert kwargs["reasoning"] is True, (
            f"ChatOllama must receive reasoning=True; got "
            f"reasoning={kwargs.get('reasoning')!r}."
        )

    def test_get_llm_chat__ollama__reasoning_none_default__kwarg_absent(self):
        settings = _make_ollama_settings()

        with patch("infra.ioc.Settings", return_value=settings), patch(
            "infra.ioc.ChatOllama"
        ) as mock_ollama:
            _reset_ioc_settings_cache()
            # No reasoning argument -> default None.
            ioc_module.get_llm_chat(model="gemma4:12b", temperature=0.1)

        mock_ollama.assert_called_once()
        kwargs = mock_ollama.call_args.kwargs
        assert "reasoning" not in kwargs, (
            "When reasoning is None (default), ChatOllama must NOT receive the "
            "`reasoning` kwarg so `think` is never sent to models that reject it; "
            f"got kwargs={sorted(kwargs)!r}."
        )

    def test_get_llm_chat__ollama__reasoning_explicit_none__kwarg_absent(self):
        settings = _make_ollama_settings()

        with patch("infra.ioc.Settings", return_value=settings), patch(
            "infra.ioc.ChatOllama"
        ) as mock_ollama:
            _reset_ioc_settings_cache()
            ioc_module.get_llm_chat(
                model="gemma4:12b", temperature=0.1, reasoning=None
            )

        mock_ollama.assert_called_once()
        kwargs = mock_ollama.call_args.kwargs
        assert "reasoning" not in kwargs, (
            "Explicit reasoning=None must behave like the default: ChatOllama "
            f"must NOT receive the `reasoning` kwarg; got kwargs={sorted(kwargs)!r}."
        )

    def test_get_llm_chat__ollama__reasoning_does_not_break_existing_kwargs(self):
        """Regression: base_url/model/temperature/keep_alive/num_ctx/num_predict
        must remain correct when reasoning is forwarded."""
        settings = _make_ollama_settings(
            reasoning=None,
            keep_alive=-1,
            num_ctx=8192,
            num_predict=-1,
            url="http://ollama-host:11434",
        )

        with patch("infra.ioc.Settings", return_value=settings), patch(
            "infra.ioc.ChatOllama"
        ) as mock_ollama:
            _reset_ioc_settings_cache()
            ioc_module.get_llm_chat(
                model="gemma4:12b", temperature=0.7, reasoning=False
            )

        kwargs = mock_ollama.call_args.kwargs
        assert kwargs.get("base_url") == "http://ollama-host:11434"
        assert kwargs.get("model") == "gemma4:12b"
        assert kwargs.get("temperature") == 0.7
        assert kwargs.get("keep_alive") == -1
        assert kwargs.get("num_ctx") == 8192
        assert kwargs.get("num_predict") == -1
        assert kwargs.get("reasoning") is False


# ===========================================================================
# 3 — OPENAI branch never receives `reasoning`
# ===========================================================================


class TestGetLlmChatOpenAiReasoning:
    """
    The OPENAI branch (ChatOpenAI) must NEVER receive the `reasoning` kwarg, even
    when reasoning is explicitly passed to get_llm_chat().

    RED: get_llm_chat() has no `reasoning` parameter yet (the call will fail with
    a TypeError before reaching the OPENAI branch).
    """

    @pytest.mark.parametrize("reasoning_value", [False, True, None])
    def test_get_llm_chat__openai__never_receives_reasoning(self, reasoning_value):
        settings = _make_openai_settings()

        with patch("infra.ioc.Settings", return_value=settings), patch(
            "infra.ioc.ChatOpenAI"
        ) as mock_openai, patch("infra.ioc.ChatOllama") as mock_ollama:
            _reset_ioc_settings_cache()
            ioc_module.get_llm_chat(
                model="gpt-4o", temperature=0.5, reasoning=reasoning_value
            )

        mock_ollama.assert_not_called()
        mock_openai.assert_called_once()
        kwargs = mock_openai.call_args.kwargs
        assert "reasoning" not in kwargs, (
            "ChatOpenAI must never receive the `reasoning` kwarg (Ollama-only); "
            f"got kwargs={sorted(kwargs)!r} for reasoning={reasoning_value!r}."
        )

    def test_get_llm_chat__openai__still_passes_model_temperature_api_key(self):
        settings = _make_openai_settings()

        with patch("infra.ioc.Settings", return_value=settings), patch(
            "infra.ioc.ChatOpenAI"
        ) as mock_openai, patch("infra.ioc.ChatOllama"):
            _reset_ioc_settings_cache()
            ioc_module.get_llm_chat(
                model="gpt-4o", temperature=0.3, reasoning=False
            )

        kwargs = mock_openai.call_args.kwargs
        assert kwargs.get("model") == "gpt-4o"
        assert kwargs.get("temperature") == 0.3
        assert kwargs.get("api_key") == "sk-test-key"


# ===========================================================================
# 4 — Per-graph -> global resolution (_resolve_reasoning helper)
# ===========================================================================


class TestResolveReasoningHelper:
    """
    _resolve_reasoning(per_graph_value) must return per_graph_value when it is not
    None, otherwise fall back to settings.llm_reasoning.

    Matrix:
      (global=False, graph=None) -> False
      (global=None,  graph=False) -> False
      (global=True,  graph=False) -> False
      (global=None,  graph=None) -> None

    RED: _resolve_reasoning does not exist on infra.ioc yet.
    """

    @pytest.mark.parametrize(
        "global_value,graph_value,expected",
        [
            (False, None, False),
            (None, False, False),
            (True, False, False),
            (None, None, None),
            # Additional coverage of the precedence rule.
            (False, True, True),
            (True, None, True),
            (None, True, True),
        ],
    )
    def test_resolve_reasoning__matrix(self, global_value, graph_value, expected):
        settings = _make_ollama_settings(reasoning=global_value)

        with patch("infra.ioc.Settings", return_value=settings):
            _reset_ioc_settings_cache()
            result = ioc_module._resolve_reasoning(graph_value)

        assert result is expected, (
            f"_resolve_reasoning(per_graph={graph_value!r}) with "
            f"global llm_reasoning={global_value!r} must return {expected!r}, "
            f"got {result!r}."
        )


# ===========================================================================
# 5 — Per-graph resolution wired through a graph factory
# ===========================================================================


_GRAPH_FACTORY_ENV = {
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


class TestGraphFactoryForwardsResolvedReasoning:
    """
    A graph factory must resolve its per-graph reasoning override against the
    global setting and forward the result to get_llm_chat() (and therefore to
    ChatOllama).

    only_talk is used as the representative graph because its factory builds a
    single llm_chat with no other graph/LLM dependencies, so the ChatOllama call
    inspected is unambiguously the one for that graph.

    RED: the factory does not yet pass a `reasoning` kwarg to get_llm_chat().
    """

    @pytest.fixture
    def patched_repos(self):
        """Patch the heavy/IO dependencies the only_talk factory transitively
        touches so a real graph can be built without network/DB access."""
        patches = [
            patch.dict(os.environ, _GRAPH_FACTORY_ENV, clear=True),
            patch("infra.ioc.SqliteUserRepository", MagicMock()),
            patch("infra.ioc.SqliteUserMemoryRepository", MagicMock()),
            patch("infra.ioc.SqliteShoppingListRepository", MagicMock()),
            patch("infra.ioc.SqliteSmartHomeEntityAliasRepository", MagicMock()),
            patch("infra.ioc.SqliteSmartHomeAreaRepository", MagicMock()),
            patch(
                "infra.ioc.HomeAssistantSmartHomeConfigurationRepository",
                MagicMock(),
            ),
            patch("infra.ioc.HomeAssistantSmartHomeLightRepository", MagicMock()),
            patch("infra.ioc.HomeAssistantSmartHomeClimateRepository", MagicMock()),
            patch("infra.ioc.HomeAssistantSmartHomeSensorRepository", MagicMock()),
            patch("infra.ioc.HomeAssistantSmartHomeCameraRepository", MagicMock()),
            patch("infra.ioc.MusicAssistantMusicRepository", MagicMock()),
            patch("infra.ioc.RedisContextRepository", MagicMock()),
        ]
        for p in patches:
            p.start()
        _reset_ioc_settings_cache()
        try:
            yield
        finally:
            _reset_ioc_settings_cache()
            for p in reversed(patches):
                p.stop()

    def _build_settings(self, *, global_value, graph_value):
        """MagicMock Settings exposing every attribute the only_talk factory and
        get_llm_chat read, with the reasoning knobs under test."""
        return MagicMock(
            llm_provider_type="OLLAMA",
            llm_provider_url="http://ollama-host:11434",
            llm_provider_api_key="",
            llm_strip_think_directive=True,
            llm_keep_alive=-1,
            llm_num_ctx=8192,
            llm_num_predict=-1,
            llm_reasoning=global_value,
            llm_only_talk_graph_chat_model="gemma4:12b",
            llm_only_talk_graph_chat_temperature=0.5,
            llm_only_talk_graph_chat_reasoning=graph_value,
            llm_only_talk_history_max_messages=30,
        )

    @pytest.mark.parametrize(
        "global_value,graph_value,expected_reasoning,expects_kwarg",
        [
            # per-graph None -> falls back to global False
            (False, None, False, True),
            # per-graph False wins over global None
            (None, False, False, True),
            # per-graph False wins over global True
            (True, False, False, True),
            # both None -> resolved None -> ChatOllama gets NO reasoning kwarg
            (None, None, None, False),
        ],
    )
    def test_get_only_talk_graph__forwards_resolved_reasoning_to_chat_ollama(
        self,
        patched_repos,
        global_value,
        graph_value,
        expected_reasoning,
        expects_kwarg,
    ):
        settings = self._build_settings(
            global_value=global_value, graph_value=graph_value
        )

        with patch("infra.ioc.Settings", return_value=settings), patch(
            "infra.ioc.ChatOllama"
        ) as mock_ollama:
            _reset_ioc_settings_cache()
            ioc_module.get_only_talk_graph()

        mock_ollama.assert_called_once()
        kwargs = mock_ollama.call_args.kwargs

        if expects_kwarg:
            assert kwargs.get("reasoning") is expected_reasoning, (
                f"only_talk factory with global={global_value!r}, "
                f"graph={graph_value!r} must forward reasoning="
                f"{expected_reasoning!r} to ChatOllama; got "
                f"reasoning={kwargs.get('reasoning')!r}."
            )
        else:
            assert "reasoning" not in kwargs, (
                f"only_talk factory with global={global_value!r}, "
                f"graph={graph_value!r} resolves to None and must NOT pass a "
                f"`reasoning` kwarg to ChatOllama; got kwargs={sorted(kwargs)!r}."
            )


# ===========================================================================
# Cleanup — keep the ioc settings cache from leaking into other test modules
# ===========================================================================


@pytest.fixture(autouse=True)
def _restore_ioc_cache():
    yield
    _reset_ioc_settings_cache()
