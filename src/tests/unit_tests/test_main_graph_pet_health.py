"""
MainGraph pet-health routing + not_recognized -> only_talk fallback (§9.1).
Sub-graphs and the LLM are mocked.
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


def _make(pet_result):
    llm_chat = MagicMock()
    resp = MagicMock()
    resp.content = '["pet_health"]'
    llm_chat.invoke.return_value = resp
    llm_chat.return_value = resp

    only_talk = MagicMock()
    only_talk.invoke.return_value = {"output": "conversa livre"}

    pet_graph = MagicMock()
    pet_graph.invoke.return_value = pet_result

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
            pet_health_graph=pet_graph,
        )
    return graph, only_talk, pet_graph


def _req():
    return GraphInvokeRequest(
        message="o Caçolin tomou vacina hoje", user=_user(), context_hints={}
    )


class TestPetHealthRouting:
    def test_routes_to_pet_graph(self):
        graph, only_talk, pet_graph = _make(
            {"intent": ["register_health_event"], "output": "Registrei"}
        )
        result = graph.invoke(invoke_request=_req())
        assert "Registrei" in result["output"]
        pet_graph.invoke.assert_called_once()
        only_talk.invoke.assert_not_called()

    def test_not_recognized__falls_back_to_only_talk(self):
        graph, only_talk, pet_graph = _make(
            {"intent": ["not_recognized"], "output": "não entendi"}
        )
        result = graph.invoke(invoke_request=_req())
        assert "conversa livre" in result["output"]
        only_talk.invoke.assert_called_once()

    def test_real_intent__does_not_call_only_talk(self):
        graph, only_talk, pet_graph = _make(
            {"intent": ["list_pets"], "output": "Os seus pets são..."}
        )
        graph.invoke(invoke_request=_req())
        only_talk.invoke.assert_not_called()
