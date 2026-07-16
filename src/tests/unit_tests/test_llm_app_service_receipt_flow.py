"""
LlmAppService receipt-flow orchestration unit tests (TDD - RED phase,
plan §4.1 suite 4). MainGraph is mocked; the REAL MaintenanceFlowService runs
over a FakeContextRepository so the tests exercise the actual dispatch of the
new ``register_receipt_confirm`` operation (plan §3.5), not a mocked parse.

Contract under test:

- a pending ``register_receipt_confirm`` + "sim" registers the maintenance
  (via MaintenanceService.register, unchanged) WITHOUT invoking the MainGraph
  and clears the pending flow;
- "não" clears the flow and persists NOTHING;
- an invalid image raises ValidationError before ANY graph runs (fail-fast
  gate, regression pin in the receipt context);
- ``_persist_turn`` never receives base64 — the history stays clean even when
  the confirmation turn carries image attachments.
"""

import asyncio
import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest

from application.appservices.llm_app_service import LlmAppService
from application.appservices.view_models import ChatRequest
from domain.entities import PendingFlow, User, Vehicle
from domain.exceptions import ValidationError
from domain.services.maintenance_flow_service import MaintenanceFlowService


VALID_PNG = "data:image/png;base64,aGVsbG8="


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class FakeContextRepository:
    def __init__(self):
        self.store: dict = {}

    def connect(self):
        pass

    async def set_key(self, key, value):
        self.store[key] = value

    async def get_key(self, key):
        return self.store.get(key)

    async def delete_key(self, key):
        return self.store.pop(key, None) is not None


def _user():
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Bruno")


def _fleet(user_id):
    return [
        Vehicle(id="id-out", user_id=user_id, name="Mitsubishi Outlander",
                brand="Mitsubishi", model="Outlander", year=2018),
    ]


def _confirm_slots(**overrides):
    slots = {
        "vehicle_id": "id-out",
        "vehicle_name": "Mitsubishi Outlander",
        "description": "troca de óleo e filtro",
        "date": "2026-07-10",
        "odometer_km": 100232,
    }
    slots.update(overrides)
    return slots


def _make_service(user):
    main_graph = MagicMock()
    main_graph.invoke.return_value = {"output": "roteado", "intent": ["only_talking"]}

    user_repository = MagicMock()
    user_repository.get_by_external_id.return_value = user

    user_memory_service = MagicMock()
    user_memory_service.get_all_by_user.return_value = []

    history = MagicMock()
    get_session_history = MagicMock(return_value=history)

    flow_service = MaintenanceFlowService(
        context_repository=FakeContextRepository(), ttl_seconds=600
    )

    maintenance_service = MagicMock()

    vehicle_read_repository = MagicMock()
    vehicle_read_repository.get_all_by_user_id.return_value = _fleet(user.id)

    service = LlmAppService(
        main_graph=main_graph,
        context_repository=MagicMock(),
        user_repository=user_repository,
        user_memory_service=user_memory_service,
        get_session_history=get_session_history,
        maintenance_flow_service=flow_service,
        maintenance_service=maintenance_service,
        vehicle_read_repository=vehicle_read_repository,
    )
    return service, main_graph, flow_service, maintenance_service, history


def _arm_confirm(flow_service, user, slots=None):
    _run(
        flow_service.set_pending(
            user.id,
            PendingFlow(
                operation="register_receipt_confirm",
                slots=slots or _confirm_slots(),
                missing_slots=[],
            ),
        )
    )


def _req(user, message, images=None):
    return ChatRequest(
        message=message,
        external_user_id=user.external_id,
        chat_id="c1",
        images=images or [],
    )


class TestConfirmYes:
    def test_pending_confirm_plus_yes__registers_without_main_graph(self):
        user = _user()
        service, main_graph, flow_service, maintenance, _ = _make_service(user)
        _arm_confirm(flow_service, user)

        out = service.chat(_req(user, "sim"))

        maintenance.register.assert_called_once()
        command = maintenance.register.call_args.args[0]
        assert command.vehicle_id == "id-out"
        assert command.description == "troca de óleo e filtro"
        assert command.performed_at == date(2026, 7, 10)
        assert command.odometer_km == 100232
        assert maintenance.register.call_args.args[1] == user.id
        main_graph.invoke.assert_not_called()
        assert out["intents"] == ["vehicle_maintenance"]
        assert out["output"]
        # The consumed flow is gone: the next turn routes normally.
        assert _run(flow_service.get_pending(user.id)) is None


class TestConfirmNo:
    def test_pending_confirm_plus_no__clears_flow_and_persists_nothing(self):
        user = _user()
        service, main_graph, flow_service, maintenance, _ = _make_service(user)
        _arm_confirm(flow_service, user)

        out = service.chat(_req(user, "não"))

        maintenance.register.assert_not_called()
        main_graph.invoke.assert_not_called()
        assert out["intents"] == ["vehicle_maintenance"]
        assert _run(flow_service.get_pending(user.id)) is None


class TestInvalidImageFailFast:
    def test_invalid_image__validation_error_before_any_graph(self):
        user = _user()
        service, main_graph, flow_service, maintenance, _ = _make_service(user)
        _arm_confirm(flow_service, user)

        with pytest.raises(ValidationError):
            service.chat(_req(user, "sim", images=["not-a-data-uri"]))

        main_graph.invoke.assert_not_called()
        maintenance.register.assert_not_called()


class TestPersistTurnNeverReceivesBase64:
    def test_confirmation_turn_with_images__history_has_no_base64(self):
        user = _user()
        service, main_graph, flow_service, maintenance, history = _make_service(user)
        _arm_confirm(flow_service, user)

        out = service.chat(_req(user, "sim", images=[VALID_PNG]))

        # The reply is consumed by the flow, not rerouted through the MainGraph.
        main_graph.invoke.assert_not_called()
        assert out["intents"] == ["vehicle_maintenance"]

        history.add_messages.assert_called_once()
        messages = history.add_messages.call_args.args[0]
        blob = "".join(str(getattr(m, "content", "")) for m in messages)
        assert "data:image" not in blob
        assert "base64" not in blob
        assert "aGVsbG8=" not in blob
