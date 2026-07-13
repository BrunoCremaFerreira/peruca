"""
MaintenanceFlowService unit tests (TDD — written before implementation).

The service persists a PendingMaintenanceFlow (JSON payload + embedded TTL,
mirroring DisambiguationService) and resolves the user's next reply
deterministically via parse_slot_reply — the §9.3 conservative parser that keeps
a legitimate command ("coloca 3 leites na lista") from being swallowed as a slot.

parse_slot_reply(pending, message, vehicles=None) -> SlotReplyResult
    kind ∈ {value, skip, cancel, invalid, correction, choose, none}
"""

import asyncio
import uuid
from datetime import date, timedelta

from domain.entities import (
    DisambiguationCandidate,
    PendingMaintenanceFlow,
    Vehicle,
)
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


def _pending_register(missing, slots=None):
    return PendingMaintenanceFlow(
        operation="register", slots=slots or {}, missing_slots=missing
    )


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
class TestPersistence:
    def test_set_then_get_roundtrip(self):
        service = _service()
        user_id = str(uuid.uuid4())
        pending = _pending_register(["date", "km"], {"description": "troca de pneus"})

        _run(service.set_pending(user_id, pending))
        loaded = _run(service.get_pending(user_id))

        assert loaded is not None
        assert loaded.operation == "register"
        assert loaded.missing_slots == ["date", "km"]
        assert loaded.slots.get("description") == "troca de pneus"

    def test_get_without_set_returns_none(self):
        service = _service()
        assert _run(service.get_pending(str(uuid.uuid4()))) is None

    def test_reconstructed_pending_has_maintenance_flow_domain(self):
        service = _service()
        user_id = str(uuid.uuid4())
        _run(service.set_pending(user_id, _pending_register(["km"])))

        loaded = _run(service.get_pending(user_id))
        assert loaded.flow_domain == "maintenance"

    def test_expired__returns_none_and_clears(self):
        repo = FakeContextRepository()
        service = _service(ttl_seconds=-10, repo=repo)
        user_id = str(uuid.uuid4())
        _run(service.set_pending(user_id, _pending_register(["km"])))

        assert _run(service.get_pending(user_id)) is None
        assert repo.store == {}


# --------------------------------------------------------------------------- #
# km slot
# --------------------------------------------------------------------------- #
class TestParseKm:
    def _p(self):
        return _pending_register(["km"], {"description": "x", "vehicle_id": "v"})

    def test_plain_number__value(self):
        r = _service().parse_slot_reply(self._p(), "100232")
        assert r.kind == "value"
        assert r.value == 100232

    def test_with_unit_and_filler__value(self):
        r = _service().parse_slot_reply(self._p(), "estava com 100.232 km")
        assert r.kind == "value"
        assert r.value == 100232

    def test_n_mil__multiplied(self):
        r = _service().parse_slot_reply(self._p(), "uns 98 mil")
        assert r.kind == "value"
        assert r.value == 98000

    def test_shopping_message_with_digit__none(self):
        r = _service().parse_slot_reply(self._p(), "coloca 3 leites na lista")
        assert r.kind == "none"

    def test_two_numbers__none(self):
        r = _service().parse_slot_reply(self._p(), "acho que era 100 ou 110")
        assert r.kind == "none"

    def test_dont_know__skip(self):
        r = _service().parse_slot_reply(self._p(), "não sei")
        assert r.kind == "skip"


# --------------------------------------------------------------------------- #
# date slot
# --------------------------------------------------------------------------- #
class TestParseDate:
    def _p(self):
        return _pending_register(["date"], {"description": "x", "vehicle_id": "v"})

    def test_ontem__value_yesterday(self):
        r = _service().parse_slot_reply(self._p(), "ontem")
        assert r.kind == "value"
        assert r.value == date.today() - timedelta(days=1)

    def test_explicit_past_date__value(self):
        r = _service().parse_slot_reply(self._p(), "foi dia 10/01/2020")
        assert r.kind == "value"
        assert r.value == date(2020, 1, 10)

    def test_future_date__invalid_keeps_pending(self):
        future = (date.today() + timedelta(days=1)).strftime("%d/%m/%Y")
        r = _service().parse_slot_reply(self._p(), future)
        assert r.kind == "invalid"
        assert r.error_message

    def test_natural_language_future__none(self):
        r = _service().parse_slot_reply(self._p(), "amanhã")
        assert r.kind == "none"

    def test_unrelated_message__none(self):
        r = _service().parse_slot_reply(self._p(), "acende a luz da sala")
        assert r.kind == "none"


# --------------------------------------------------------------------------- #
# correction
# --------------------------------------------------------------------------- #
class TestCorrection:
    def test_date_correction_while_awaiting_km(self):
        pending = _pending_register(
            ["km"], {"description": "x", "vehicle_id": "v", "date": "2026-01-01"}
        )
        r = _service().parse_slot_reply(pending, "na verdade foi ontem")
        assert r.kind == "correction"
        assert r.corrected_slot == "date"
        assert r.value == date.today() - timedelta(days=1)


# --------------------------------------------------------------------------- #
# confirmation (delete_confirm)
# --------------------------------------------------------------------------- #
class TestConfirmation:
    def _p(self):
        return PendingMaintenanceFlow(
            operation="delete_confirm", slots={"record_id": "r"}
        )

    def test_pure_yes__value_true(self):
        r = _service().parse_slot_reply(self._p(), "sim")
        assert r.kind == "value"
        assert r.value is True

    def test_pode_remover__value_true(self):
        r = _service().parse_slot_reply(self._p(), "pode remover")
        assert r.kind == "value"
        assert r.value is True

    def test_nao__cancel(self):
        r = _service().parse_slot_reply(self._p(), "não")
        assert r.kind == "cancel"

    def test_mixed_message__none(self):
        r = _service().parse_slot_reply(self._p(), "sim, mas antes acende a luz")
        assert r.kind == "none"


# --------------------------------------------------------------------------- #
# choose_vehicle
# --------------------------------------------------------------------------- #
class TestChooseVehicle:
    def _p(self):
        return PendingMaintenanceFlow(
            operation="choose_vehicle",
            slots={"description": "troca de óleo"},
            candidates=[
                DisambiguationCandidate(id="id-out", name="Mitsubishi Outlander"),
                DisambiguationCandidate(id="id-paj", name="Mitsubishi Pajero"),
            ],
        )

    def test_ordinal__matches_candidate(self):
        r = _service().parse_slot_reply(self._p(), "o segundo")
        assert r.kind == "value"
        assert r.value.id == "id-paj"

    def test_name__matches_candidate(self):
        r = _service().parse_slot_reply(self._p(), "pajero")
        assert r.kind == "value"
        assert r.value.id == "id-paj"

    def test_unrelated__none(self):
        r = _service().parse_slot_reply(self._p(), "acende a luz")
        assert r.kind == "none"


# --------------------------------------------------------------------------- #
# vehicle slot + top-level cancel
# --------------------------------------------------------------------------- #
class TestVehicleSlot:
    def _fleet(self):
        uid = str(uuid.uuid4())
        return [
            Vehicle(id="id-out", user_id=uid, name="Mitsubishi Outlander",
                    brand="Mitsubishi", model="Outlander", year=2018),
            Vehicle(id="id-paj", user_id=uid, name="Mitsubishi Pajero",
                    brand="Mitsubishi", model="Pajero", year=2015),
        ]

    def test_single_match__value(self):
        p = _pending_register(["vehicle"], {"description": "x"})
        r = _service().parse_slot_reply(p, "do outlander", vehicles=self._fleet())
        assert r.kind == "value"
        assert r.value.id == "id-out"

    def test_ambiguous__choose(self):
        p = _pending_register(["vehicle"], {"description": "x"})
        r = _service().parse_slot_reply(p, "mitsubishi", vehicles=self._fleet())
        assert r.kind == "choose"
        assert len(r.value) == 2

    def test_no_match__none(self):
        p = _pending_register(["vehicle"], {"description": "x"})
        r = _service().parse_slot_reply(p, "põe leite na lista", vehicles=self._fleet())
        assert r.kind == "none"


class TestTopLevelCancel:
    def test_cancel_while_awaiting_km(self):
        p = _pending_register(["km"], {"description": "x", "vehicle_id": "v"})
        r = _service().parse_slot_reply(p, "cancela")
        assert isinstance(r, SlotReplyResult)
        assert r.kind == "cancel"


# --------------------------------------------------------------------------- #
# Focused record (§2.7)
# --------------------------------------------------------------------------- #
class TestFocus:
    def _focus(self):
        return {
            "record_id": "r1",
            "vehicle_id": "v1",
            "vehicle_name": "Mitsubishi Pajero",
            "description": "troca de óleo",
            "performed_at": "2025-12-17",
            "odometer_km": 99821,
        }

    def test_set_then_get_focus_roundtrip(self):
        service = _service()
        user_id = str(uuid.uuid4())
        _run(service.set_focus(user_id, self._focus()))
        loaded = _run(service.get_focus(user_id))
        assert loaded is not None
        assert loaded["record_id"] == "r1"
        assert loaded["odometer_km"] == 99821

    def test_get_focus_without_set_returns_none(self):
        assert _run(_service().get_focus(str(uuid.uuid4()))) is None

    def test_expired_focus_returns_none_and_clears(self):
        repo = FakeContextRepository()
        service = _service(ttl_seconds=-10, repo=repo)
        user_id = str(uuid.uuid4())
        _run(service.set_focus(user_id, self._focus()))
        assert _run(service.get_focus(user_id)) is None
        assert repo.store == {}

    def test_clear_focus(self):
        service = _service()
        user_id = str(uuid.uuid4())
        _run(service.set_focus(user_id, self._focus()))
        _run(service.clear_focus(user_id))
        assert _run(service.get_focus(user_id)) is None


# --------------------------------------------------------------------------- #
# Date reference injected by the caller (plan §8.4 / §10.6)
#
# `_parse_date` had `reference = date.today()` baked in — the SERVER's date. The
# multi-turn flow would resolve "ontem" in the server's timezone even after the
# graphs were fixed. The reference becomes a parameter, and LlmAppService passes
# the user's LOCAL date:
#
#     parse_slot_reply(pending, message, vehicles=None, reference: date = None)
#
# `reference=None` keeps today's behaviour (date.today()) so nothing else breaks.
# --------------------------------------------------------------------------- #
class TestDateReference:
    def _p(self):
        return _pending_register(["date"], {"vehicle_id": "v1", "description": "óleo"})

    def test_today_token__resolves_against_the_given_reference(self):
        reference = date(2026, 7, 9)
        r = _service().parse_slot_reply(self._p(), "hoje", reference=reference)
        assert r.kind == "value"
        assert r.value == reference

    def test_yesterday_token__resolves_against_the_given_reference(self):
        reference = date(2026, 7, 9)
        r = _service().parse_slot_reply(self._p(), "ontem", reference=reference)
        assert r.kind == "value"
        assert r.value == reference - timedelta(days=1)

    def test_future_guard__is_relative_to_the_given_reference(self):
        # A date the SERVER already considers past can still be in the user's
        # future (and vice-versa): the guard must use the injected reference.
        reference = date(2026, 7, 9)
        r = _service().parse_slot_reply(
            self._p(), "10/07/2026", reference=reference
        )
        assert r.kind == "invalid"

    def test_reference_day_itself__is_not_in_the_future(self):
        reference = date(2026, 7, 9)
        r = _service().parse_slot_reply(
            self._p(), "09/07/2026", reference=reference
        )
        assert r.kind == "value"
        assert r.value == reference

    def test_no_reference__falls_back_to_the_server_date(self):
        r = _service().parse_slot_reply(self._p(), "hoje")
        assert r.kind == "value"
        assert r.value == date.today()
