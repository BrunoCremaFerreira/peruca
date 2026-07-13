"""
PetHealthService unit tests (TDD — written before implementation, Fase A / RED).

PetHealthService registers/updates/deletes health events and reads them back per
pet. Every operation validates the target pet's ownership before touching data (a
pet_id from LLM output or a stale pending flow must never reach another user's
records). It also enforces the cross-entity rule: an event may not predate the
pet's birth_date (§2.8) — only when birth_date is set.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from domain.commands import PetHealthEventAdd, PetHealthEventUpdate
from domain.entities import Pet, PetHealthEvent
from domain.exceptions import NofFoundValidationError, ValidationError
from domain.services.pet_health_service import PetHealthService


def _uuid() -> str:
    return str(uuid.uuid4())


def _pet(user_id, birth_date=None) -> Pet:
    return Pet(id=_uuid(), user_id=user_id, name="Caçolin", nicknames=["Lilo"],
               birth_date=birth_date, sex="male", species="dog")


def _event(pet_id) -> PetHealthEvent:
    return PetHealthEvent(id=_uuid(), pet_id=pet_id, event_type="vaccine",
                          description="DHPPI", occurred_at=date(2026, 2, 20))


def _make():
    event_repo = MagicMock()
    event_repo.get_by_id.return_value = None
    event_repo.get_all_by_pet_id.return_value = []
    pet_read_repo = MagicMock()
    pet_read_repo.get_by_id.return_value = None
    return event_repo, pet_read_repo


class TestRegister:
    def test_register_valid__returns_uuid_and_persists(self):
        event_repo, pet_read_repo = _make()
        user_id = _uuid()
        pet = _pet(user_id, birth_date=date(2020, 1, 1))
        pet_read_repo.get_by_id.return_value = pet
        service = PetHealthService(event_repo, pet_read_repo)

        new_id = service.register(
            PetHealthEventAdd(pet_id=pet.id, event_type="vaccine",
                              description="DHPPI", occurred_at=date(2026, 2, 20)),
            user_id,
        )

        assert uuid.UUID(new_id)
        event_repo.add.assert_called_once()

    def test_register_unknown_pet__raises_and_does_not_persist(self):
        event_repo, pet_read_repo = _make()
        pet_read_repo.get_by_id.return_value = None
        service = PetHealthService(event_repo, pet_read_repo)
        with pytest.raises(NofFoundValidationError):
            service.register(
                PetHealthEventAdd(pet_id=_uuid(), event_type="vaccine",
                                  description="DHPPI", occurred_at=date(2026, 2, 20)),
                _uuid(),
            )
        event_repo.add.assert_not_called()

    def test_register_pet_of_other_user__raises_and_does_not_persist(self):
        event_repo, pet_read_repo = _make()
        pet = _pet(_uuid())  # owned by someone else
        pet_read_repo.get_by_id.return_value = pet
        service = PetHealthService(event_repo, pet_read_repo)
        with pytest.raises(NofFoundValidationError):
            service.register(
                PetHealthEventAdd(pet_id=pet.id, event_type="vaccine",
                                  description="DHPPI", occurred_at=date(2026, 2, 20)),
                _uuid(),  # a different user
            )
        event_repo.add.assert_not_called()

    def test_register_future_date__raises(self):
        event_repo, pet_read_repo = _make()
        user_id = _uuid()
        pet = _pet(user_id)
        pet_read_repo.get_by_id.return_value = pet
        service = PetHealthService(event_repo, pet_read_repo)
        # Unambiguously future = UTC today + 2 days. "+1 day" is no longer a
        # future date: occurred_at is a civil date (no timezone), so the guard is
        # clock.max_civil_date_on_earth() (UTC+14's local date = UTC today+1),
        # which is already "today" for a user in the earliest timezone.
        beyond_earth = datetime.now(timezone.utc).date() + timedelta(days=2)
        with pytest.raises(ValidationError):
            service.register(
                PetHealthEventAdd(pet_id=pet.id, event_type="vaccine",
                                  description="DHPPI",
                                  occurred_at=beyond_earth),
                user_id,
            )
        event_repo.add.assert_not_called()

    def test_register_event_before_birth__raises(self):
        event_repo, pet_read_repo = _make()
        user_id = _uuid()
        pet = _pet(user_id, birth_date=date(2024, 1, 1))
        pet_read_repo.get_by_id.return_value = pet
        service = PetHealthService(event_repo, pet_read_repo)
        with pytest.raises(ValidationError):
            service.register(
                PetHealthEventAdd(pet_id=pet.id, event_type="vaccine",
                                  description="DHPPI", occurred_at=date(2023, 6, 1)),
                user_id,
            )
        event_repo.add.assert_not_called()

    def test_register_before_birth_rule_skipped_when_birth_date_none(self):
        event_repo, pet_read_repo = _make()
        user_id = _uuid()
        pet = _pet(user_id, birth_date=None)
        pet_read_repo.get_by_id.return_value = pet
        service = PetHealthService(event_repo, pet_read_repo)

        service.register(
            PetHealthEventAdd(pet_id=pet.id, event_type="vaccine",
                              description="DHPPI", occurred_at=date(2010, 1, 1)),
            user_id,
        )
        event_repo.add.assert_called_once()


class TestUpdate:
    def test_update_applies_non_none_fields__persists(self):
        event_repo, pet_read_repo = _make()
        user_id = _uuid()
        pet = _pet(user_id)
        event = _event(pet.id)
        event_repo.get_by_id.return_value = event
        pet_read_repo.get_by_id.return_value = pet
        service = PetHealthService(event_repo, pet_read_repo)

        service.update(
            PetHealthEventUpdate(id=event.id, description="Leptospirose"), user_id
        )

        event_repo.update.assert_called_once()
        updated = event_repo.update.call_args.args[0] \
            if event_repo.update.call_args.args \
            else list(event_repo.update.call_args.kwargs.values())[0]
        assert updated.description == "Leptospirose"

    def test_update_not_found__raises(self):
        event_repo, pet_read_repo = _make()
        event_repo.get_by_id.return_value = None
        service = PetHealthService(event_repo, pet_read_repo)
        with pytest.raises(NofFoundValidationError):
            service.update(
                PetHealthEventUpdate(id=_uuid(), description="x"), _uuid()
            )

    def test_update_pet_of_other_user__raises_and_does_not_persist(self):
        event_repo, pet_read_repo = _make()
        pet = _pet(_uuid())  # other user
        event = _event(pet.id)
        event_repo.get_by_id.return_value = event
        pet_read_repo.get_by_id.return_value = pet
        service = PetHealthService(event_repo, pet_read_repo)
        with pytest.raises(NofFoundValidationError):
            service.update(
                PetHealthEventUpdate(id=event.id, description="x"), _uuid()
            )
        event_repo.update.assert_not_called()


class TestDelete:
    def test_delete__persists(self):
        event_repo, pet_read_repo = _make()
        user_id = _uuid()
        pet = _pet(user_id)
        event = _event(pet.id)
        event_repo.get_by_id.return_value = event
        pet_read_repo.get_by_id.return_value = pet
        service = PetHealthService(event_repo, pet_read_repo)

        service.delete(event.id, user_id)

        event_repo.delete.assert_called_once()

    def test_delete_not_found__raises(self):
        event_repo, pet_read_repo = _make()
        event_repo.get_by_id.return_value = None
        service = PetHealthService(event_repo, pet_read_repo)
        with pytest.raises(NofFoundValidationError):
            service.delete(_uuid(), _uuid())

    def test_delete_pet_of_other_user__raises_and_does_not_persist(self):
        event_repo, pet_read_repo = _make()
        pet = _pet(_uuid())  # other user
        event = _event(pet.id)
        event_repo.get_by_id.return_value = event
        pet_read_repo.get_by_id.return_value = pet
        service = PetHealthService(event_repo, pet_read_repo)
        with pytest.raises(NofFoundValidationError):
            service.delete(event.id, _uuid())
        event_repo.delete.assert_not_called()


class TestGetByPet:
    def test_get_by_pet__returns_repo_records_with_limit(self):
        event_repo, pet_read_repo = _make()
        user_id = _uuid()
        pet = _pet(user_id)
        pet_read_repo.get_by_id.return_value = pet
        records = [_event(pet.id), _event(pet.id)]
        event_repo.get_all_by_pet_id.return_value = records
        service = PetHealthService(event_repo, pet_read_repo)

        result = service.get_by_pet(pet.id, user_id, limit=5)

        assert result == records
        event_repo.get_all_by_pet_id.assert_called_once()
        call = event_repo.get_all_by_pet_id.call_args
        assert call.kwargs.get("limit") == 5 or 5 in call.args

    def test_get_by_pet_of_other_user__raises(self):
        event_repo, pet_read_repo = _make()
        pet = _pet(_uuid())  # other user
        pet_read_repo.get_by_id.return_value = pet
        service = PetHealthService(event_repo, pet_read_repo)
        with pytest.raises(NofFoundValidationError):
            service.get_by_pet(pet.id, _uuid())
