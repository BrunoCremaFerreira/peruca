import uuid
from datetime import datetime, timezone
from typing import List

from domain.commands import PetAdd, PetUpdate
from domain.entities import Pet
from domain.exceptions import NofFoundValidationError, ValidationError
from domain.interfaces.pet_repository import (
    PetHealthEventRepository,
    PetRepository,
)
from domain.services.text_matching import find_by_term, normalize
from domain.validations.pet_validation import PetValidator
from infra.utils import auto_map


def _searchables(pet: Pet) -> List[str]:
    """Every string a term may legitimately match a pet by: name + nicknames."""
    return [pet.name, *pet.nicknames]


def find_pets_by_term(term: str, pets: List[Pet]) -> List[Pet]:
    """
    Resolve a user-typed term against already-loaded pets, deterministically
    (no LLM, no repository access), matching on name AND nicknames.
    """
    return find_by_term(term, pets, _searchables)


class PetService:
    """
    Pet CRUD (REST-side), per-user uniqueness over the UNION of every pet's name
    and nicknames, and cascade delete of the pet's health events (children
    first).
    """

    def __init__(
        self,
        pet_repository: PetRepository,
        pet_health_event_repository: PetHealthEventRepository,
    ):
        self.pet_repository = pet_repository
        self.pet_health_event_repository = pet_health_event_repository

    def _validate(self, pet: Pet) -> None:
        PetValidator().validate_id(pet.id).validate_user_id(
            pet.user_id
        ).validate_name(pet.name).validate_nicknames(
            pet.nicknames, pet.name
        ).validate_birth_date(
            pet.birth_date
        ).validate_sex(
            pet.sex
        ).validate_species(
            pet.species
        ).validate_description(
            pet.description
        ).validate()

    def _assert_unique(self, pet: Pet, exclude_id: str = "") -> None:
        """
        Reject a name/nickname colliding (normalized) with the name OR a nickname
        of another pet of the same user — otherwise the chat matcher would be
        permanently ambiguous (§2.8).
        """
        new_terms = {normalize(t) for t in _searchables(pet) if t and t.strip()}
        for existing in self.pet_repository.get_all_by_user_id(pet.user_id):
            if existing.id == exclude_id:
                continue
            existing_terms = {
                normalize(t) for t in _searchables(existing) if t and t.strip()
            }
            if new_terms & existing_terms:
                raise ValidationError(
                    [
                        f"The pet '{pet.name}' collides with an existing pet "
                        "for this user"
                    ]
                )

    def add(self, command: PetAdd) -> str:
        pet = auto_map(command, Pet)
        pet.id = str(uuid.uuid4())
        pet.when_created = datetime.now(timezone.utc)

        self._validate(pet)
        self._assert_unique(pet)

        self.pet_repository.add(pet)
        return pet.id

    def get_by_id(self, pet_id: str):
        return self.pet_repository.get_by_id(pet_id)

    def get_all_by_user_id(self, user_id: str) -> List[Pet]:
        return self.pet_repository.get_all_by_user_id(user_id)

    def update(self, command: PetUpdate) -> None:
        pet = auto_map(command, Pet)

        self._validate(pet)

        db_pet = self.pet_repository.get_by_id(pet.id)
        if not db_pet or db_pet.user_id != pet.user_id:
            raise NofFoundValidationError("Pet", "id", pet.id)

        self._assert_unique(pet, exclude_id=pet.id)

        self.pet_repository.update(pet)

    def delete(self, pet_id: str, user_id: str) -> None:
        PetValidator().validate_id(pet_id).validate()

        db_pet = self.pet_repository.get_by_id(pet_id)
        if not db_pet or db_pet.user_id != user_id:
            raise NofFoundValidationError("Pet", "id", pet_id)

        # Cascade: children first, so a mid-operation failure never leaves an
        # orphan health event (§9.4 invariant).
        self.pet_health_event_repository.delete_all_by_pet_id(pet_id)
        self.pet_repository.delete(pet_id)

    def find_pets_by_term(self, term: str, pets: List[Pet]) -> List[Pet]:
        return find_pets_by_term(term, pets)
