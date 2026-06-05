"""
MainGraph._classify_intent parsing robustness unit tests.

Regression coverage for the curly-quote bug: the main_graph.md prompt examples
were authored with smart/curly quotes (U+201C/U+201D, U+2018/U+2019). Qwen3
mimics those examples and emits Python-looking lists with curly quotes such as
``[“smart_home_lights”]``. The classifier used ``eval()``, which raises
SyntaxError on curly quotes, and the bare ``except`` silently collapsed every
such response into ``["only_talking"]`` — misrouting valid imperative commands.

These tests pin the contract: whatever quote style the model emits, the parsed
intent must reflect the model's actual classification.
"""

from unittest.mock import MagicMock, patch
import uuid

import pytest

from application.graphs.main_graph import MainGraph
from domain.entities import GraphInvokeRequest, User


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="")


def _sample_request(message: str = "oi", context_hints: dict = None) -> GraphInvokeRequest:
    return GraphInvokeRequest(
        message=message,
        user=_sample_user(),
        memories=[],
        context_hints=context_hints or {},
    )


def _make_main_graph() -> MainGraph:
    llm_chat = MagicMock()
    llm_response = MagicMock()
    llm_response.content = '["only_talking"]'
    llm_chat.invoke.return_value = llm_response

    sub = MagicMock()
    sub.invoke.return_value = {"output": "ok"}

    with patch.object(MainGraph, "load_prompt", return_value="{input} {music_is_playing}"):
        return MainGraph(
            llm_chat=llm_chat,
            only_talk_graph=sub,
            shopping_list_graph=sub,
            smart_home_lights_graph=sub,
            smart_home_climate_graph=sub,
            smart_home_sensors_graph=sub,
        )


class TestClassifyIntentQuoteParsing:
    def test_classify_intent__curly_double_quotes__parses_real_intent(self):
        graph = _make_main_graph()
        graph._remove_thinking_tag = MagicMock(return_value="[“smart_home_lights”]")

        result = graph._classify_intent({"input": _sample_request("Ligue a luz da sala")})

        assert result["intent"] == ["smart_home_lights"], result

    def test_classify_intent__curly_single_quotes__parses_real_intent(self):
        graph = _make_main_graph()
        graph._remove_thinking_tag = MagicMock(return_value="[‘music’]")

        result = graph._classify_intent({"input": _sample_request("pausa a música")})

        assert result["intent"] == ["music"], result

    def test_classify_intent__curly_quotes_multi_intent__parses_all(self):
        graph = _make_main_graph()
        graph._remove_thinking_tag = MagicMock(
            return_value="[“smart_home_lights”, “music”]"
        )

        result = graph._classify_intent({"input": _sample_request("acende a luz e toca jazz")})

        assert result["intent"] == ["smart_home_lights", "music"], result

    def test_classify_intent__straight_quotes__still_parses(self):
        graph = _make_main_graph()
        graph._remove_thinking_tag = MagicMock(return_value='["shopping_list"]')

        result = graph._classify_intent({"input": _sample_request("adiciona leite na lista")})

        assert result["intent"] == ["shopping_list"], result

    def test_classify_intent__unparseable_output__falls_back_to_only_talking(self):
        graph = _make_main_graph()
        graph._remove_thinking_tag = MagicMock(return_value="não sei classificar isso")

        result = graph._classify_intent({"input": _sample_request("???")})

        assert result["intent"] == ["only_talking"], result
