from abc import ABC, abstractmethod
from typing import List, Optional

from domain.entities import MaintenanceRecord, Vehicle


class VehicleReadRepository(ABC):
    """
    Read-only view of vehicles. This is the ONLY vehicle interface injected into
    the chat/graph path — writing a vehicle is a REST-only capability (§2.4), so
    no code reachable from chat can mutate vehicles even under prompt injection.
    """

    @abstractmethod
    def get_by_id(self, vehicle_id: str) -> Optional[Vehicle]:
        """Get a vehicle by id."""
        pass

    @abstractmethod
    def get_all_by_user_id(self, user_id: str) -> List[Vehicle]:
        """Get every vehicle owned by a user."""
        pass


class VehicleRepository(VehicleReadRepository):
    """
    Full vehicle repository (read + write). Only wired into the REST app service.
    """

    @abstractmethod
    def add(self, vehicle: Vehicle) -> None:
        """Add a vehicle."""
        pass

    @abstractmethod
    def update(self, vehicle: Vehicle) -> None:
        """Update a vehicle."""
        pass

    @abstractmethod
    def delete(self, vehicle_id: str) -> None:
        """Delete a vehicle by id."""
        pass


class MaintenanceRecordRepository(ABC):
    """
    Maintenance record persistence.
    """

    @abstractmethod
    def add(self, record: MaintenanceRecord) -> None:
        """Add a maintenance record."""
        pass

    @abstractmethod
    def get_by_id(self, record_id: str) -> Optional[MaintenanceRecord]:
        """Get a maintenance record by id."""
        pass

    @abstractmethod
    def get_all_by_vehicle_id(
        self, vehicle_id: str, limit: Optional[int] = None
    ) -> List[MaintenanceRecord]:
        """Get records for a vehicle, ordered by performed_at DESC."""
        pass

    @abstractmethod
    def update(self, record: MaintenanceRecord) -> None:
        """Update a maintenance record."""
        pass

    @abstractmethod
    def delete(self, record_id: str) -> None:
        """Delete a maintenance record by id."""
        pass

    @abstractmethod
    def delete_all_by_vehicle_id(self, vehicle_id: str) -> None:
        """Delete every maintenance record of a vehicle (cascade helper)."""
        pass
