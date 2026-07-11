"""
CalculatorGraph classify unit tests (TDD RED) — LLM mocked.

The classifier emits JSON (json.loads) with ALL fields always present (plan §3):
    {"intents": ["calculate"|"calculate_symbolic"|"not_supported"|"not_recognized"],
     "expression": "...", "operation": "", "variable": "", "to": "", "reason": ""}

The intent string IS the StateGraph node name (intent_router returns
state["intent"] directly): calculate / calculate_symbolic / not_supported /
not_recognized. Malformed output falls back to not_recognized — never an
exception. `operation` is a closed set (integrate|diff|gradient|limit|simplify;
empty in numeric mode); an invented value falls back to not_recognized.

Pattern: test_pet_health_graph_classify_intent.py (load_prompt patched,
llm_chat=MagicMock(), classify JSON injected). CalculatorGraph does not exist
yet — it is imported lazily so this file collects and the tests fail RED.
"""

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from domain.entities import GraphInvokeRequest, User

pytest.importorskip("langgraph")


def _uuid():
    return str(uuid.uuid4())


def _user():
    return User(id=_uuid(), external_id=_uuid(), name="Bruno")


def _graph_cls():
    from application.graphs.calculator_graph import CalculatorGraph

    return CalculatorGraph


def _make_graph(symbolic_service=None, llm_content=None):
    CalculatorGraph = _graph_cls()
    llm_chat = MagicMock()
    if llm_content is not None:
        response = MagicMock()
        response.content = llm_content
        llm_chat.invoke.return_value = response
        llm_chat.return_value = response
    with patch.object(CalculatorGraph, "load_prompt", return_value="{input}"):
        graph = CalculatorGraph(
            llm_chat=llm_chat,
            symbolic_math_service=symbolic_service or MagicMock(),
        )
    return graph


def _payload(intents, expression="", operation="", variable="", to="", reason=""):
    # All fields always present — the repo-wide flat-schema pattern (plan §3).
    return json.dumps(
        {
            "intents": intents,
            "expression": expression,
            "operation": operation,
            "variable": variable,
            "to": to,
            "reason": reason,
        }
    )


def _classify(graph, user, raw_json, message="msg"):
    req = GraphInvokeRequest(message=message, user=user)
    with patch.object(graph, "_extract_structured_output", return_value=raw_json):
        return graph._classify_intent({"input": req})


class TestClassify:
    def test_numeric_phrase__routes_to_calculate_node(self):
        graph = _make_graph()
        raw = _payload(["calculate"], expression="10 + 5 * 2")
        state = _classify(graph, _user(), raw, message="quanto é 10 mais 5 vezes 2?")
        assert state["intent"] == ["calculate"]
        assert state["expression"] == "10 + 5 * 2"

    def test_symbolic_phrase__routes_to_symbolic_node(self):
        graph = _make_graph()
        raw = _payload(
            ["calculate_symbolic"],
            expression="cos(omega*x)**2",
            operation="integrate",
            variable="x",
        )
        state = _classify(graph, _user(), raw)
        assert state["intent"] == ["calculate_symbolic"]
        assert state["expression"] == "cos(omega*x)**2"
        assert state["operation"] == "integrate"
        assert state["variable"] == "x"

    def test_limit_phrase__carries_to_field(self):
        graph = _make_graph()
        raw = _payload(
            ["calculate_symbolic"],
            expression="1/x",
            operation="limit",
            variable="x",
            to="oo",
        )
        state = _classify(graph, _user(), raw)
        assert state["intent"] == ["calculate_symbolic"]
        assert state["to"] == "oo"

    def test_malformed_json__falls_back_not_recognized(self):
        graph = _make_graph()
        state = _classify(graph, _user(), "not json")
        assert state["intent"] == ["not_recognized"]

    def test_none_extract__falls_back_not_recognized(self):
        graph = _make_graph()
        state = _classify(graph, _user(), None)
        assert state["intent"] == ["not_recognized"]

    def test_explicit_not_recognized__carries_through(self):
        graph = _make_graph()
        raw = _payload(["not_recognized"])
        state = _classify(graph, _user(), raw)
        assert state["intent"] == ["not_recognized"]

    def test_not_supported__carries_reason(self):
        graph = _make_graph()
        raw = _payload(["not_supported"], reason="equation")
        state = _classify(graph, _user(), raw)
        assert state["intent"] == ["not_supported"]

    def test_think_block_response__parsed_by_real_extractor(self):
        # The extractor is NOT mocked here: exercises the real
        # _remove_thinking_tag + balanced-literal extraction path.
        content = (
            "<think>the user wants arithmetic</think>\n"
            + _payload(["calculate"], expression="2 + 3")
        )
        graph = _make_graph(llm_content=content)
        req = GraphInvokeRequest(message="quanto é 2 mais 3?", user=_user())
        state = graph._classify_intent({"input": req})
        assert state["intent"] == ["calculate"]
        assert state["expression"] == "2 + 3"

    def test_unknown_operation_value__falls_back_not_recognized(self):
        # The LLM invents "operation": "algebra" — outside the closed set,
        # the classify node degrades to not_recognized (plan §9.2).
        graph = _make_graph()
        raw = _payload(
            ["calculate_symbolic"], expression="x + 1", operation="algebra"
        )
        state = _classify(graph, _user(), raw)
        assert state["intent"] == ["not_recognized"]

    def test_percentage_phrase__routes_to_calculate(self):
        # Inversion of the original draft: percentage is now SUPPORTED and
        # goes to the numeric node, no longer not_supported (plan §9.2).
        graph = _make_graph()
        raw = _payload(["calculate"], expression="10% * 200")
        state = _classify(graph, _user(), raw, message="quanto é 10% de 200?")
        assert state["intent"] == ["calculate"]
        assert state["expression"] == "10% * 200"


class TestInvalidExpressionEndToEnd:
    def test_expression_failing_tokenizer__friendly_reply_without_stacktrace(self):
        # Full invoke: the LLM emits an expression the closed-set tokenizer
        # rejects ("10 + banana"); the graph must answer with a friendly
        # message — never raise, never leak a stack trace (plan §9.2).
        content = _payload(["calculate"], expression="10 + banana")
        graph = _make_graph(llm_content=content)
        req = GraphInvokeRequest(message="quanto é 10 mais banana?", user=_user())
        result = graph.invoke(invoke_request=req)
        assert isinstance(result["output"], str)
        assert result["output"].strip()
        assert "Traceback" not in result["output"]
        assert "ValidationError" not in result["output"]
