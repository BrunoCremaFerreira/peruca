"""
CalculatorGraph handler unit tests (TDD RED) — the LLM never runs here.

Action nodes are 100% deterministic (plan §4.1): `calculate` delegates to the
pure domain function calculator_service.evaluate_expression; the
`calculate_symbolic` node delegates to the injected SymbolicMathService; both
format by template WITHOUT a second LLM call, prefix their output with
CALCULATOR_RESULT_HEADER (markers.py — merge bypass, plan §7), and render
numbers in pt-BR (comma decimal, trailing-zero trim: Decimal("20") -> "20").

Handler contract driven by these tests (pet-health pattern — handlers called
directly with a state dict):
    _handle_calculate(state)           -> {"output_calculate": str}
    _handle_calculate_symbolic(state)  -> {"output_symbolic": str}
    _handle_not_supported(state)       -> {"output_not_supported": str}
    _handle_not_recognized(state)      -> {"output_not_recognized": str}

CalculatorGraph and the marker do not exist yet — imported lazily so this file
collects and the tests fail RED.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from domain.entities import GraphInvokeRequest, User
from domain.exceptions import ValidationError

pytest.importorskip("langgraph")


def _uuid():
    return str(uuid.uuid4())


def _user():
    return User(id=_uuid(), external_id=_uuid(), name="Bruno")


def _req(user, message="msg"):
    return GraphInvokeRequest(message=message, user=user)


def _graph_cls():
    from application.graphs.calculator_graph import CalculatorGraph

    return CalculatorGraph


def _header():
    from application.graphs.markers import CALCULATOR_RESULT_HEADER

    return CALCULATOR_RESULT_HEADER


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


def _assert_llm_not_called(graph):
    # Action nodes never spend a second LLM call (plan §4.1).
    graph.llm_chat.invoke.assert_not_called()
    assert not graph.llm_chat.called


class TestCalculateNode:
    def _state(self, expression):
        return {"input": _req(_user()), "expression": expression}

    def test_delegates_to_service_and_formats_result(self):
        graph = _make_graph()
        out = graph._handle_calculate(self._state("10 + 5 * 2"))
        # Sequential fold: (10 + 5) * 2 = 30.
        assert "30" in out["output_calculate"]

    def test_llm_not_called_in_action_node(self):
        graph = _make_graph()
        graph._handle_calculate(self._state("2 + 3"))
        _assert_llm_not_called(graph)

    def test_integer_result__trims_decimals(self):
        # Decimal("20") is rendered "20" — never "20.000000" (plan §4.4).
        graph = _make_graph()
        out = graph._handle_calculate(self._state("10 + 10"))
        assert "20" in out["output_calculate"]
        assert "20.0" not in out["output_calculate"]
        assert "20,0" not in out["output_calculate"]

    def test_decimal_result__formatted_with_pt_br_comma(self):
        graph = _make_graph()
        out = graph._handle_calculate(self._state("10 / 4"))
        assert "2,5" in out["output_calculate"]

    def test_output_prefixed_with_calculator_result_header(self):
        # The merge bypass (plan §7) keys on this marker.
        graph = _make_graph()
        out = graph._handle_calculate(self._state("2 + 3"))
        assert out["output_calculate"].startswith(_header())

    def test_division_by_zero__friendly_message(self):
        graph = _make_graph()
        out = graph._handle_calculate(self._state("10 / 0"))
        assert out["output_calculate"].strip()
        assert "zero" in out["output_calculate"].lower()
        assert "Traceback" not in out["output_calculate"]
        _assert_llm_not_called(graph)

    def test_math_domain_error__friendly_message(self):
        # sqrt of a negative / log of zero -> fixed friendly template,
        # never the exception class name or a stack trace.
        graph = _make_graph()
        out = graph._handle_calculate(self._state("sqrt(-4)"))
        assert out["output_calculate"].strip()
        assert "MathDomainError" not in out["output_calculate"]
        assert "Traceback" not in out["output_calculate"]

    def test_empty_expression__asks_for_complete_expression(self):
        # "soma 5" arrives structurally incomplete (plan §4.2): the node
        # answers by template asking for the full expression — no LLM call,
        # no exception.
        graph = _make_graph()
        out = graph._handle_calculate(self._state(""))
        assert isinstance(out["output_calculate"], str)
        assert out["output_calculate"].strip()
        _assert_llm_not_called(graph)


class TestCalculateSymbolicNode:
    def _state(self, operation="integrate", expression="x**2", variable="x", to=""):
        return {
            "input": _req(_user()),
            "operation": operation,
            "expression": expression,
            "variable": variable,
            "to": to,
        }

    def test_delegates_to_symbolic_service_with_extracted_slots(self):
        service = MagicMock()
        service.evaluate.return_value = "x**3/3"
        graph = _make_graph(symbolic_service=service)
        out = graph._handle_calculate_symbolic(self._state())
        service.evaluate.assert_called_once_with(
            operation="integrate", expression="x**2", variable="x", to=""
        )
        assert "3" in out["output_symbolic"]

    def test_llm_not_called_in_symbolic_node(self):
        service = MagicMock()
        service.evaluate.return_value = "2*x"
        graph = _make_graph(symbolic_service=service)
        graph._handle_calculate_symbolic(self._state(operation="diff"))
        _assert_llm_not_called(graph)

    def test_symbolic_node__formats_result_deterministically(self):
        # Assert stable fragments, never the full SymPy string (its term
        # order changes between versions — plan §4.4/§9.5); and the exact
        # same input formats to the exact same output (no LLM in the path).
        service = MagicMock()
        service.evaluate.return_value = "x/2 + sin(2*w*x)/(4*w)"
        graph = _make_graph(symbolic_service=service)
        first = graph._handle_calculate_symbolic(self._state(expression="cos(w*x)**2"))
        second = graph._handle_calculate_symbolic(self._state(expression="cos(w*x)**2"))
        assert "sin" in first["output_symbolic"]
        assert first["output_symbolic"] == second["output_symbolic"]

    def test_symbolic_output__prefixed_with_calculator_result_header(self):
        # The §7 merge bypass covers BOTH action nodes.
        service = MagicMock()
        service.evaluate.return_value = "2*x"
        graph = _make_graph(symbolic_service=service)
        out = graph._handle_calculate_symbolic(self._state(operation="diff"))
        assert out["output_symbolic"].startswith(_header())

    def test_symbolic_node__validation_error_from_hostile_string__friendly_message_no_stacktrace(self):
        service = MagicMock()
        service.evaluate.side_effect = ValidationError(errors=["expression rejected"])
        graph = _make_graph(symbolic_service=service)
        out = graph._handle_calculate_symbolic(
            self._state(operation="simplify", expression="__import__('os')")
        )
        assert out["output_symbolic"].strip()
        assert "Traceback" not in out["output_symbolic"]
        assert "ValidationError" not in out["output_symbolic"]
        _assert_llm_not_called(graph)

    def test_symbolic_node__timeout_error__friendly_message(self):
        import domain.exceptions as domain_exceptions

        service = MagicMock()
        service.evaluate.side_effect = domain_exceptions.CalculationTimeoutError(
            errors=["calculation timed out"]
        )
        graph = _make_graph(symbolic_service=service)
        out = graph._handle_calculate_symbolic(self._state())
        assert out["output_symbolic"].strip()
        assert "Traceback" not in out["output_symbolic"]

    def test_symbolic_node__no_closed_form_error__friendly_message(self):
        import domain.exceptions as domain_exceptions

        service = MagicMock()
        service.evaluate.side_effect = domain_exceptions.NoClosedFormError(
            errors=["no closed form"]
        )
        graph = _make_graph(symbolic_service=service)
        out = graph._handle_calculate_symbolic(self._state(expression="x**x"))
        assert out["output_symbolic"].strip()
        assert "Traceback" not in out["output_symbolic"]


class TestNotSupportedNode:
    def test_returns_friendly_message(self):
        graph = _make_graph()
        out = graph._handle_not_supported(
            {"input": _req(_user()), "reason": "equation"}
        )
        assert isinstance(out["output_not_supported"], str)
        assert out["output_not_supported"].strip()


class TestNotRecognizedNode:
    def test_returns_message(self):
        graph = _make_graph()
        out = graph._handle_not_recognized({"input": _req(_user())})
        assert isinstance(out["output_not_recognized"], str)
        assert out["output_not_recognized"].strip()


class TestInvokeContract:
    def test_invoke__not_recognized__exposes_intent_for_main_graph_fallback(self):
        # MainGraph._handle_calculator inspects result["intent"] to trigger
        # the not_recognized -> only_talk fallback (plan §5) — the sub-graph
        # must expose it alongside "output", like vehicle/pet graphs do.
        import json

        content = json.dumps(
            {
                "intents": ["not_recognized"],
                "expression": "",
                "operation": "",
                "variable": "",
                "to": "",
                "reason": "",
            }
        )
        graph = _make_graph(llm_content=content)
        result = graph.invoke(
            invoke_request=_req(_user(), message="conta uma história")
        )
        assert result["intent"] == ["not_recognized"]
        assert isinstance(result["output"], str)
