"""
VehicleMaintenanceGraph handler unit tests (TDD) — LLM never runs here; handlers
are driven directly with a state dict.

Covers: list vehicles, write-forbidden fixed string (write repo never touched),
register against an unregistered / ambiguous / resolved vehicle, deterministic
query render, and the not_recognized fallback string.
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.entities import GraphInvokeRequest, MaintenanceRecord, User, Vehicle


pytest.importorskip("langgraph")

from application.graphs.vehicle_maintenance_graph import VehicleMaintenanceGraph


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


def _make_graph(fleet=None, maintenance_service=None, flow_service=None):
    with patch.object(VehicleMaintenanceGraph, "load_prompt", return_value="{input}"):
        vehicle_read_repo = MagicMock()
        vehicle_read_repo.get_all_by_user_id.return_value = fleet or []
        graph = VehicleMaintenanceGraph(
            llm_chat=MagicMock(),
            vehicle_read_repository=vehicle_read_repo,
            maintenance_service=maintenance_service or MagicMock(),
            maintenance_flow_service=flow_service or MagicMock(),
            get_session_history=None,
        )
    return graph


def _req(user, message="msg"):
    return GraphInvokeRequest(message=message, user=user)


class TestListVehicles:
    def test_lists_registered_vehicles(self):
        user = _user()
        graph = _make_graph(fleet=_fleet(user.id))
        out = graph._handle_list_vehicles({"input": _req(user)})
        text = out["output_list"]
        assert "Outlander" in text and "Pajero" in text

    def test_no_vehicles(self):
        user = _user()
        graph = _make_graph(fleet=[])
        out = graph._handle_list_vehicles({"input": _req(user)})
        assert "nenhum" in out["output_list"].lower()


class TestWriteForbidden:
    def test_returns_fixed_string_and_never_writes(self):
        user = _user()
        graph = _make_graph(fleet=_fleet(user.id))
        out = graph._handle_vehicle_write_forbidden({"input": _req(user)})
        assert out["output_forbidden"] == "Não tenho permissão para realizar esta operação"


class TestRegister:
    def _state(self, user, vehicle_term, description="troca de óleo",
               performed_at=date(2025, 10, 25), odometer_km=100000):
        return {
            "input": _req(user),
            "vehicle_term": vehicle_term,
            "description": description,
            "resolved_performed_at": performed_at,
            "odometer_km": odometer_km,
        }

    def test_unregistered_vehicle__informs_and_does_not_register(self):
        user = _user()
        maintenance = MagicMock()
        graph = _make_graph(fleet=_fleet(user.id), maintenance_service=maintenance)
        out = graph._handle_register_maintenance(self._state(user, "Porche"))
        assert "Porche" in out["output_register"]
        maintenance.register.assert_not_called()

    def test_ambiguous_vehicle__asks_and_does_not_register(self):
        user = _user()
        maintenance = MagicMock()
        flow = MagicMock()
        graph = _make_graph(fleet=_fleet(user.id), maintenance_service=maintenance,
                            flow_service=flow)
        out = graph._handle_register_maintenance(self._state(user, "mitsubishi"))
        # Asks which one and never registers.
        assert "Outlander" in out["output_register"] and "Pajero" in out["output_register"]
        maintenance.register.assert_not_called()

    def test_resolved_and_complete__registers(self):
        user = _user()
        maintenance = MagicMock()
        maintenance.register.return_value = _uuid()
        graph = _make_graph(fleet=_fleet(user.id), maintenance_service=maintenance)
        out = graph._handle_register_maintenance(self._state(user, "outlander"))
        maintenance.register.assert_called_once()
        assert "Outlander" in out["output_register"]

    def test_missing_date__asks_and_does_not_register(self):
        user = _user()
        maintenance = MagicMock()
        flow = MagicMock()
        graph = _make_graph(fleet=_fleet(user.id), maintenance_service=maintenance,
                            flow_service=flow)
        state = self._state(user, "outlander", performed_at=None)
        out = graph._handle_register_maintenance(state)
        maintenance.register.assert_not_called()
        assert out["output_register"]  # a question was produced


class TestQuery:
    def test_no_records__fixed_message_no_llm(self):
        user = _user()
        maintenance = MagicMock()
        maintenance.get_by_vehicle.return_value = []
        graph = _make_graph(fleet=_fleet(user.id), maintenance_service=maintenance)
        state = {"input": _req(user), "vehicle_term": "outlander",
                 "query_kind": "list", "query_limit": 2, "resolved_period": None,
                 "query": ""}
        out = graph._handle_query_maintenance(state)
        assert "nenhum" in out["output_query"].lower() or "não" in out["output_query"].lower()
        graph.llm_chat.assert_not_called()

    def test_list_kind__deterministic_render_no_llm(self):
        user = _user()
        maintenance = MagicMock()
        maintenance.get_by_vehicle.return_value = [
            MaintenanceRecord(id=_uuid(), vehicle_id="id-out", description="troca de óleo",
                              performed_at=date(2026, 5, 22), odometer_km=99998),
        ]
        graph = _make_graph(fleet=_fleet(user.id), maintenance_service=maintenance)
        state = {"input": _req(user), "vehicle_term": "outlander",
                 "query_kind": "list", "query_limit": 2, "resolved_period": None,
                 "query": ""}
        out = graph._handle_query_maintenance(state)
        assert "22/05/2026" in out["output_query"]
        assert "troca de óleo" in out["output_query"]
        graph.llm_chat.assert_not_called()


class TestNotRecognized:
    def test_fixed_string(self):
        user = _user()
        graph = _make_graph(fleet=[])
        out = graph._handle_not_recognized({"input": _req(user)})
        assert out["output_not_recognized"]


def _async_flow(focus=None):
    flow = MagicMock()
    flow.get_focus = AsyncMock(return_value=focus)
    flow.set_focus = AsyncMock()
    flow.set_pending = AsyncMock()
    flow.clear_focus = AsyncMock()
    return flow


def _focus():
    return {
        "record_id": "r1",
        "vehicle_id": "id-paj",
        "vehicle_name": "Mitsubishi Pajero",
        "description": "troca de óleo",
        "performed_at": "2025-12-17",
        "odometer_km": 99821,
    }


class TestFocusedQuerySetsFocus:
    def test_query_stores_top_record_as_focus(self):
        user = _user()
        maintenance = MagicMock()
        maintenance.get_by_vehicle.return_value = [
            MaintenanceRecord(id="r-top", vehicle_id="id-out", description="troca de óleo",
                              performed_at=date(2026, 5, 22), odometer_km=99998),
        ]
        flow = _async_flow()
        graph = _make_graph(fleet=_fleet(user.id), maintenance_service=maintenance,
                            flow_service=flow)
        state = {"input": _req(user), "vehicle_term": "outlander",
                 "query_kind": "list", "query_limit": 1, "resolved_period": None,
                 "query": ""}
        graph._handle_query_maintenance(state)
        flow.set_focus.assert_awaited()
        stored = flow.set_focus.await_args.args[1]
        assert stored["record_id"] == "r-top"


class TestQueryLimitCap:
    def test_huge_query_limit_is_capped_to_20(self):
        user = _user()
        maintenance = MagicMock()
        maintenance.get_by_vehicle.return_value = [
            MaintenanceRecord(id=f"r{i}", vehicle_id="id-out", description="troca",
                              performed_at=date(2026, 1, 1), odometer_km=1000 + i)
            for i in range(50)
        ]
        graph = _make_graph(fleet=_fleet(user.id), maintenance_service=maintenance)
        state = {"input": _req(user), "vehicle_term": "outlander",
                 "query_kind": "list", "query_limit": 100000, "resolved_period": None,
                 "query": ""}
        out = graph._handle_query_maintenance(state)
        # Never fetches more than the hard ceiling from the store...
        assert maintenance.get_by_vehicle.call_args.kwargs["limit"] == 20
        # ...and never renders more than the hard ceiling, whatever the LLM emitted.
        assert out["output_query"].count("\n- ") <= 20


class TestEdit:
    def test_edit_km_applies_update(self):
        user = _user()
        maintenance = MagicMock()
        flow = _async_flow(focus=_focus())
        graph = _make_graph(fleet=_fleet(user.id), maintenance_service=maintenance,
                            flow_service=flow)
        state = {"input": _req(user), "edit_field": "quilometragem",
                 "new_value": "100821"}
        out = graph._handle_edit_maintenance(state)
        maintenance.update.assert_called_once()
        update_arg = maintenance.update.call_args.args[0]
        assert update_arg.id == "r1"
        assert update_arg.odometer_km == 100821
        assert "100821" in out["output_edit"]

    def test_edit_without_focus_asks(self):
        user = _user()
        maintenance = MagicMock()
        flow = _async_flow(focus=None)
        graph = _make_graph(fleet=_fleet(user.id), maintenance_service=maintenance,
                            flow_service=flow)
        out = graph._handle_edit_maintenance(
            {"input": _req(user), "edit_field": "km", "new_value": "1"}
        )
        maintenance.update.assert_not_called()
        assert out["output_edit"]


class TestDelete:
    def test_delete_with_focus_asks_confirmation_and_stores_pending(self):
        user = _user()
        maintenance = MagicMock()
        flow = _async_flow(focus=_focus())
        graph = _make_graph(fleet=_fleet(user.id), maintenance_service=maintenance,
                            flow_service=flow)
        out = graph._handle_delete_maintenance({"input": _req(user)})
        # Never deletes on this turn; asks and stores a delete_confirm flow.
        maintenance.delete.assert_not_called()
        flow.set_pending.assert_awaited()
        pending = flow.set_pending.await_args.args[1]
        assert pending.operation == "delete_confirm"
        assert pending.slots["record_id"] == "r1"
        assert "?" in out["output_delete"]

    def test_delete_without_focus_asks(self):
        user = _user()
        flow = _async_flow(focus=None)
        graph = _make_graph(fleet=_fleet(user.id), flow_service=flow)
        out = graph._handle_delete_maintenance({"input": _req(user)})
        assert out["output_delete"]
        flow.set_pending.assert_not_awaited()
