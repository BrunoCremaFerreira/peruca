"""
LlmAppService maintenance-flow short-circuit (§9.3) + user_vehicles hint (§2.5).

A pending flow is consumed deterministically before the MainGraph; a reply that
does not parse falls through with the original message. The context hint always
carries the user's vehicle names for the classifier.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

from application.appservices.llm_app_service import LlmAppService
from application.appservices.view_models import ChatRequest
from domain.entities import PendingMaintenanceFlow, User, Vehicle
from domain.services.maintenance_flow_service import SlotReplyResult


def _user():
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Bruno")


def _make(user, pending, slot_result, fleet=None):
    main_graph = MagicMock()
    main_graph.invoke.return_value = {"output": "roteado", "intent": ["only_talking"]}

    user_repository = MagicMock()
    user_repository.get_by_external_id.return_value = user

    user_memory_service = MagicMock()
    user_memory_service.get_all_by_user.return_value = []

    flow = MagicMock()
    flow.get_pending = AsyncMock(return_value=pending)
    flow.set_pending = AsyncMock()
    flow.clear_pending = AsyncMock()
    flow.parse_slot_reply = MagicMock(return_value=slot_result)

    maintenance_service = MagicMock()

    vehicle_read_repository = MagicMock()
    vehicle_read_repository.get_all_by_user_id.return_value = fleet or []

    service = LlmAppService(
        main_graph=main_graph,
        context_repository=MagicMock(),
        user_repository=user_repository,
        user_memory_service=user_memory_service,
        disambiguation_service=None,
        maintenance_flow_service=flow,
        maintenance_service=maintenance_service,
        vehicle_read_repository=vehicle_read_repository,
    )
    return service, main_graph, flow, maintenance_service


def _req(user, message):
    return ChatRequest(message=message, external_user_id=user.external_id, chat_id="c1")


class TestRegisterCompletion:
    def test_km_reply_completes_registration_without_main_graph(self):
        user = _user()
        pending = PendingMaintenanceFlow(
            operation="register",
            slots={"description": "troca de óleo", "vehicle_id": "v1",
                   "vehicle_name": "Mitsubishi Outlander", "date": "2026-07-05"},
            missing_slots=["km"],
        )
        result = SlotReplyResult(kind="value", value=101127)
        service, main_graph, flow, maintenance = _make(user, pending, result)

        out = service.chat(_req(user, "101127"))

        assert out["intents"] == ["vehicle_maintenance"]
        maintenance.register.assert_called_once()
        main_graph.invoke.assert_not_called()
        flow.clear_pending.assert_awaited()


class TestFallthrough:
    def test_unrelated_reply_falls_through_to_main_graph(self):
        user = _user()
        pending = PendingMaintenanceFlow(operation="register", missing_slots=["km"])
        result = SlotReplyResult(kind="none")
        service, main_graph, flow, maintenance = _make(user, pending, result)

        service.chat(_req(user, "acende a luz da sala"))

        main_graph.invoke.assert_called_once()
        maintenance.register.assert_not_called()


class TestDeleteConfirm:
    def test_mixed_message_does_not_delete(self):
        user = _user()
        pending = PendingMaintenanceFlow(
            operation="delete_confirm", slots={"record_id": "r1"}
        )
        result = SlotReplyResult(kind="none")
        service, main_graph, flow, maintenance = _make(user, pending, result)

        service.chat(_req(user, "sim, mas antes acende a luz"))

        maintenance.delete.assert_not_called()

    def test_confirmed_deletes_focused_record(self):
        user = _user()
        pending = PendingMaintenanceFlow(
            operation="delete_confirm", slots={"record_id": "r1"}
        )
        result = SlotReplyResult(kind="value", value=True)
        service, main_graph, flow, maintenance = _make(user, pending, result)

        out = service.chat(_req(user, "sim"))

        maintenance.delete.assert_called_once_with("r1", user.id)
        main_graph.invoke.assert_not_called()
        assert out["intents"] == ["vehicle_maintenance"]


class TestUserVehiclesHint:
    def test_hint_populated_on_main_graph_route(self):
        user = _user()
        fleet = [Vehicle(id="v1", user_id=user.id, name="Mitsubishi Outlander",
                         brand="Mitsubishi", model="Outlander", year=2018)]
        # No pending flow -> straight to MainGraph.
        service, main_graph, flow, maintenance = _make(
            user, None, SlotReplyResult(kind="none"), fleet=fleet
        )

        service.chat(_req(user, "quais são os meus veículos?"))

        invoke_request = main_graph.invoke.call_args.kwargs["invoke_request"]
        assert invoke_request.context_hints["user_vehicles"] == "Mitsubishi Outlander"
