import os
from unittest.mock import MagicMock, patch

import pytest

from infra.ioc import get_llm_chat
from application.graphs.graph import Graph
from domain.entities import GraphInvokeRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OLLAMA_ENV = {
    "LLM_PROVIDER_TYPE": "OLLAMA",
    "LLM_PROVIDER_URL": "http://ollama-host:11434",
    "LLM_PROVIDER_API_KEY": "",
}

_OPENAI_ENV = {
    "LLM_PROVIDER_TYPE": "OPENAI",
    "LLM_PROVIDER_URL": "",
    "LLM_PROVIDER_API_KEY": "sk-test-key",
}


def _make_concrete_graph(provider: str) -> Graph:
    """Instantiate a minimal anonymous concrete subclass of Graph."""

    class _ConcreteGraph(Graph):
        def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
            return {}

    return _ConcreteGraph(provider=provider)


# ---------------------------------------------------------------------------
# TestGetLlmChatOllama
# ---------------------------------------------------------------------------


class TestGetLlmChatOllama:
    def test_get_llm_chat__ollama_provider__returns_chat_ollama_instance(self):
        # Arrange
        mock_chat_ollama = MagicMock()
        with patch.dict(os.environ, _OLLAMA_ENV), patch(
            "infra.ioc.ChatOllama", mock_chat_ollama
        ):
            # Act
            result = get_llm_chat(model="qwen3:14b", temperature=0.5)

        # Assert — ChatOllama must be built once with the correct core kwargs.
        # Extra tuning kwargs (keep_alive / num_ctx / num_predict) are tolerated.
        mock_chat_ollama.assert_called_once()
        kwargs = mock_chat_ollama.call_args.kwargs
        assert kwargs["base_url"] == "http://ollama-host:11434"
        assert kwargs["model"] == "qwen3:14b"
        assert kwargs["temperature"] == 0.5
        assert result is mock_chat_ollama.return_value

    def test_get_llm_chat__ollama_provider__does_not_call_chat_openai(self):
        # Arrange
        mock_chat_openai = MagicMock()
        mock_chat_ollama = MagicMock()
        with patch.dict(os.environ, _OLLAMA_ENV), patch(
            "infra.ioc.ChatOpenAI", mock_chat_openai, create=True
        ), patch("infra.ioc.ChatOllama", mock_chat_ollama):
            # Act
            get_llm_chat(model="qwen3:14b", temperature=0.5)

        # Assert
        mock_chat_openai.assert_not_called()


# ---------------------------------------------------------------------------
# TestGetLlmChatOpenAI
# ---------------------------------------------------------------------------


class TestGetLlmChatOpenAI:
    def test_get_llm_chat__openai_provider__returns_chat_openai_instance(self):
        # Arrange
        mock_chat_openai = MagicMock()
        with patch.dict(os.environ, _OPENAI_ENV), patch(
            "infra.ioc.ChatOpenAI", mock_chat_openai, create=True
        ):
            # Act
            result = get_llm_chat(model="gpt-4o-mini", temperature=0.5)

        # Assert
        mock_chat_openai.assert_called_once_with(
            model="gpt-4o-mini",
            temperature=0.5,
            api_key="sk-test-key",
        )
        assert result is mock_chat_openai.return_value

    def test_get_llm_chat__openai_lowercase__is_accepted(self):
        # Arrange
        env = {**_OPENAI_ENV, "LLM_PROVIDER_TYPE": "openai"}
        mock_chat_openai = MagicMock()
        with patch.dict(os.environ, env), patch(
            "infra.ioc.ChatOpenAI", mock_chat_openai, create=True
        ):
            # Act
            result = get_llm_chat(model="gpt-4o-mini", temperature=0.0)

        # Assert
        mock_chat_openai.assert_called_once()
        assert result is mock_chat_openai.return_value


# ---------------------------------------------------------------------------
# TestGetLlmChatInvalidProvider
# ---------------------------------------------------------------------------


class TestGetLlmChatInvalidProvider:
    def test_get_llm_chat__unknown_provider__raises_value_error(self):
        # Arrange
        env = {
            "LLM_PROVIDER_TYPE": "ANTHROPIC",
            "LLM_PROVIDER_URL": "",
            "LLM_PROVIDER_API_KEY": "",
        }
        with patch.dict(os.environ, env):
            # Act & Assert
            with pytest.raises(ValueError):
                get_llm_chat(model="claude-3", temperature=0.5)


# ---------------------------------------------------------------------------
# TestGraphLoadPromptOllama
# ---------------------------------------------------------------------------


class TestGraphLoadPromptOllama:
    def test_load_prompt__ollama__preserves_no_think_directive(self):
        # Arrange
        raw = "/no_think\nConteúdo do prompt."
        graph = _make_concrete_graph("OLLAMA")

        with patch("pathlib.Path.read_text", return_value=raw):
            # Act
            result = graph.load_prompt("main_graph.md")

        # Assert
        assert result.startswith("/no_think")

    def test_load_prompt__ollama__preserves_no_thinking_directive(self):
        # Arrange
        raw = "/no_thinking\nAlgum conteúdo aqui."
        graph = _make_concrete_graph("OLLAMA")

        with patch("pathlib.Path.read_text", return_value=raw):
            result = graph.load_prompt("some_prompt.md")

        assert result.startswith("/no_thinking")


# ---------------------------------------------------------------------------
# TestGraphLoadPromptOpenAI
# ---------------------------------------------------------------------------


class TestGraphLoadPromptOpenAI:
    def test_load_prompt__openai__strips_no_think_first_line(self):
        # Arrange
        raw = "/no_think\nConteúdo do prompt."
        graph = _make_concrete_graph("OPENAI")

        with patch("pathlib.Path.read_text", return_value=raw):
            # Act
            result = graph.load_prompt("main_graph.md")

        # Assert
        assert not result.startswith("/no_think")

    def test_load_prompt__openai__strips_no_thinking_variant(self):
        # Arrange
        raw = "/no_thinking\nConteúdo do prompt."
        graph = _make_concrete_graph("OPENAI")

        with patch("pathlib.Path.read_text", return_value=raw):
            result = graph.load_prompt("shopping_list_graph.md")

        assert not result.startswith("/no_thinking")

    def test_load_prompt__openai__preserves_content_after_directive(self):
        # Arrange
        body = "Você é um assistente doméstico.\nResponda de forma concisa."
        raw = f"/no_think\n{body}"
        graph = _make_concrete_graph("OPENAI")

        with patch("pathlib.Path.read_text", return_value=raw):
            result = graph.load_prompt("main_graph.md")

        # Assert — body must be present and unchanged
        assert body in result

    def test_load_prompt__openai__no_directive__content_unchanged(self):
        # Arrange
        raw = "Prompt sem diretiva.\nSegunda linha."
        graph = _make_concrete_graph("OPENAI")

        with patch("pathlib.Path.read_text", return_value=raw):
            result = graph.load_prompt("only_talk_graph.md")

        # Assert — no stripping should happen, content identical
        assert result == raw

    def test_load_prompt__openai_lowercase__strips_directive(self):
        # Arrange
        raw = "/no_think\nConteúdo do prompt."
        graph = _make_concrete_graph("openai")

        with patch("pathlib.Path.read_text", return_value=raw):
            result = graph.load_prompt("main_graph.md")

        assert not result.startswith("/no_think")
