from abc import ABC, abstractmethod
from typing import List, Optional

from domain.entities import Pet, PetHealthEvent


class PetReadRepository(ABC):
    """
    Read-only view of pets. This is the ONLY pet interface injected into the
    chat/graph path — writing a pet is a REST-only capability (§2.4), so no code
    reachable from chat can mutate pets even under prompt injection.
    """

    @abstractmethod
    def get_by_id(self, pet_id: str) -> Optional[Pet]:
        """Get a pet by id."""
        pass

    @abstractmethod
    def get_all_by_user_id(self, user_id: str) -> List[Pet]:
        """Get every pet owned by a user."""
        pass


class PetRepository(PetReadRepository):
    """
    Full pet repository (read + write). Only wired into the REST app service.
    """

    @abstractmethod
    def add(self, pet: Pet) -> None:
        """Add a pet."""
        pass

    @abstractmethod
    def update(self, pet: Pet) -> None:
        """Update a pet."""
        pass

    @abstractmethod
    def delete(self, pet_id: str) -> None:
        """Delete a pet by id."""
        pass


class PetHealthEventRepository(ABC):
    """
    Pet health event persistence.
    """

    @abstractmethod
    def add(self, event: PetHealthEvent) -> None:
        """Add a health event."""
        pass

    @abstractmethod
    def get_by_id(self, event_id: str) -> Optional[PetHealthEvent]:
        """Get a health event by id."""
        pass

    @abstractmethod
    def get_all_by_pet_id(
        self, pet_id: str, limit: Optional[int] = None
    ) -> List[PetHealthEvent]:
        """Get events for a pet, ordered by occurred_at DESC."""
        pass

    @abstractmethod
    def update(self, event: PetHealthEvent) -> None:
        """Update a health event."""
        pass

    @abstractmethod
    def delete(self, event_id: str) -> None:
        """Delete a health event by id."""
        pass

    @abstractmethod
    def delete_all_by_pet_id(self, pet_id: str) -> None:
        """Delete every health event of a pet (cascade helper)."""
        pass
