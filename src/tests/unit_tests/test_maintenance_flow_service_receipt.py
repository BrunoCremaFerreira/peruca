"""
MaintenanceFlowService receipt operations unit tests (TDD - RED phase,
plan §4.1 suite 3).

Two new operations join the PendingFlow machine (plan §3.5):

- ``register_receipt``   — slot phase, slots pre-filled by the extraction,
  missing_slots in the canonical order vehicle -> date -> km;
- ``register_receipt_confirm`` — mandatory yes/no phase, mirror of
  ``delete_confirm``: "sim"/"pode"/"confirma" confirm, "não"/"cancela" cancel,
  "sim, mas a km é 101000" is a correction (the confirmation stays armed with
  the corrected slot), and an unrelated command falls through (kind "none")
  without confirming and without swallowing the command.

Persistence reuses the generic FlowStateStore (JSON payload + embedded TTL);
the roundtrip/TTL cases here pin that contract for the new operation strings.
"""

import asyncio
import uuid

import pytest

from domain.entities import PendingFlow
from domain.services.maintenance_flow_service import (
    MaintenanceFlowService,
    SlotReplyResult,
)


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


def _service(ttl_seconds=600, repo=None):
    return MaintenanceFlowService(
        context_repository=repo or FakeContextRepository(), ttl_seconds=ttl_seconds
    )


def _receipt_slots(**overrides):
    slots = {
        "vehicle_id": "id-out",
        "vehicle_name": "Mitsubishi Outlander",
        "description": "troca de óleo e filtro",
        "date": "2026-07-10",
        "odometer_km": 100232,
    }
    slots.update(overrides)
    return slots


def _confirm_pending(slots=None):
    return PendingFlow(
        operation="register_receipt_confirm",
        slots=slots or _receipt_slots(),
        missing_slots=[],
    )


def _receipt_pending(missing, slots=None):
    return PendingFlow(
        operation="register_receipt",
        slots=slots or _receipt_slots(odometer_km=None),
        missing_slots=missing,
    )


# --------------------------------------------------------------------------- #
# Persistence roundtrip of the two new operations
# --------------------------------------------------------------------------- #
class TestReceiptPersistence:
    def test_register_receipt__set_then_get_roundtrip(self):
        service = _service()
        user_id = str(uuid.uuid4())
        pending = _receipt_pending(["km"])

        _run(service.set_pending(user_id, pending))
        loaded = _run(service.get_pending(user_id))

        assert loaded is not None
        assert loaded.operation == "register_receipt"
        assert loaded.missing_slots == ["km"]
        assert loaded.slots["vehicle_id"] == "id-out"
        assert loaded.slots["description"] == "troca de óleo e filtro"
        assert loaded.flow_domain == "maintenance"

    def test_register_receipt_confirm__set_then_get_roundtrip(self):
        service = _service()
        user_id = str(uuid.uuid4())

        _run(service.set_pending(user_id, _confirm_pending()))
        loaded = _run(service.get_pending(user_id))

        assert loaded is not None
        assert loaded.operation == "register_receipt_confirm"
        assert loaded.slots["odometer_km"] == 100232
        assert loaded.slots["date"] == "2026-07-10"

    def test_expired_receipt_pending__returns_none_and_clears(self):
        repo = FakeContextRepository()
        service = _service(ttl_seconds=-10, repo=repo)
        user_id = str(uuid.uuid4())

        _run(service.set_pending(user_id, _confirm_pending()))

        assert _run(service.get_pending(user_id)) is None
        assert repo.store == {}


# --------------------------------------------------------------------------- #
# register_receipt_confirm: yes/no parsing (mirror of delete_confirm)
# --------------------------------------------------------------------------- #
class TestRegisterReceiptConfirmReply:
    @pytest.mark.parametrize("message", ["sim", "pode", "confirma"])
    def test_affirmative_reply__confirms(self, message):
        result = _service().parse_slot_reply(_confirm_pending(), message)

        assert isinstance(result, SlotReplyResult)
        assert result.kind == "value"
        assert result.value is True

    @pytest.mark.parametrize("message", ["não", "cancela"])
    def test_negative_reply__cancels(self, message):
        result = _service().parse_slot_reply(_confirm_pending(), message)

        assert result.kind == "cancel"

    def test_yes_with_km_amendment__parsed_as_km_correction(self):
        # "Sim, mas a km é 101000" is a correction (plan §6): the confirmation
        # stays armed with the corrected slot; nothing is confirmed on this turn.
        result = _service().parse_slot_reply(
            _confirm_pending(), "sim, mas a km é 101000"
        )

        assert result.kind == "correction"
        assert result.corrected_slot == "km"
        assert result.value == 101000

    def test_unrelated_reply__falls_through_without_confirming(self):
        # A legitimate command must never be swallowed as a confirmation (§9.3).
        result = _service().parse_slot_reply(
            _confirm_pending(), "coloca 3 leites na lista"
        )

        assert result.kind == "none"


# --------------------------------------------------------------------------- #
# register_receipt: slot filling after the extraction
# --------------------------------------------------------------------------- #
class TestRegisterReceiptSlotFilling:
    def test_missing_km__numeric_reply_fills_the_slot(self):
        pending = _receipt_pending(["km"])

        result = _service().parse_slot_reply(pending, "100232")

        assert result.kind == "value"
        assert result.value == 100232
