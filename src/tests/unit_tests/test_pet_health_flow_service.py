"""
PetHealthFlowService unit tests (TDD — written before implementation, Fase A).

The service persists a PendingFlow (flow_domain="pet_health") + a focused record
between turns via the generic FlowStateStore, and resolves the user's next reply
deterministically via parse_slot_reply — the §9.3 conservative parser plus the
"tomou mais alguma?" loop (register_more, §2.6).

parse_slot_reply(pending, message, pets=None) -> SlotReplyResult
    kind ∈ {value, cancel, invalid, choose, affirm, none}
"""

import asyncio
import uuid
from datetime import date, timedelta

from domain.entities import DisambiguationCandidate, PendingFlow, Pet
from domain.services.pet_health_flow_service import (
    PetHealthFlowService,
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
    return PetHealthFlowService(
        context_repository=repo or FakeContextRepository(), ttl_seconds=ttl_seconds
    )


def _pending_register(missing, slots=None):
    return PendingFlow(
        operation="register",
        slots=slots or {},
        missing_slots=missing,
        flow_domain="pet_health",
    )


def _pets():
    uid = str(uuid.uuid4())
    return [
        Pet(id="p-caco", user_id=uid, name="Caçolin", nicknames=["Lilo", "Suzu"]),
        Pet(id="p-cacao", user_id=uid, name="Caçolão", nicknames=["Lyon"]),
    ]


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
class TestPersistence:
    def test_set_then_get_roundtrip(self):
        service = _service()
        user_id = str(uuid.uuid4())
        pending = _pending_register(
            ["event_name"], {"pet_id": "p-caco", "pet_name": "Caçolin"}
        )

        _run(service.set_pending(user_id, pending))
        loaded = _run(service.get_pending(user_id))

        assert loaded is not None
        assert loaded.operation == "register"
        assert loaded.missing_slots == ["event_name"]
        assert loaded.slots.get("pet_name") == "Caçolin"

    def test_get_without_set_returns_none(self):
        assert _run(_service().get_pending(str(uuid.uuid4()))) is None

    def test_reconstructed_pending_has_pet_health_flow_domain(self):
        service = _service()
        user_id = str(uuid.uuid4())
        _run(service.set_pending(user_id, _pending_register(["date"])))

        loaded = _run(service.get_pending(user_id))
        assert loaded.flow_domain == "pet_health"

    def test_expired__returns_none_and_clears(self):
        repo = FakeContextRepository()
        service = _service(ttl_seconds=-10, repo=repo)
        user_id = str(uuid.uuid4())
        _run(service.set_pending(user_id, _pending_register(["date"])))

        assert _run(service.get_pending(user_id)) is None
        assert repo.store == {}

    def test_clear_pending(self):
        service = _service()
        user_id = str(uuid.uuid4())
        _run(service.set_pending(user_id, _pending_register(["date"])))
        _run(service.clear_pending(user_id))
        assert _run(service.get_pending(user_id)) is None


# --------------------------------------------------------------------------- #
# Focused record (§2.7)
# --------------------------------------------------------------------------- #
class TestFocus:
    def _focus(self):
        return {
            "record_id": "e1",
            "pet_id": "p-caco",
            "pet_name": "Caçolin",
            "event_type": "vaccine",
            "description": "DHPPI",
            "occurred_at": "2026-02-20",
        }

    def test_set_then_get_focus_roundtrip(self):
        service = _service()
        user_id = str(uuid.uuid4())
        _run(service.set_focus(user_id, self._focus()))
        loaded = _run(service.get_focus(user_id))
        assert loaded is not None
        assert loaded["record_id"] == "e1"
        assert loaded["description"] == "DHPPI"

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
# event_name slot (the only open-text slot — §2.5)
# --------------------------------------------------------------------------- #
class TestParseEventName:
    def _p(self):
        return _pending_register(
            ["event_name"], {"pet_id": "p-caco", "pet_name": "Caçolin",
                             "date": "2026-07-05"}
        )

    def test_bare_name__value_preserved(self):
        r = _service().parse_slot_reply(self._p(), "DHPPI")
        assert r.kind == "value"
        assert r.value == "DHPPI"

    def test_name_with_fillers__value_preserving_casing(self):
        r = _service().parse_slot_reply(self._p(), "a vacina DHPPI")
        assert r.kind == "value"
        assert r.value == "DHPPI"

    def test_empty_after_fillers__none(self):
        r = _service().parse_slot_reply(self._p(), "a vacina")
        assert r.kind == "none"

    def test_too_many_tokens__none(self):
        r = _service().parse_slot_reply(
            self._p(), "quero registrar sete oito nove dez onze doze"
        )
        assert r.kind == "none"

    def test_cancel__cancel(self):
        r = _service().parse_slot_reply(self._p(), "cancela")
        assert r.kind == "cancel"


# --------------------------------------------------------------------------- #
# date slot
# --------------------------------------------------------------------------- #
class TestParseDate:
    def _p(self):
        return _pending_register(
            ["date"], {"pet_id": "p-caco", "pet_name": "Caçolin",
                       "event_name": "DHPPI"}
        )

    def test_ontem__value_yesterday(self):
        r = _service().parse_slot_reply(self._p(), "ontem")
        assert r.kind == "value"
        assert r.value == date.today() - timedelta(days=1)

    def test_hoje__value_today(self):
        r = _service().parse_slot_reply(self._p(), "hoje")
        assert r.kind == "value"
        assert r.value == date.today()

    def test_explicit_past_date__value(self):
        r = _service().parse_slot_reply(self._p(), "22/05/2020")
        assert r.kind == "value"
        assert r.value == date(2020, 5, 22)

    def test_explicit_future_date__invalid_keeps_pending(self):
        future = (date.today() + timedelta(days=5)).strftime("%d/%m/%Y")
        r = _service().parse_slot_reply(self._p(), future)
        assert r.kind == "invalid"
        assert r.error_message

    def test_unrelated_message__none(self):
        r = _service().parse_slot_reply(self._p(), "liga a luz da sala")
        assert r.kind == "none"


# --------------------------------------------------------------------------- #
# pet slot
# --------------------------------------------------------------------------- #
class TestParsePet:
    def _p(self):
        return _pending_register(
            ["pet"], {"event_name": "DHPPI", "date": "2026-07-05"}
        )

    def test_single_match_by_name__value(self):
        r = _service().parse_slot_reply(self._p(), "caçolin", pets=_pets())
        assert r.kind == "value"
        assert r.value.id == "p-caco"

    def test_single_match_by_nickname__value(self):
        r = _service().parse_slot_reply(self._p(), "Lyon", pets=_pets())
        assert r.kind == "value"
        assert r.value.id == "p-cacao"

    def test_ambiguous__choose(self):
        uid = str(uuid.uuid4())
        pets = [
            Pet(id="g1", user_id=uid, name="Gato Preto"),
            Pet(id="g2", user_id=uid, name="Gato Branco"),
        ]
        r = _service().parse_slot_reply(self._p(), "gato", pets=pets)
        assert r.kind == "choose"
        assert len(r.value) == 2

    def test_no_match__none(self):
        r = _service().parse_slot_reply(self._p(), "Rex", pets=_pets())
        assert r.kind == "none"

    def test_too_many_tokens__none(self):
        r = _service().parse_slot_reply(
            self._p(), "acho que era o cachorro lá de casa mesmo", pets=_pets()
        )
        assert r.kind == "none"


# --------------------------------------------------------------------------- #
# delete_confirm
# --------------------------------------------------------------------------- #
class TestConfirmation:
    def _p(self):
        return PendingFlow(
            operation="delete_confirm", slots={"record_id": "e1"},
            flow_domain="pet_health",
        )

    def test_pure_yes__value_true(self):
        r = _service().parse_slot_reply(self._p(), "sim")
        assert r.kind == "value"
        assert r.value is True

    def test_nao__cancel(self):
        r = _service().parse_slot_reply(self._p(), "não")
        assert r.kind == "cancel"

    def test_mixed_message__none(self):
        r = _service().parse_slot_reply(self._p(), "sim, mas antes acende a luz")
        assert r.kind == "none"


# --------------------------------------------------------------------------- #
# choose_pet (ordinal / name / nickname)
# --------------------------------------------------------------------------- #
class TestChoosePet:
    def _p(self):
        return PendingFlow(
            operation="choose_pet",
            slots={"event_name": "DHPPI", "date": "2026-07-05"},
            candidates=[
                DisambiguationCandidate(id="p-caco", name="Caçolin"),
                DisambiguationCandidate(id="p-cacao", name="Caçolão"),
            ],
            flow_domain="pet_health",
        )

    def test_ordinal__matches_candidate(self):
        r = _service().parse_slot_reply(self._p(), "o segundo")
        assert r.kind == "value"
        assert r.value.id == "p-cacao"

    def test_name__matches_candidate(self):
        r = _service().parse_slot_reply(self._p(), "Caçolão")
        assert r.kind == "value"
        assert r.value.id == "p-cacao"

    def test_nickname__matches_candidate(self):
        r = _service().parse_slot_reply(self._p(), "Lyon", pets=_pets())
        assert r.kind == "value"
        assert r.value.id == "p-cacao"

    def test_cancel__cancel(self):
        r = _service().parse_slot_reply(self._p(), "cancela")
        assert r.kind == "cancel"

    def test_unrelated__none(self):
        r = _service().parse_slot_reply(self._p(), "acende a luz")
        assert r.kind == "none"


# --------------------------------------------------------------------------- #
# register_more loop (§2.6)
# --------------------------------------------------------------------------- #
class TestRegisterMore:
    def _p(self):
        return PendingFlow(
            operation="register_more",
            slots={"pet_id": "p-caco", "pet_name": "Caçolin",
                   "date": "2026-07-05", "event_type": "vaccine"},
            flow_domain="pet_health",
        )

    def test_so_esta__cancel(self):
        r = _service().parse_slot_reply(self._p(), "só esta")
        assert r.kind == "cancel"

    def test_nao__cancel(self):
        r = _service().parse_slot_reply(self._p(), "não")
        assert r.kind == "cancel"

    def test_por_enquanto_nao__cancel(self):
        r = _service().parse_slot_reply(self._p(), "por enquanto não")
        assert r.kind == "cancel"

    def test_bare_yes__affirm(self):
        r = _service().parse_slot_reply(self._p(), "sim")
        assert r.kind == "affirm"

    def test_bare_tomou__affirm(self):
        r = _service().parse_slot_reply(self._p(), "tomou")
        assert r.kind == "affirm"

    def test_yes_with_content__value_is_event_name(self):
        r = _service().parse_slot_reply(self._p(), "sim, a raiva")
        assert r.kind == "value"
        assert r.value == "raiva"

    def test_changed_subject__none(self):
        r = _service().parse_slot_reply(self._p(), "liga a luz da sala")
        assert r.kind == "none"


# --------------------------------------------------------------------------- #
# Result type contract
# --------------------------------------------------------------------------- #
class TestResultType:
    def test_parse_returns_slot_reply_result(self):
        p = _pending_register(["event_name"], {"pet_id": "p", "pet_name": "x"})
        r = _service().parse_slot_reply(p, "DHPPI")
        assert isinstance(r, SlotReplyResult)


# --------------------------------------------------------------------------- #
# Date reference injected by the caller (plan §8.4 / §10.6)
#
# Same fix as MaintenanceFlowService: `_parse_date` must stop reading the SERVER's
# date and take the reference from the caller, which passes the user's LOCAL date.
#
#     parse_slot_reply(pending, message, pets=None, reference: date = None)
# --------------------------------------------------------------------------- #
class TestDateReference:
    def _p(self):
        return _pending_register(
            ["date"], {"pet_id": "p1", "pet_name": "Caçolin", "event_name": "raiva"}
        )

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
        reference = date(2026, 7, 9)
        r = _service().parse_slot_reply(self._p(), "10/07/2026", reference=reference)
        assert r.kind == "invalid"

    def test_reference_day_itself__is_not_in_the_future(self):
        reference = date(2026, 7, 9)
        r = _service().parse_slot_reply(self._p(), "09/07/2026", reference=reference)
        assert r.kind == "value"
        assert r.value == reference

    def test_no_reference__falls_back_to_the_server_date(self):
        r = _service().parse_slot_reply(self._p(), "hoje")
        assert r.kind == "value"
        assert r.value == date.today()
