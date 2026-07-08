from typing import List, Optional

from application.appservices.view_models import (
    PetHealthEventResponse,
    PetResponse,
)
from domain.commands import PetAdd, PetUpdate
from domain.entities import Pet, PetHealthEvent
from domain.exceptions import (
    EmptyParamValidationError,
    NofFoundValidationError,
    ValidationError,
)
from domain.interfaces.data_repository import UserRepository
from domain.interfaces.pet_repository import (
    PetHealthEventRepository,
    PetRepository,
)
from domain.services.pet_service import PetService
from infra.utils import is_null_or_whitespace


class PetAppService:
    """
    Pet CRUD over REST (the only write path for pets) plus read-only health-event
    auditing. Health events themselves are written via chat; REST only reads them.
    """

    def __init__(
        self,
        pet_service: PetService,
        pet_repository: PetRepository,
        pet_health_event_repository: PetHealthEventRepository,
        user_repository: UserRepository,
    ):
        self.pet_service = pet_service
        self.pet_repository = pet_repository
        self.pet_health_event_repository = pet_health_event_repository
        self.user_repository = user_repository

    # =====================================
    # Queries
    # =====================================
    def get_all_by_user(self, user_id: str) -> List[PetResponse]:
        if is_null_or_whitespace(user_id):
            raise EmptyParamValidationError(param_name="user_id")
        pets = self.pet_repository.get_all_by_user_id(user_id)
        return [self._map_pet(p) for p in pets]

    def get_by_id(self, pet_id: str) -> Optional[PetResponse]:
        if is_null_or_whitespace(pet_id):
            raise EmptyParamValidationError(param_name="pet_id")
        pet = self.pet_repository.get_by_id(pet_id)
        return self._map_pet(pet) if pet else None

    def get_health_events(self, pet_id: str) -> List[PetHealthEventResponse]:
        if is_null_or_whitespace(pet_id):
            raise EmptyParamValidationError(param_name="pet_id")
        pet = self.pet_repository.get_by_id(pet_id)
        if not pet:
            raise NofFoundValidationError("Pet", "id", pet_id)
        records = self.pet_health_event_repository.get_all_by_pet_id(pet_id)
        return [self._map_event(r) for r in records]

    # =====================================
    # Commands
    # =====================================
    def add(self, pet_add: PetAdd) -> str:
        if is_null_or_whitespace(pet_add.user_id):
            raise EmptyParamValidationError(param_name="user_id")
        if not self.user_repository.get_by_id(user_id=pet_add.user_id):
            raise ValidationError(
                [f"The user with id '{pet_add.user_id}' does not exist"]
            )
        return self.pet_service.add(pet_add)

    def update(self, pet_update: PetUpdate) -> None:
        self.pet_service.update(pet_update)

    def delete(self, pet_id: str) -> None:
        if is_null_or_whitespace(pet_id):
            raise EmptyParamValidationError(param_name="pet_id")
        pet = self.pet_repository.get_by_id(pet_id)
        if not pet:
            raise NofFoundValidationError("Pet", "id", pet_id)
        # Delegate to the domain service so the cascade + ownership rules run.
        self.pet_service.delete(pet_id, pet.user_id)

    @staticmethod
    def _map_pet(pet: Pet) -> PetResponse:
        return PetResponse(
            id=pet.id,
            user_id=pet.user_id,
            name=pet.name,
            nicknames=list(pet.nicknames or []),
            birth_date=pet.birth_date.isoformat() if pet.birth_date else "",
            sex=pet.sex,
            species=pet.species,
            description=pet.description,
        )

    @staticmethod
    def _map_event(event: PetHealthEvent) -> PetHealthEventResponse:
        return PetHealthEventResponse(
            id=event.id,
            pet_id=event.pet_id,
            event_type=event.event_type,
            description=event.description,
            occurred_at=event.occurred_at.isoformat() if event.occurred_at else "",
        )
