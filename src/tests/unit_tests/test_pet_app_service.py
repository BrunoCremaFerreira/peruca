"""
PetAppService unit tests (TDD).

Maps entities to PetResponse/PetHealthEventResponse, enforces per-user listing,
rejects empty ids, refuses to create a pet for a non-existent user, and cascades
delete through the domain service.
"""

import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest

from application.appservices.pet_app_service import PetAppService
from application.appservices.view_models import (
    PetHealthEventResponse,
    PetResponse,
)
from domain.commands import PetAdd
from domain.entities import Pet, PetHealthEvent, User
from domain.exceptions import EmptyParamValidationError, ValidationError


def _uuid() -> str:
    return str(uuid.uuid4())


def _pet(user_id, name="Caçolin", nicknames=None) -> Pet:
    return Pet(id=_uuid(), user_id=user_id, name=name,
               nicknames=nicknames if nicknames is not None else ["Lilo"],
               birth_date=date(2020, 1, 1), sex="male", species="dog",
               description="preguiçoso")


def _make():
    pet_service = MagicMock()
    pet_repository = MagicMock()
    pet_repository.get_by_id.return_value = None
    pet_repository.get_all_by_user_id.return_value = []
    event_repository = MagicMock()
    event_repository.get_all_by_pet_id.return_value = []
    user_repository = MagicMock()
    user_repository.get_by_id.return_value = None
    return (
        PetAppService(
            pet_service=pet_service,
            pet_repository=pet_repository,
            pet_health_event_repository=event_repository,
            user_repository=user_repository,
        ),
        pet_service,
        pet_repository,
        event_repository,
        user_repository,
    )


class TestAdd:
    def test_add_existing_user__delegates_and_returns_id(self):
        svc, pet_service, _, _, user_repository = _make()
        user_id = _uuid()
        user_repository.get_by_id.return_value = User(id=user_id, name="Bruno")
        pet_service.add.return_value = "pet-id"

        result = svc.add(PetAdd(user_id=user_id, name="Caçolão",
                                nicknames=["Lyon"], sex="male", species="dog"))

        assert result == "pet-id"
        pet_service.add.assert_called_once()

    def test_add_unknown_user__raises_and_does_not_delegate(self):
        svc, pet_service, _, _, user_repository = _make()
        user_repository.get_by_id.return_value = None
        with pytest.raises(ValidationError):
            svc.add(PetAdd(user_id=_uuid(), name="Rex", sex="male", species="dog"))
        pet_service.add.assert_not_called()


class TestQueries:
    def test_get_all_by_user__maps_and_scopes(self):
        svc, _, pet_repository, _, _ = _make()
        user_id = _uuid()
        pet_repository.get_all_by_user_id.return_value = [
            _pet(user_id, nicknames=["Lilo", "Suzu"])
        ]

        result = svc.get_all_by_user(user_id)

        assert all(isinstance(r, PetResponse) for r in result)
        assert result[0].name == "Caçolin"
        assert result[0].nicknames == ["Lilo", "Suzu"]
        pet_repository.get_all_by_user_id.assert_called_once_with(user_id)

    def test_get_by_id_empty__raises(self):
        svc, *_ = _make()
        with pytest.raises(EmptyParamValidationError):
            svc.get_by_id("   ")

    def test_get_health_events__maps(self):
        svc, _, pet_repository, event_repo, _ = _make()
        pet = _pet(_uuid())
        pet_repository.get_by_id.return_value = pet
        event_repo.get_all_by_pet_id.return_value = [
            PetHealthEvent(id=_uuid(), pet_id=pet.id, event_type="vaccine",
                           description="DHPPI", occurred_at=date(2026, 2, 20))
        ]

        result = svc.get_health_events(pet.id)

        assert all(isinstance(r, PetHealthEventResponse) for r in result)
        assert result[0].description == "DHPPI"
        assert result[0].occurred_at == "2026-02-20"


class TestDelete:
    def test_delete__loads_owner_and_delegates(self):
        svc, pet_service, pet_repository, _, _ = _make()
        user_id = _uuid()
        pet = _pet(user_id)
        pet_repository.get_by_id.return_value = pet

        svc.delete(pet.id)

        pet_service.delete.assert_called_once_with(pet.id, user_id)

    def test_delete_missing__raises(self):
        svc, pet_service, pet_repository, _, _ = _make()
        pet_repository.get_by_id.return_value = None
        with pytest.raises(ValidationError):
            svc.delete(_uuid())
        pet_service.delete.assert_not_called()
