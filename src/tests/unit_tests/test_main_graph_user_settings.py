"""
MainGraph user_settings routing unit tests (TDD RED — plan §5/§10.6).

Mould: test_main_graph_calculator.py. Sub-graphs and the LLM are mocked.

Contract fixed by these tests:
  - MainGraph gains a `user_settings_graph` constructor parameter and a
    "user_settings" node, wired UNCONDITIONALLY (no external dependency), the
    same way the calculator node is.
  - intent ["user_settings"] routes to UserSettingsGraph.invoke and does NOT
    call only_talk.
  - When the sub-graph reports intent ["not_recognized"], MainGraph degrades to
    only_talk (mirrors _handle_pet_health) — "que horas são?" misrouted by the
    main classifier must still get a conversational answer.
  - The whole GraphInvokeRequest (including user_timezone) is forwarded to the
    sub-graph, not a rebuilt one.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

try:
    from application.graphs.main_graph import MainGraph
    from domain.entities import GraphInvokeRequest, User
except ImportError:  # pragma: no cover
    pytest.skip("MainGraph not importable", allow_module_level=True)


_TZ = "America/Sao_Paulo"


def _user():
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Bruno")


def _make(user_settings_result):
    llm_chat = MagicMock()
    resp = MagicMock()
    resp.content = '["user_settings"]'
    llm_chat.invoke.return_value = resp
    llm_chat.return_value = resp

    only_talk = MagicMock()
    only_talk.invoke.return_value = {"output": "conversa livre"}

    user_settings_graph = MagicMock()
    user_settings_graph.invoke.return_value = user_settings_result

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
            calculator_graph=None,
            user_settings_graph=user_settings_graph,
        )
    return graph, only_talk, user_settings_graph


def _req(message="altere o timezone para São Paulo"):
    return GraphInvokeRequest(
        message=message, user=_user(), context_hints={}, user_timezone=_TZ
    )


class TestUserSettingsRouting:
    def test_routes_to_user_settings_graph(self):
        graph, only_talk, user_settings_graph = _make(
            {
                "intent": ["set_timezone"],
                "output": "Pronto! Agora uso o fuso de America/Sao_Paulo (São Paulo).",
            }
        )
        result = graph.invoke(invoke_request=_req())
        assert "America/Sao_Paulo" in result["output"]
        user_settings_graph.invoke.assert_called_once()
        only_talk.invoke.assert_not_called()

    def test_get_timezone__routes_to_same_node(self):
        graph, only_talk, user_settings_graph = _make(
            {"intent": ["get_timezone"], "output": "Estou usando o fuso Europe/Lisbon."}
        )
        result = graph.invoke(
            invoke_request=_req(message="qual fuso horário está configurado?")
        )
        assert "Europe/Lisbon" in result["output"]
        user_settings_graph.invoke.assert_called_once()
        only_talk.invoke.assert_not_called()

    def test_not_recognized__falls_back_to_only_talk(self):
        graph, only_talk, user_settings_graph = _make(
            {"intent": ["not_recognized"], "output": "não entendi"}
        )
        result = graph.invoke(invoke_request=_req(message="que horas são?"))
        assert "conversa livre" in result["output"]
        only_talk.invoke.assert_called_once()

    def test_forwards_the_request_with_the_user_timezone(self):
        graph, _, user_settings_graph = _make(
            {"intent": ["get_timezone"], "output": "Estou usando o fuso X."}
        )
        request = _req(message="qual o fuso?")
        graph.invoke(invoke_request=request)
        _, kwargs = user_settings_graph.invoke.call_args
        forwarded = kwargs.get("invoke_request")
        assert forwarded is not None
        assert forwarded.user_timezone == _TZ
