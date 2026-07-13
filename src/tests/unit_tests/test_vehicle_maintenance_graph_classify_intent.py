"""
VehicleMaintenanceGraph classify unit tests (TDD) — LLM mocked.

The classifier emits JSON (json.loads); the node parses intents + slots, resolves
the dictated date via date_resolver and the vehicle term in Python. Malformed
output falls back to not_recognized.
"""

import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from domain.services.clock import local_date_for_user
from domain.entities import GraphInvokeRequest, User, Vehicle

pytest.importorskip("langgraph")

from application.graphs.vehicle_maintenance_graph import VehicleMaintenanceGraph


_TZ = "America/Sao_Paulo"


def _uuid():
    return str(uuid.uuid4())


def _user():
    return User(id=_uuid(), external_id=_uuid(), name="Bruno")


def _fleet(user_id):
    return [
        Vehicle(id="id-out", user_id=user_id, name="Mitsubishi Outlander",
                brand="Mitsubishi", model="Outlander", year=2018),
        Vehicle(id="id-paj", user_id=user_id, name="Mitsubishi Pajero",
                brand="Mitsubishi", model="Pajero", year=2015),
    ]


def _make_graph(fleet):
    with patch.object(VehicleMaintenanceGraph, "load_prompt", return_value="{input}"):
        vehicle_read_repo = MagicMock()
        vehicle_read_repo.get_all_by_user_id.return_value = fleet
        graph = VehicleMaintenanceGraph(
            llm_chat=MagicMock(),
            vehicle_read_repository=vehicle_read_repo,
            maintenance_service=MagicMock(),
            maintenance_flow_service=MagicMock(),
            get_session_history=None,
        )
    return graph


def _classify(graph, user, raw_json):
    req = GraphInvokeRequest(message="msg", user=user, user_timezone=_TZ)
    with patch.object(graph, "_extract_structured_output", return_value=raw_json):
        return graph._classify_intent({"input": req})


class TestClassify:
    def test_register_with_token_date_resolves(self):
        user = _user()
        graph = _make_graph(_fleet(user.id))
        raw = (
            '{"intents": ["register_maintenance"], "vehicle_term": "outlander", '
            '"description": "troca de óleo", "date_token": "yesterday", '
            '"date_value": "", "period": "", "odometer_km": 100232, "query": "", '
            '"query_kind": "", "query_limit": 0, "edit_field": "", "new_value": ""}'
        )
        state = _classify(graph, user, raw)
        assert state["intent"] == ["register_maintenance"]
        # The reference is the USER's civil date (request.user_timezone), not the
        # server's — see test_vehicle_maintenance_graph_timezone.py.
        assert state["resolved_performed_at"] == local_date_for_user(_TZ) - timedelta(
            days=1
        )
        assert state["odometer_km"] == 100232
        assert len(state["matched_vehicles"]) == 1
        assert state["matched_vehicles"][0].id == "id-out"

    def test_register_with_explicit_date(self):
        user = _user()
        graph = _make_graph(_fleet(user.id))
        raw = (
            '{"intents": ["register_maintenance"], "vehicle_term": "pajero", '
            '"description": "pneus", "date_token": "", "date_value": "2020-01-10", '
            '"period": "", "odometer_km": 0, "query": "", "query_kind": "", '
            '"query_limit": 0, "edit_field": "", "new_value": ""}'
        )
        state = _classify(graph, user, raw)
        assert state["resolved_performed_at"] == date(2020, 1, 10)

    def test_list_vehicles(self):
        user = _user()
        graph = _make_graph(_fleet(user.id))
        raw = '{"intents": ["list_vehicles"], "vehicle_term": "", "description": ""}'
        state = _classify(graph, user, raw)
        assert state["intent"] == ["list_vehicles"]

    def test_write_forbidden(self):
        user = _user()
        graph = _make_graph(_fleet(user.id))
        raw = '{"intents": ["vehicle_write_forbidden"], "vehicle_term": "corolla"}'
        state = _classify(graph, user, raw)
        assert state["intent"] == ["vehicle_write_forbidden"]

    def test_malformed_json__not_recognized(self):
        user = _user()
        graph = _make_graph(_fleet(user.id))
        state = _classify(graph, user, "not json")
        assert state["intent"] == ["not_recognized"]

    def test_none_extract__not_recognized(self):
        user = _user()
        graph = _make_graph(_fleet(user.id))
        state = _classify(graph, user, None)
        assert state["intent"] == ["not_recognized"]

    def test_query_kind_carried(self):
        user = _user()
        graph = _make_graph(_fleet(user.id))
        raw = (
            '{"intents": ["query_maintenance"], "vehicle_term": "outlander", '
            '"query": "quando troquei o óleo", "query_kind": "open", "query_limit": 1}'
        )
        state = _classify(graph, user, raw)
        assert state["intent"] == ["query_maintenance"]
        assert state["query_kind"] == "open"
