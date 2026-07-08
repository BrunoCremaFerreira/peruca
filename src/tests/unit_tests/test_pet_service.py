"""
PetService unit tests (TDD — written before implementation, Fase A / RED).

PetService owns pet CRUD (REST-side), per-user uniqueness over the UNION of every
pet's name + nicknames (§2.8), cascade delete of the pet's health events
(children first), and the deterministic resolver find_pets_by_term used by the
chat graph (matches on name AND nicknames).
"""

import uuid
from unittest.mock import MagicMock

import pytest

from domain.commands import PetAdd, PetUpdate
from domain.entities import Pet
from domain.exceptions import NofFoundValidationError, ValidationError
from domain.services.pet_service import PetService


def _uuid() -> str:
    return str(uuid.uuid4())


def _sample_pet(user_id=None, name="Caçolin", nicknames=None, sex="male",
                species="dog") -> Pet:
    return Pet(
        id=_uuid(),
        user_id=user_id or _uuid(),
        name=name,
        nicknames=list(nicknames) if nicknames is not None else ["Lilo"],
        sex=sex,
        species=species,
    )


def _make_repos():
    pet_repo = MagicMock()
    pet_repo.get_all_by_user_id.return_value = []
    pet_repo.get_by_id.return_value = None
    event_repo = MagicMock()
    return pet_repo, event_repo


def _add(user_id, name="Caçolão", nicknames=None, sex="male", species="dog"):
    return PetAdd(
        user_id=user_id,
        name=name,
        nicknames=nicknames if nicknames is not None else [],
        sex=sex,
        species=species,
    )


class TestPetServiceAdd:
    def test_add_valid__returns_uuid_and_persists(self):
        pet_repo, event_repo = _make_repos()
        service = PetService(pet_repo, event_repo)

        new_id = service.add(_add(_uuid(), name="Caçolão", nicknames=["Lyon"]))

        assert uuid.UUID(new_id)
        pet_repo.add.assert_called_once()

    def test_add_empty_name__raises(self):
        pet_repo, event_repo = _make_repos()
        service = PetService(pet_repo, event_repo)
        with pytest.raises(ValidationError):
            service.add(_add(_uuid(), name=""))
        pet_repo.add.assert_not_called()

    def test_add_duplicate_name_same_user__raises(self):
        pet_repo, event_repo = _make_repos()
        user_id = _uuid()
        pet_repo.get_all_by_user_id.return_value = [
            _sample_pet(user_id=user_id, name="Caçolin", nicknames=["Lilo"])
        ]
        service = PetService(pet_repo, event_repo)
        with pytest.raises(ValidationError):
            service.add(_add(user_id, name="Caçolin", nicknames=[]))
        pet_repo.add.assert_not_called()

    def test_add_nickname_collides_with_other_pet_name_same_user__raises(self):
        pet_repo, event_repo = _make_repos()
        user_id = _uuid()
        pet_repo.get_all_by_user_id.return_value = [
            _sample_pet(user_id=user_id, name="Caçolão", nicknames=["Lyon"])
        ]
        service = PetService(pet_repo, event_repo)
        with pytest.raises(ValidationError):
            # New pet whose nickname normalizes to an existing pet's NAME.
            service.add(_add(user_id, name="Rex", nicknames=["cacolao"]))
        pet_repo.add.assert_not_called()

    def test_add_nickname_collides_with_other_pet_nickname_same_user__raises(self):
        pet_repo, event_repo = _make_repos()
        user_id = _uuid()
        pet_repo.get_all_by_user_id.return_value = [
            _sample_pet(user_id=user_id, name="Caçolin", nicknames=["Lilo"])
        ]
        service = PetService(pet_repo, event_repo)
        with pytest.raises(ValidationError):
            service.add(_add(user_id, name="Rex", nicknames=["lilo"]))
        pet_repo.add.assert_not_called()

    def test_add_same_collision_different_user__passes(self):
        pet_repo, event_repo = _make_repos()
        # The new user's fleet is empty — same name/nickname is allowed cross-user.
        pet_repo.get_all_by_user_id.return_value = []
        service = PetService(pet_repo, event_repo)
        service.add(_add(_uuid(), name="Caçolin", nicknames=["Lilo"]))
        pet_repo.add.assert_called_once()


class TestPetServiceReads:
    def test_get_by_id_delegates(self):
        pet_repo, event_repo = _make_repos()
        pet = _sample_pet()
        pet_repo.get_by_id.return_value = pet
        service = PetService(pet_repo, event_repo)
        assert service.get_by_id(pet.id) is pet

    def test_get_all_by_user_id_delegates(self):
        pet_repo, event_repo = _make_repos()
        pets = [_sample_pet()]
        pet_repo.get_all_by_user_id.return_value = pets
        service = PetService(pet_repo, event_repo)
        assert service.get_all_by_user_id(_uuid()) == pets


class TestPetServiceUpdate:
    def test_update_valid__persists(self):
        pet_repo, event_repo = _make_repos()
        user_id = _uuid()
        pet = _sample_pet(user_id=user_id, name="Caçolin", nicknames=["Lilo"])
        pet_repo.get_by_id.return_value = pet
        pet_repo.get_all_by_user_id.return_value = [pet]
        service = PetService(pet_repo, event_repo)

        service.update(
            PetUpdate(id=pet.id, user_id=user_id, name="Caçolin",
                      nicknames=["Lilo"], birth_date=None, sex="male",
                      species="dog", description="preguiçoso")
        )
        pet_repo.update.assert_called_once()

    def test_update_not_found__raises(self):
        pet_repo, event_repo = _make_repos()
        pet_repo.get_by_id.return_value = None
        service = PetService(pet_repo, event_repo)
        with pytest.raises(NofFoundValidationError):
            service.update(
                PetUpdate(id=_uuid(), user_id=_uuid(), name="Rex", nicknames=[],
                          birth_date=None, sex="male", species="dog", description="")
            )

    def test_update_owned_by_other_user__raises(self):
        pet_repo, event_repo = _make_repos()
        pet = _sample_pet(user_id=_uuid())  # owned by someone else
        pet_repo.get_by_id.return_value = pet
        service = PetService(pet_repo, event_repo)
        with pytest.raises(NofFoundValidationError):
            service.update(
                PetUpdate(id=pet.id, user_id=_uuid(), name="Rex", nicknames=[],
                          birth_date=None, sex="male", species="dog", description="")
            )
        pet_repo.update.assert_not_called()

    def test_update_name_collides_with_other_pet__raises(self):
        pet_repo, event_repo = _make_repos()
        user_id = _uuid()
        pet_a = _sample_pet(user_id=user_id, name="Caçolin", nicknames=[])
        pet_b = _sample_pet(user_id=user_id, name="Caçolão", nicknames=[])
        pet_repo.get_by_id.return_value = pet_a
        pet_repo.get_all_by_user_id.return_value = [pet_a, pet_b]
        service = PetService(pet_repo, event_repo)
        with pytest.raises(ValidationError):
            service.update(
                PetUpdate(id=pet_a.id, user_id=user_id, name="Caçolão",
                          nicknames=[], birth_date=None, sex="male",
                          species="dog", description="")
            )
        pet_repo.update.assert_not_called()


class TestPetServiceDelete:
    def test_delete_not_found__raises(self):
        pet_repo, event_repo = _make_repos()
        pet_repo.get_by_id.return_value = None
        service = PetService(pet_repo, event_repo)
        with pytest.raises(NofFoundValidationError):
            service.delete(_uuid(), _uuid())

    def test_delete_owned_by_other_user__raises(self):
        pet_repo, event_repo = _make_repos()
        pet = _sample_pet(user_id=_uuid())
        pet_repo.get_by_id.return_value = pet
        service = PetService(pet_repo, event_repo)
        with pytest.raises(NofFoundValidationError):
            service.delete(pet.id, _uuid())
        pet_repo.delete.assert_not_called()

    def test_delete_cascades_events_before_pet(self):
        parent = MagicMock()
        pet_repo = parent.pet_repo
        event_repo = parent.event_repo
        user_id = _uuid()
        pet = _sample_pet(user_id=user_id)
        pet_repo.get_by_id.return_value = pet
        service = PetService(pet_repo, event_repo)

        service.delete(pet.id, user_id)

        names = [c[0] for c in parent.mock_calls]
        assert "event_repo.delete_all_by_pet_id" in names
        assert "pet_repo.delete" in names
        assert names.index("event_repo.delete_all_by_pet_id") < names.index(
            "pet_repo.delete"
        )


class TestPetServiceFindByTerm:
    def _pets(self):
        user_id = _uuid()
        return [
            _sample_pet(user_id=user_id, name="Caçolin",
                        nicknames=["Lilo", "Caçolinho", "Suzu"]),
            _sample_pet(user_id=user_id, name="Caçolão", nicknames=["Lyon"]),
        ]

    def test_matches_by_secondary_nickname(self):
        pet_repo, event_repo = _make_repos()
        service = PetService(pet_repo, event_repo)
        matched = service.find_pets_by_term("Suzu", self._pets())
        assert len(matched) == 1
        assert matched[0].name == "Caçolin"

    def test_unregistered_term_returns_empty(self):
        pet_repo, event_repo = _make_repos()
        service = PetService(pet_repo, event_repo)
        assert service.find_pets_by_term("Rex", self._pets()) == []
