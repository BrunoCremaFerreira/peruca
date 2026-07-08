import uuid
from datetime import datetime, timezone
from typing import List, Optional

from domain.commands import PetHealthEventAdd, PetHealthEventUpdate
from domain.entities import PetHealthEvent
from domain.exceptions import NofFoundValidationError, ValidationError
from domain.interfaces.pet_repository import (
    PetHealthEventRepository,
    PetReadRepository,
)
from domain.validations.pet_health_event_validation import (
    PetHealthEventValidator,
)


class PetHealthService:
    """
    Registers, updates, deletes and reads pet health events. Every operation
    validates the target pet's ownership before touching data — a pet_id/event_id
    sourced from LLM output or a stale pending flow must never reach another
    user's records. It also enforces the cross-entity rule that an event may not
    predate the pet's birth_date, but only when birth_date is set (§2.8).
    """

    def __init__(
        self,
        pet_health_event_repository: PetHealthEventRepository,
        pet_read_repository: PetReadRepository,
    ):
        self.pet_health_event_repository = pet_health_event_repository
        self.pet_read_repository = pet_read_repository

    def _owned_pet_or_raise(self, pet_id: str, user_id: str):
        pet = self.pet_read_repository.get_by_id(pet_id)
        if not pet or pet.user_id != user_id:
            raise NofFoundValidationError("Pet", "id", pet_id)
        return pet

    def register(self, command: PetHealthEventAdd, user_id: str) -> str:
        PetHealthEventValidator().validate_event_type(
            command.event_type
        ).validate_description(command.description).validate_occurred_at(
            command.occurred_at
        ).validate()

        pet = self._owned_pet_or_raise(command.pet_id, user_id)

        if (
            pet.birth_date is not None
            and command.occurred_at is not None
            and command.occurred_at < pet.birth_date
        ):
            raise ValidationError(
                ["The event date is before the pet's birth date"]
            )

        event = PetHealthEvent(
            id=str(uuid.uuid4()),
            pet_id=command.pet_id,
            event_type=command.event_type,
            description=command.description,
            occurred_at=command.occurred_at,
            when_created=datetime.now(timezone.utc),
        )
        self.pet_health_event_repository.add(event)
        return event.id

    def update(self, command: PetHealthEventUpdate, user_id: str) -> None:
        event = self.pet_health_event_repository.get_by_id(command.id)
        if not event:
            raise NofFoundValidationError("PetHealthEvent", "id", command.id)

        self._owned_pet_or_raise(event.pet_id, user_id)

        if command.event_type is not None:
            event.event_type = command.event_type
        if command.description is not None:
            event.description = command.description
        if command.occurred_at is not None:
            event.occurred_at = command.occurred_at

        PetHealthEventValidator().validate_id(event.id).validate_pet_id(
            event.pet_id
        ).validate_event_type(event.event_type).validate_description(
            event.description
        ).validate_occurred_at(
            event.occurred_at
        ).validate()

        event.when_updated = datetime.now(timezone.utc)
        self.pet_health_event_repository.update(event)

    def delete(self, event_id: str, user_id: str) -> None:
        event = self.pet_health_event_repository.get_by_id(event_id)
        if not event:
            raise NofFoundValidationError("PetHealthEvent", "id", event_id)

        self._owned_pet_or_raise(event.pet_id, user_id)
        self.pet_health_event_repository.delete(event_id)

    def get_by_pet(
        self, pet_id: str, user_id: str, limit: Optional[int] = None
    ) -> List[PetHealthEvent]:
        self._owned_pet_or_raise(pet_id, user_id)
        return self.pet_health_event_repository.get_all_by_pet_id(
            pet_id=pet_id, limit=limit
        )
