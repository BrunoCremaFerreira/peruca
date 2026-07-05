"""
Security regression: classifier parsers must not execute LLM output.

MainGraph and ShoppingListGraph parse the classifier's structured output with
a Python literal parser. They historically used ``eval()``, which executes
arbitrary expressions embedded in the model's text — a code-execution vector
reachable via prompt injection. The parser must accept only literals
(``ast.literal_eval``): a non-literal expression such as an ``__import__``
call must NOT run; it must fall back to the graph's safe default intent.

Valid literals (including the single-quoted Python dicts/lists the prompts
emit) must keep parsing unchanged.
"""

from unittest.mock import MagicMock, patch
import uuid

from application.graphs.main_graph import MainGraph
from application.graphs.shopping_list_graph import ShoppingListGraph
from domain.entities import GraphInvokeRequest, User


# ===========================================================================
# MainGraph
# ===========================================================================


def _sample_request(message: str = "oi") -> GraphInvokeRequest:
    uid = str(uuid.uuid4())
    user = User(id=uid, external_id=uid, name="Alice", summary="")
    return GraphInvokeRequest(message=message, user=user, memories=[], context_hints={})


def _make_main_graph() -> MainGraph:
    llm_chat = MagicMock()
    response = MagicMock()
    response.content = '["only_talking"]'
    llm_chat.invoke.return_value = response
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


class TestMainGraphClassifyLiteralSafety:
    def test_classify_intent__injection_expression__not_executed_falls_back(self):
        graph = _make_main_graph()
        # An eval() would import os and build a valid list -> misused as intent.
        graph._remove_thinking_tag = MagicMock(
            return_value="['smart_home_lights', __import__('os').getpid()]"
        )

        result = graph._classify_intent({"input": _sample_request("ligue a luz")})

        assert result["intent"] == ["only_talking"], result

    def test_classify_intent__function_call__not_executed_falls_back(self):
        graph = _make_main_graph()
        graph._remove_thinking_tag = MagicMock(return_value="[len('abc')]")

        result = graph._classify_intent({"input": _sample_request("oi")})

        assert result["intent"] == ["only_talking"], result

    def test_classify_intent__valid_literal__still_parses(self):
        graph = _make_main_graph()
        graph._remove_thinking_tag = MagicMock(return_value="['smart_home_lights']")

        result = graph._classify_intent({"input": _sample_request("ligue a luz")})

        assert result["intent"] == ["smart_home_lights"], result


# ===========================================================================
# ShoppingListGraph
# ===========================================================================


def _make_shopping_graph() -> ShoppingListGraph:
    llm_chat = MagicMock()
    with patch.object(ShoppingListGraph, "load_prompt", return_value="{input}"):
        return ShoppingListGraph(
            llm_chat=llm_chat, shopping_list_service=MagicMock()
        )


def _set_llm_content(graph: ShoppingListGraph, raw: str) -> None:
    response = MagicMock()
    response.content = raw
    graph.llm_chat.return_value = response


def _shopping_request() -> MagicMock:
    request = MagicMock()
    request.message = "test message"
    return request


class TestShoppingListGraphClassifyLiteralSafety:
    def test_classify_intent__injection_expression__not_executed_falls_back(self):
        graph = _make_shopping_graph()
        _set_llm_content(
            graph,
            "{'intents': ['add_item'], 'add_item': 'x', 'y': __import__('os').getpid()}",
        )

        result = graph._classify_intent({"input": _shopping_request()})

        assert result["intent"] == ["not_recognized"], result
        assert result["output_add_item"] is None, result

    def test_classify_intent__valid_single_quoted_literal__still_parses(self):
        graph = _make_shopping_graph()
        _set_llm_content(
            graph, "{'intents': ['add_item'], 'add_item': 'cerveja,1'}"
        )

        result = graph._classify_intent({"input": _shopping_request()})

        assert result["intent"] == ["add_item"], result
        assert result["output_add_item"] == "cerveja,1", result
