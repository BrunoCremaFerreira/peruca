"""
VehicleMaintenanceGraph `register_from_receipt` node unit tests (TDD - RED
phase, plan §4.1 suite 2). The vision extractor is MOCKED — no LLM runs here.

Contract under test (plan §3.4/§3.5):

- the graph receives the extractor via constructor: ``receipt_extractor=...``;
- routing to the node is deterministic IN CODE, never trusted to the LLM:
  after the text-only classify, ``request.images`` + intent
  ``register_maintenance`` is overridden to ``register_from_receipt``; the
  inverse (a receipt intent without images) is demoted back;
- the classify textual payload never receives the base64 data URIs;
- a full extraction arms a ``register_receipt_confirm`` PendingFlow and NEVER
  persists (``maintenance_service.register`` untouched — the central
  invariant: no code path goes from receipt to persistence without the
  confirmation turn);
- gate false -> deterministic polite refusal by ``reject_reason``, no flow,
  no register;
- missing extracted slots -> ``register_receipt`` PendingFlow with
  missing_slots in the canonical order vehicle -> date -> km;
- vehicle resolution against the fleet: unique match fills the slot, multiple
  matches arm a choose_vehicle disambiguation, zero matches leave "vehicle"
  missing with a warning (never an offer to register the vehicle);
- deterministic merge: a field dictated in the USER's text beats the same
  field read from the document.
"""

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.entities import GraphInvokeRequest, User, Vehicle

pytest.importorskip("langgraph")

from application.graphs.vehicle_maintenance_graph import VehicleMaintenanceGraph


_TZ = "America/Sao_Paulo"
VALID_PNG = "data:image/png;base64,aGVsbG8="


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


def _extraction(**overrides):
    """ReceiptExtraction stand-in (plan §3.2) — a SimpleNamespace keeps this
    suite independent from the extractor module, which is mocked anyway."""
    data = dict(
        is_maintenance_document=True,
        reject_reason="",
        vehicle_term="outlander",
        performed_at=date(2026, 7, 10),
        odometer_km=100232,
        description="troca de óleo e filtro",
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def _async_flow():
    flow = MagicMock()
    flow.get_pending = AsyncMock(return_value=None)
    flow.set_pending = AsyncMock()
    flow.clear_pending = AsyncMock()
    flow.get_focus = AsyncMock(return_value=None)
    flow.set_focus = AsyncMock()
    flow.clear_focus = AsyncMock()
    return flow


def _make_graph(fleet=None, maintenance_service=None, flow_service=None,
                extractor=None):
    with patch.object(VehicleMaintenanceGraph, "load_prompt", return_value="{input}"):
        vehicle_read_repo = MagicMock()
        vehicle_read_repo.get_all_by_user_id.return_value = fleet or []
        graph = VehicleMaintenanceGraph(
            llm_chat=MagicMock(),
            vehicle_read_repository=vehicle_read_repo,
            maintenance_service=maintenance_service or MagicMock(),
            maintenance_flow_service=flow_service or _async_flow(),
            get_session_history=None,
            receipt_extractor=extractor if extractor is not None else MagicMock(),
        )
    return graph


def _req(user, message="registra essa manutenção", images=None):
    return GraphInvokeRequest(
        message=message,
        user=user,
        user_timezone=_TZ,
        images=images if images is not None else [VALID_PNG],
    )


def _register_json(vehicle_term=""):
    return (
        '{"intents": ["register_maintenance"], "vehicle_term": "%s", '
        '"description": "", "date_token": "", "date_value": "", "period": "", '
        '"odometer_km": 0, "query": "", "query_kind": "", "query_limit": 0, '
        '"edit_field": "", "new_value": ""}' % vehicle_term
    )


def _classify(graph, user, raw_json, images=None):
    req = _req(user, images=images)
    with patch.object(graph, "_extract_structured_output", return_value=raw_json):
        return graph._classify_intent({"input": req})


def _node_state(user, images=None, vehicle_term="", description="",
                performed_at=None, odometer_km=None):
    """State as the classify node leaves it: user-text slots alongside the
    request. The node merges them over the document's extraction."""
    return {
        "input": _req(user, images=images),
        "vehicle_term": vehicle_term,
        "description": description,
        "resolved_performed_at": performed_at,
        "odometer_km": odometer_km,
    }


# --------------------------------------------------------------------------- #
# Deterministic routing override (in code, never trusted to the LLM)
# --------------------------------------------------------------------------- #
class TestDeterministicRoutingOverride:
    def test_images_with_register_intent__overridden_to_register_from_receipt(self):
        user = _user()
        graph = _make_graph(fleet=_fleet(user.id))

        state = _classify(graph, user, _register_json(), images=[VALID_PNG])

        assert state["intent"] == ["register_from_receipt"]

    def test_receipt_intent_without_images__demoted_to_register_maintenance(self):
        user = _user()
        graph = _make_graph(fleet=_fleet(user.id))
        raw = _register_json().replace(
            '"register_maintenance"', '"register_from_receipt"'
        )

        state = _classify(graph, user, raw, images=[])

        assert state["intent"] == ["register_maintenance"]

    def test_classify_textual_payload__never_contains_base64(self):
        user = _user()
        graph = _make_graph(fleet=_fleet(user.id))

        captured = {}
        resp = MagicMock()
        resp.content = _register_json()
        chain_mock = MagicMock()
        chain_mock.invoke.side_effect = (
            lambda payload, *a, **k: (captured.__setitem__("payload", payload) or resp)
        )
        prompt_mock = MagicMock()
        prompt_mock.__or__.return_value = chain_mock
        graph.classification_prompt = prompt_mock

        graph._classify_intent({"input": _req(user, images=[VALID_PNG])})

        payload = captured["payload"]
        assert "images" not in payload
        assert not any("data:image" in str(v) for v in payload.values())


# --------------------------------------------------------------------------- #
# Node: full extraction -> confirmation armed, NEVER persisted on this turn
# --------------------------------------------------------------------------- #
class TestRegisterFromReceiptConfirmationInvariant:
    def test_full_extraction__arms_confirm_flow_and_never_registers(self):
        user = _user()
        maintenance = MagicMock()
        flow = _async_flow()
        extractor = MagicMock()
        extractor.extract.return_value = _extraction()
        graph = _make_graph(fleet=_fleet(user.id), maintenance_service=maintenance,
                            flow_service=flow, extractor=extractor)

        out = graph._handle_register_from_receipt(_node_state(user))

        # Central invariant: no path from receipt to persistence before "sim".
        maintenance.register.assert_not_called()
        flow.set_pending.assert_awaited()
        pending = flow.set_pending.await_args.args[1]
        assert pending.operation == "register_receipt_confirm"
        assert pending.slots["vehicle_id"] == "id-out"
        assert pending.slots["date"] == "2026-07-10"
        assert pending.slots["odometer_km"] == 100232
        # The image is read ONCE; base64 never enters the flow payload.
        assert "data:image" not in str(pending.slots)
        # Deterministic summary + confirmation question.
        assert "Outlander" in out["output_register"]
        assert "?" in out["output_register"]

    def test_image_is_read_once_by_the_extractor(self):
        user = _user()
        extractor = MagicMock()
        extractor.extract.return_value = _extraction()
        graph = _make_graph(fleet=_fleet(user.id), extractor=extractor)

        graph._handle_register_from_receipt(_node_state(user))

        extractor.extract.assert_called_once()
        assert VALID_PNG in str(extractor.extract.call_args)


# --------------------------------------------------------------------------- #
# Node: gate false -> deterministic refusal, service and flow untouched
# --------------------------------------------------------------------------- #
class TestRegisterFromReceiptGateRefusal:
    def test_gate_false__polite_refusal_no_flow_no_register(self):
        user = _user()
        maintenance = MagicMock()
        flow = _async_flow()
        extractor = MagicMock()
        extractor.extract.return_value = _extraction(
            is_maintenance_document=False,
            reject_reason="not_vehicle_maintenance",
            vehicle_term=None,
            performed_at=None,
            odometer_km=None,
            description=None,
        )
        graph = _make_graph(fleet=_fleet(user.id), maintenance_service=maintenance,
                            flow_service=flow, extractor=extractor)

        out = graph._handle_register_from_receipt(_node_state(user))

        assert out["output_register"]
        maintenance.register.assert_not_called()
        flow.set_pending.assert_not_awaited()


# --------------------------------------------------------------------------- #
# Node: missing slots -> register_receipt flow, canonical order
# --------------------------------------------------------------------------- #
class TestRegisterFromReceiptSlotFilling:
    def test_missing_date_and_km__arms_register_receipt_in_canonical_order(self):
        user = _user()
        maintenance = MagicMock()
        flow = _async_flow()
        extractor = MagicMock()
        extractor.extract.return_value = _extraction(
            performed_at=None, odometer_km=None
        )
        graph = _make_graph(fleet=_fleet(user.id), maintenance_service=maintenance,
                            flow_service=flow, extractor=extractor)

        out = graph._handle_register_from_receipt(_node_state(user))

        maintenance.register.assert_not_called()
        flow.set_pending.assert_awaited()
        pending = flow.set_pending.await_args.args[1]
        assert pending.operation == "register_receipt"
        assert pending.missing_slots == ["date", "km"]
        assert pending.slots["vehicle_id"] == "id-out"
        assert out["output_register"]

    def test_unknown_vehicle__vehicle_is_first_missing_slot_with_warning(self):
        user = _user()
        maintenance = MagicMock()
        flow = _async_flow()
        extractor = MagicMock()
        extractor.extract.return_value = _extraction(
            vehicle_term="porsche", odometer_km=None
        )
        graph = _make_graph(fleet=_fleet(user.id), maintenance_service=maintenance,
                            flow_service=flow, extractor=extractor)

        out = graph._handle_register_from_receipt(_node_state(user))

        maintenance.register.assert_not_called()
        flow.set_pending.assert_awaited()
        pending = flow.set_pending.await_args.args[1]
        assert pending.operation == "register_receipt"
        assert pending.missing_slots[0] == "vehicle"
        # Warns that the receipt's vehicle is not registered (and never offers
        # to register it — vehicle writes stay REST-only).
        assert "porsche" in out["output_register"].lower()


# --------------------------------------------------------------------------- #
# Node: ambiguous vehicle -> choose_vehicle disambiguation
# --------------------------------------------------------------------------- #
class TestRegisterFromReceiptDisambiguation:
    def test_multiple_vehicle_matches__arms_choose_vehicle(self):
        user = _user()
        maintenance = MagicMock()
        flow = _async_flow()
        extractor = MagicMock()
        extractor.extract.return_value = _extraction(vehicle_term="mitsubishi")
        graph = _make_graph(fleet=_fleet(user.id), maintenance_service=maintenance,
                            flow_service=flow, extractor=extractor)

        out = graph._handle_register_from_receipt(_node_state(user))

        maintenance.register.assert_not_called()
        flow.set_pending.assert_awaited()
        pending = flow.set_pending.await_args.args[1]
        assert pending.operation == "choose_vehicle"
        assert len(pending.candidates) == 2
        assert "Outlander" in out["output_register"]
        assert "Pajero" in out["output_register"]


# --------------------------------------------------------------------------- #
# Node: deterministic merge — the user's text beats the document
# --------------------------------------------------------------------------- #
class TestRegisterFromReceiptMerge:
    def test_user_text_vehicle_term__beats_document_vehicle_term(self):
        user = _user()
        flow = _async_flow()
        extractor = MagicMock()
        extractor.extract.return_value = _extraction(vehicle_term="outlander")
        graph = _make_graph(fleet=_fleet(user.id), flow_service=flow,
                            extractor=extractor)

        # "adiciona essa manutenção, foi no Pajero" — the spoken vehicle wins.
        state = _node_state(user, vehicle_term="pajero")
        graph._handle_register_from_receipt(state)

        flow.set_pending.assert_awaited()
        pending = flow.set_pending.await_args.args[1]
        assert pending.slots["vehicle_id"] == "id-paj"

    def test_user_text_km__beats_document_km(self):
        user = _user()
        flow = _async_flow()
        extractor = MagicMock()
        extractor.extract.return_value = _extraction(odometer_km=100232)
        graph = _make_graph(fleet=_fleet(user.id), flow_service=flow,
                            extractor=extractor)

        state = _node_state(user, odometer_km=154343)
        graph._handle_register_from_receipt(state)

        flow.set_pending.assert_awaited()
        pending = flow.set_pending.await_args.args[1]
        assert pending.slots["odometer_km"] == 154343
