"""
MainGraph calculator routing unit tests (TDD RED — plan §9.3).

Pattern: test_main_graph_pet_health.py. Sub-graphs and the LLM are mocked.

Contract fixed by these tests:
  - MainGraph gains a `calculator_graph` constructor parameter and a
    "calculator" node (single intent — the numeric/symbolic distinction is
    internal to the CalculatorGraph, plan §5).
  - intent ["calculator"] routes to CalculatorGraph.invoke and does NOT call
    only_talk.
  - When the sub-graph reports intent ["not_recognized"], MainGraph degrades
    to only_talk (mirrors _handle_pet_health).

IoC factory note: test_ioc_graph_cache.py covers only the Phase-1 factories —
get_pet_health_graph / get_vehicle_maintenance_graph were never added to it,
so no get_calculator_graph cache test is required here (repo precedent).
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

try:
    from application.graphs.main_graph import MainGraph
    from domain.entities import GraphInvokeRequest, User
except ImportError:
    pytest.skip("MainGraph not importable", allow_module_level=True)


def _user():
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Bruno")


def _make(calculator_result):
    llm_chat = MagicMock()
    resp = MagicMock()
    resp.content = '["calculator"]'
    llm_chat.invoke.return_value = resp
    llm_chat.return_value = resp

    only_talk = MagicMock()
    only_talk.invoke.return_value = {"output": "conversa livre"}

    calculator_graph = MagicMock()
    calculator_graph.invoke.return_value = calculator_result

    def _mk(name):
        m = MagicMock()
        m.invoke.return_value = {"output": f"{name} ok"}
        return m

    with patch.object(MainGraph, "load_prompt", return_value="{input}"):
        graph = MainGraph(
            llm_chat=llm_chat,
            only_talk_graph=only_talk,
            shopping_list_graph=_mk("shop"),
            smart_home_lights_graph=_mk("lights"),
            smart_home_climate_graph=_mk("climate"),
            smart_home_sensors_graph=_mk("sensors"),
            smart_home_cameras_graph=_mk("cams"),
            music_graph=None,
            vehicle_maintenance_graph=None,
            pet_health_graph=None,
            calculator_graph=calculator_graph,
        )
    return graph, only_talk, calculator_graph


def _req(message="quanto é 10 mais 5 vezes 2?"):
    return GraphInvokeRequest(message=message, user=_user(), context_hints={})


class TestCalculatorRouting:
    def test_routes_to_calculator_graph(self):
        graph, only_talk, calculator_graph = _make(
            {"intent": ["calculate"], "output": "10 + 5 × 2 = 30"}
        )
        result = graph.invoke(invoke_request=_req())
        assert "30" in result["output"]
        calculator_graph.invoke.assert_called_once()
        only_talk.invoke.assert_not_called()

    def test_not_recognized__falls_back_to_only_talk(self):
        graph, only_talk, calculator_graph = _make(
            {"intent": ["not_recognized"], "output": "não entendi"}
        )
        result = graph.invoke(invoke_request=_req(message="conta uma história"))
        assert "conversa livre" in result["output"]
        only_talk.invoke.assert_called_once()

    def test_symbolic_phrase__routes_to_same_calculator_node(self):
        # The numeric/symbolic distinction is internal to the sub-graph
        # (plan §5): a symbolic phrase still travels through the single
        # "calculator" node.
        graph, only_talk, calculator_graph = _make(
            {"intent": ["calculate_symbolic"], "output": "d/dx x**3 = 3*x**2"}
        )
        result = graph.invoke(
            invoke_request=_req(message="qual a derivada de x ao cubo?")
        )
        assert "3*x**2" in result["output"]
        calculator_graph.invoke.assert_called_once()
        only_talk.invoke.assert_not_called()

    def test_real_intent__does_not_call_only_talk(self):
        graph, only_talk, calculator_graph = _make(
            {"intent": ["calculate"], "output": "2 + 3 = 5"}
        )
        graph.invoke(invoke_request=_req(message="quanto é 2 mais 3?"))
        only_talk.invoke.assert_not_called()
