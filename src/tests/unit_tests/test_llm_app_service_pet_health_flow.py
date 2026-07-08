"""
LlmAppService pet-health flow short-circuit (§9.3) + user_pets hints (§2.9) +
the "tomou mais alguma?" loop (§2.6).

A pending pet-health flow is consumed deterministically before the MainGraph;
a reply that does not parse falls through. Dispatch is by flow_domain: a pending
maintenance flow is never consumed by the pet consumer and vice-versa.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

from application.appservices.llm_app_service import LlmAppService
from application.appservices.view_models import ChatRequest
from domain.entities import Pet, PendingFlow, User
from domain.services.pet_health_flow_service import SlotReplyResult


def _user():
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Bruno")


def _make(user, pending, slot_result, pets=None):
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
    flow.clear_focus = AsyncMock()
    flow.parse_slot_reply = MagicMock(return_value=slot_result)

    pet_health_service = MagicMock()

    pet_read_repository = MagicMock()
    pet_read_repository.get_all_by_user_id.return_value = pets or []

    service = LlmAppService(
        main_graph=main_graph,
        context_repository=MagicMock(),
        user_repository=user_repository,
        user_memory_service=user_memory_service,
        disambiguation_service=None,
        maintenance_flow_service=None,
        pet_health_flow_service=flow,
        pet_health_service=pet_health_service,
        pet_read_repository=pet_read_repository,
    )
    return service, main_graph, flow, pet_health_service


def _req(user, message):
    return ChatRequest(message=message, external_user_id=user.external_id, chat_id="c1")


class TestRegisterCompletion:
    def test_event_name_reply_completes_without_main_graph(self):
        user = _user()
        pending = PendingFlow(
            operation="register",
            slots={"pet_id": "p1", "pet_name": "Caçolin", "event_type": "vaccine",
                   "date": "2026-07-05"},
            missing_slots=["event_name"],
            flow_domain="pet_health",
        )
        result = SlotReplyResult(kind="value", value="DHPPI")
        service, main_graph, flow, health = _make(user, pending, result)

        out = service.chat(_req(user, "DHPPI"))

        assert out["intents"] == ["pet_health"]
        health.register.assert_called_once()
        main_graph.invoke.assert_not_called()
        # Vaccine -> arms the register_more loop.
        assert "mais alguma" in out["output"].lower()


class TestRegisterMoreLoop:
    def test_so_esta_ends_loop_without_main_graph(self):
        user = _user()
        pending = PendingFlow(
            operation="register_more",
            slots={"pet_id": "p1", "pet_name": "Caçolin", "event_type": "vaccine",
                   "date": "2026-07-05"},
            flow_domain="pet_health",
        )
        result = SlotReplyResult(kind="cancel")
        service, main_graph, flow, health = _make(user, pending, result)

        out = service.chat(_req(user, "só esta"))

        main_graph.invoke.assert_not_called()
        flow.clear_pending.assert_awaited()
        assert "perfeito" in out["output"].lower()

    def test_bare_yes_asks_for_next_vaccine(self):
        user = _user()
        pending = PendingFlow(
            operation="register_more",
            slots={"pet_id": "p1", "pet_name": "Caçolin", "event_type": "vaccine",
                   "date": "2026-07-05"},
            flow_domain="pet_health",
        )
        result = SlotReplyResult(kind="affirm")
        service, main_graph, flow, health = _make(user, pending, result)

        out = service.chat(_req(user, "sim"))

        assert "vacina" in out["output"].lower()
        health.register.assert_not_called()
        flow.set_pending.assert_awaited()

    def test_yes_with_content_registers_directly(self):
        user = _user()
        pending = PendingFlow(
            operation="register_more",
            slots={"pet_id": "p1", "pet_name": "Caçolin", "event_type": "vaccine",
                   "date": "2026-07-05"},
            flow_domain="pet_health",
        )
        result = SlotReplyResult(kind="value", value="raiva")
        service, main_graph, flow, health = _make(user, pending, result)

        service.chat(_req(user, "sim, a raiva"))

        health.register.assert_called_once()


class TestFallthrough:
    def test_unrelated_reply_falls_through_to_main_graph(self):
        user = _user()
        pending = PendingFlow(
            operation="register", missing_slots=["date"], flow_domain="pet_health"
        )
        result = SlotReplyResult(kind="none")
        service, main_graph, flow, health = _make(user, pending, result)

        service.chat(_req(user, "acende a luz da sala"))

        main_graph.invoke.assert_called_once()
        health.register.assert_not_called()


class TestDeleteConfirm:
    def test_confirmed_deletes_focused_record(self):
        user = _user()
        pending = PendingFlow(
            operation="delete_confirm", slots={"record_id": "r1"},
            flow_domain="pet_health",
        )
        result = SlotReplyResult(kind="value", value=True)
        service, main_graph, flow, health = _make(user, pending, result)

        out = service.chat(_req(user, "sim"))

        health.delete.assert_called_once_with("r1", user.id)
        assert out["intents"] == ["pet_health"]


class TestUserPetsHint:
    def test_hint_and_persona_populated_on_main_graph_route(self):
        user = _user()
        pets = [Pet(id="p1", user_id=user.id, name="Caçolin",
                    nicknames=["Lilo", "Suzu"], description="preguiçoso")]
        service, main_graph, flow, health = _make(
            user, None, SlotReplyResult(kind="none"), pets=pets
        )

        service.chat(_req(user, "quais são os meus pets?"))

        hints = main_graph.invoke.call_args.kwargs["invoke_request"].context_hints
        assert "Caçolin" in hints["user_pets"]
        assert "Lilo" in hints["user_pets"]
        assert "Caçolin" in hints["user_pets_persona"]
        assert "preguiçoso" in hints["user_pets_persona"]
