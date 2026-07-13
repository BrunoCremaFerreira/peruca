"""
PetHealthGraph handler unit tests (TDD) — LLM never runs here; handlers are
driven directly with a state dict.
"""

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from domain.entities import GraphInvokeRequest, Pet, PetHealthEvent, User


pytest.importorskip("langgraph")

from application.graphs.pet_health_graph import PetHealthGraph


_TZ = "America/Sao_Paulo"


def _uuid():
    return str(uuid.uuid4())


def _user():
    return User(id=_uuid(), external_id=_uuid(), name="Bruno")


def _pets(user_id):
    return [
        Pet(id="id-caco", user_id=user_id, name="Caçolin", nicknames=["Lilo", "Suzu"]),
        Pet(id="id-cacao", user_id=user_id, name="Caçolão", nicknames=["Lyon"]),
    ]


def _make_graph(pets=None, health_service=None, flow_service=None):
    with patch.object(PetHealthGraph, "load_prompt", return_value="{input}"):
        pet_read_repo = MagicMock()
        pet_read_repo.get_all_by_user_id.return_value = pets or []
        graph = PetHealthGraph(
            llm_chat=MagicMock(),
            pet_read_repository=pet_read_repo,
            pet_health_service=health_service or MagicMock(),
            pet_health_flow_service=flow_service or MagicMock(),
            get_session_history=None,
        )
    return graph


def _req(user, message="msg"):
    return GraphInvokeRequest(message=message, user=user, user_timezone=_TZ)


class TestListPets:
    def test_lists_registered_pets(self):
        user = _user()
        graph = _make_graph(pets=_pets(user.id))
        out = graph._handle_list_pets({"input": _req(user)})
        assert "Caçolin" in out["output_list"] and "Caçolão" in out["output_list"]

    def test_no_pets(self):
        user = _user()
        graph = _make_graph(pets=[])
        out = graph._handle_list_pets({"input": _req(user)})
        assert "nenhum" in out["output_list"].lower()


class TestWriteForbidden:
    def test_returns_fixed_string(self):
        user = _user()
        graph = _make_graph(pets=_pets(user.id))
        out = graph._handle_pet_write_forbidden({"input": _req(user)})
        assert out["output_forbidden"] == "Não tenho permissão para realizar esta operação"


class TestRegister:
    def _state(self, user, pet_term, event_type="vaccine", event_name="DHPPI",
               occurred_at=date(2026, 2, 20)):
        return {
            "input": _req(user),
            "pet_term": pet_term,
            "event_type": event_type,
            "event_name": event_name,
            "resolved_occurred_at": occurred_at,
        }

    def test_unregistered_pet__informs_and_does_not_register(self):
        user = _user()
        health = MagicMock()
        graph = _make_graph(pets=_pets(user.id), health_service=health)
        out = graph._handle_register_health_event(self._state(user, "Rex"))
        assert "Rex" in out["output_register"]
        health.register.assert_not_called()

    def test_ambiguous_pet__asks_and_stores_choose(self):
        user = _user()
        pets = [
            Pet(id="g1", user_id=user.id, name="Gato Preto"),
            Pet(id="g2", user_id=user.id, name="Gato Branco"),
        ]
        health = MagicMock()
        flow = MagicMock()
        graph = _make_graph(pets=pets, health_service=health, flow_service=flow)
        out = graph._handle_register_health_event(self._state(user, "gato"))
        assert "Gato Preto" in out["output_register"] and "Gato Branco" in out["output_register"]
        health.register.assert_not_called()

    def test_resolved_and_complete__registers(self):
        user = _user()
        health = MagicMock()
        health.register.return_value = _uuid()
        graph = _make_graph(pets=_pets(user.id), health_service=health)
        out = graph._handle_register_health_event(self._state(user, "caçolin"))
        health.register.assert_called_once()
        assert "Caçolin" in out["output_register"]

    def test_direct_complete_vaccine__does_not_ask_more(self):
        # Direct registration (EX2) confirms and ends — no "tomou mais alguma?".
        user = _user()
        health = MagicMock()
        graph = _make_graph(pets=_pets(user.id), health_service=health)
        out = graph._handle_register_health_event(self._state(user, "caçolin"))
        assert "mais alguma" not in out["output_register"].lower()

    def test_missing_event_name__asks_which_vaccine(self):
        user = _user()
        flow = MagicMock()
        graph = _make_graph(pets=_pets(user.id), flow_service=flow)
        out = graph._handle_register_health_event(
            self._state(user, "caçolin", event_name="")
        )
        assert "vacina" in out["output_register"].lower()
        flow.set_pending.assert_called()

    def test_missing_date__asks_when(self):
        user = _user()
        flow = MagicMock()
        graph = _make_graph(pets=_pets(user.id), flow_service=flow)
        out = graph._handle_register_health_event(
            self._state(user, "caçolin", occurred_at=None)
        )
        assert "quando" in out["output_register"].lower()

    def test_missing_pet__asks_which_pet(self):
        user = _user()
        flow = MagicMock()
        graph = _make_graph(pets=_pets(user.id), flow_service=flow)
        out = graph._handle_register_health_event(self._state(user, ""))
        assert "pet" in out["output_register"].lower()


class TestQuery:
    def test_no_records__message_without_llm(self):
        user = _user()
        health = MagicMock()
        health.get_by_pet.return_value = []
        graph = _make_graph(pets=_pets(user.id), health_service=health)
        out = graph._handle_query_health_event(
            {"input": _req(user), "pet_term": "caçolin", "query_kind": "list"}
        )
        assert "Caçolin" in out["output_query"]
        graph.llm_chat.assert_not_called()

    def test_list_render_and_sets_focus(self):
        user = _user()
        health = MagicMock()
        rec = PetHealthEvent(id="e1", pet_id="id-caco", event_type="vaccine",
                             description="DHPPI", occurred_at=date(2026, 2, 20))
        health.get_by_pet.return_value = [rec]
        flow = MagicMock()
        graph = _make_graph(pets=_pets(user.id), health_service=health, flow_service=flow)
        out = graph._handle_query_health_event(
            {"input": _req(user), "pet_term": "caçolin", "query_kind": "list"}
        )
        assert "DHPPI" in out["output_query"]
        flow.set_focus.assert_called_once()

    def test_query_limit_capped_at_20(self):
        user = _user()
        health = MagicMock()
        health.get_by_pet.return_value = [
            PetHealthEvent(id=str(i), pet_id="id-caco", event_type="vaccine",
                           description=f"v{i}", occurred_at=date(2026, 1, 1))
            for i in range(30)
        ]
        graph = _make_graph(pets=_pets(user.id), health_service=health)
        graph._handle_query_health_event(
            {"input": _req(user), "pet_term": "caçolin", "query_kind": "list",
             "query_limit": 100}
        )
        # The service is asked for at most the hard ceiling.
        _, kwargs = health.get_by_pet.call_args
        assert kwargs.get("limit") == 20


class TestDelete:
    def test_no_focus__asks_to_query_first(self):
        user = _user()
        flow = MagicMock()
        flow.get_focus.return_value = None
        graph = _make_graph(pets=_pets(user.id), flow_service=flow)
        with patch("application.graphs.pet_health_graph.async_runner.run",
                   return_value=None):
            out = graph._handle_delete_health_event({"input": _req(user)})
        assert "Consulte" in out["output_delete"] or "consulte" in out["output_delete"]

    def test_with_focus__asks_confirmation_and_stores_flow(self):
        user = _user()
        flow = MagicMock()
        focus = {"record_id": "e1", "pet_name": "Caçolin", "description": "DHPPI",
                 "occurred_at": "2026-02-20"}
        graph = _make_graph(pets=_pets(user.id), flow_service=flow)
        with patch("application.graphs.pet_health_graph.async_runner.run",
                   return_value=focus):
            out = graph._handle_delete_health_event({"input": _req(user)})
        assert "DHPPI" in out["output_delete"]
        flow.set_pending.assert_called()


class TestNotRecognized:
    def test_returns_message(self):
        user = _user()
        graph = _make_graph(pets=_pets(user.id))
        out = graph._handle_not_recognized({"input": _req(user)})
        assert isinstance(out["output_not_recognized"], str)
        assert out["output_not_recognized"].strip()
