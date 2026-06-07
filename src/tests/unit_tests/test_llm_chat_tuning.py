"""
ChatOllama tuning unit tests — Phase 1 / Change #1 (TDD RED phase).

`get_llm_chat()` in infra/ioc.py must, on the OLLAMA branch, forward three new
performance tuning parameters sourced from Settings:

    - keep_alive=settings.llm_keep_alive   (default "-1")
    - num_ctx=settings.llm_num_ctx         (default 8192)
    - num_predict=settings.llm_num_predict (default -1)

The OPENAI branch (ChatOpenAI) must remain unchanged and must NOT receive any of
these kwargs.

These tests are written BEFORE the implementation exists, so they are expected
to FAIL against the current codebase:
  - The Settings fields do not exist yet (llm_keep_alive / llm_num_ctx /
    llm_num_predict).
  - get_llm_chat() does not forward keep_alive / num_ctx / num_predict to
    ChatOllama.

Note on the settings singleton: get_llm_chat() currently instantiates Settings()
directly, but the implementation will switch to the module-level singleton
exposed via _get_settings() (whose cache is invalidated when the os.environ
snapshot changes). To stay robust against either form, these tests patch
infra.ioc.Settings to return a controlled MagicMock and reset the ioc settings
cache before each test (mirroring test_settings_singleton in
test_performance_optimizations.py).
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
    _get_settings() call by clearing the cached class/snapshot.
    """
    ioc_module._real_settings = None
    ioc_module._settings_cls = None
    ioc_module._settings_env_snapshot = None
    ioc_module._repo_cache.clear()


def _make_ollama_settings(
    *,
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
        llm_keep_alive=keep_alive,
        llm_num_ctx=num_ctx,
        llm_num_predict=num_predict,
    )


def _make_openai_settings():
    """Build a MagicMock Settings configured for the OPENAI provider."""
    return MagicMock(
        llm_provider_type="OPENAI",
        llm_provider_url="http://ignored",
        llm_provider_api_key="sk-test-key",
        llm_keep_alive=-1,
        llm_num_ctx=8192,
        llm_num_predict=-1,
    )


# ===========================================================================
# 1 — Settings exposes the new tuning fields
# ===========================================================================


class TestSettingsTuningFields:
    """
    The Settings class must expose the three new tuning fields with the
    documented defaults.

    RED: these attributes do not exist on Settings yet.
    """

    def test_settings__has_llm_keep_alive_default(self):
        from infra.settings import Settings

        settings = Settings()
        assert hasattr(settings, "llm_keep_alive"), (
            "Settings must expose `llm_keep_alive`."
        )
        assert settings.llm_keep_alive == -1, (
            f"Default llm_keep_alive must be the integer -1 (Ollama rejects the "
            f"string '-1' as an invalid duration), got {settings.llm_keep_alive!r}."
        )

    def test_settings__has_llm_num_ctx_default(self):
        from infra.settings import Settings

        settings = Settings()
        assert hasattr(settings, "llm_num_ctx"), (
            "Settings must expose `llm_num_ctx`."
        )
        assert settings.llm_num_ctx == 8192, (
            f"Default llm_num_ctx must be 8192, got {settings.llm_num_ctx!r}."
        )

    def test_settings__has_llm_num_predict_default(self):
        from infra.settings import Settings

        settings = Settings()
        assert hasattr(settings, "llm_num_predict"), (
            "Settings must expose `llm_num_predict`."
        )
        assert settings.llm_num_predict == -1, (
            f"Default llm_num_predict must be -1, got {settings.llm_num_predict!r}."
        )


# ===========================================================================
# 2 — OLLAMA branch forwards the tuning kwargs
# ===========================================================================


class TestGetLlmChatOllamaTuning:
    """
    On the OLLAMA branch, get_llm_chat() must pass keep_alive / num_ctx /
    num_predict (sourced from Settings) to ChatOllama, in addition to the
    existing base_url / model / temperature.

    RED: get_llm_chat() does not forward these kwargs today.
    """

    def test_get_llm_chat__ollama__passes_keep_alive_num_ctx_num_predict(self):
        settings = _make_ollama_settings()

        with patch("infra.ioc.Settings", return_value=settings), patch(
            "infra.ioc.ChatOllama"
        ) as mock_ollama:
            _reset_ioc_settings_cache()
            ioc_module.get_llm_chat(model="qwen3:14b", temperature=0.5)

        mock_ollama.assert_called_once()
        kwargs = mock_ollama.call_args.kwargs

        assert kwargs.get("keep_alive") == -1, (
            f"ChatOllama must receive keep_alive from settings.llm_keep_alive; "
            f"got keep_alive={kwargs.get('keep_alive')!r}."
        )
        assert kwargs.get("num_ctx") == 8192, (
            f"ChatOllama must receive num_ctx from settings.llm_num_ctx; "
            f"got num_ctx={kwargs.get('num_ctx')!r}."
        )
        assert kwargs.get("num_predict") == -1, (
            f"ChatOllama must receive num_predict from settings.llm_num_predict; "
            f"got num_predict={kwargs.get('num_predict')!r}."
        )

    def test_get_llm_chat__ollama__still_passes_base_url_model_temperature(self):
        settings = _make_ollama_settings(url="http://ollama-host:11434")

        with patch("infra.ioc.Settings", return_value=settings), patch(
            "infra.ioc.ChatOllama"
        ) as mock_ollama:
            _reset_ioc_settings_cache()
            ioc_module.get_llm_chat(model="qwen3:14b", temperature=0.7)

        mock_ollama.assert_called_once()
        kwargs = mock_ollama.call_args.kwargs

        assert kwargs.get("base_url") == "http://ollama-host:11434"
        assert kwargs.get("model") == "qwen3:14b"
        assert kwargs.get("temperature") == 0.7

    def test_get_llm_chat__ollama__forwards_custom_tuning_values(self):
        """Tuning values must come from settings, not be hard-coded."""
        settings = _make_ollama_settings(
            keep_alive="30m", num_ctx=16384, num_predict=512
        )

        with patch("infra.ioc.Settings", return_value=settings), patch(
            "infra.ioc.ChatOllama"
        ) as mock_ollama:
            _reset_ioc_settings_cache()
            ioc_module.get_llm_chat(model="qwen3:14b", temperature=0.1)

        kwargs = mock_ollama.call_args.kwargs
        assert kwargs.get("keep_alive") == "30m"
        assert kwargs.get("num_ctx") == 16384
        assert kwargs.get("num_predict") == 512


# ===========================================================================
# 3 — OPENAI branch is untouched
# ===========================================================================


class TestGetLlmChatOpenAiUnchanged:
    """
    The OPENAI branch must NOT receive the tuning kwargs — they are Ollama
    specific.

    RED: this test currently passes for the "no kwargs" part but the surrounding
    contract (new Settings fields) does not yet exist; it is included to lock the
    OPENAI branch behaviour against the upcoming change.
    """

    def test_get_llm_chat__openai__does_not_pass_ollama_tuning_kwargs(self):
        settings = _make_openai_settings()

        with patch("infra.ioc.Settings", return_value=settings), patch(
            "infra.ioc.ChatOpenAI"
        ) as mock_openai, patch("infra.ioc.ChatOllama") as mock_ollama:
            _reset_ioc_settings_cache()
            ioc_module.get_llm_chat(model="gpt-4o", temperature=0.5)

        mock_ollama.assert_not_called()
        mock_openai.assert_called_once()
        kwargs = mock_openai.call_args.kwargs

        assert "keep_alive" not in kwargs, (
            "ChatOpenAI must not receive keep_alive (Ollama-only kwarg)."
        )
        assert "num_ctx" not in kwargs, (
            "ChatOpenAI must not receive num_ctx (Ollama-only kwarg)."
        )
        assert "num_predict" not in kwargs, (
            "ChatOpenAI must not receive num_predict (Ollama-only kwarg)."
        )

    def test_get_llm_chat__openai__still_passes_model_temperature_api_key(self):
        settings = _make_openai_settings()

        with patch("infra.ioc.Settings", return_value=settings), patch(
            "infra.ioc.ChatOpenAI"
        ) as mock_openai, patch("infra.ioc.ChatOllama"):
            _reset_ioc_settings_cache()
            ioc_module.get_llm_chat(model="gpt-4o", temperature=0.3)

        kwargs = mock_openai.call_args.kwargs
        assert kwargs.get("model") == "gpt-4o"
        assert kwargs.get("temperature") == 0.3
        assert kwargs.get("api_key") == "sk-test-key"


# ===========================================================================
# Cleanup — keep the ioc settings cache from leaking into other test modules
# ===========================================================================


@pytest.fixture(autouse=True)
def _restore_ioc_cache():
    yield
    _reset_ioc_settings_cache()
