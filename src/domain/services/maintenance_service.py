import uuid
from datetime import datetime, timezone
from typing import List, Optional

from domain.commands import MaintenanceRecordAdd, MaintenanceRecordUpdate
from domain.entities import MaintenanceRecord
from domain.exceptions import NofFoundValidationError
from domain.interfaces.vehicle_repository import (
    MaintenanceRecordRepository,
    VehicleReadRepository,
)
from domain.validations.maintenance_record_validation import (
    MaintenanceRecordValidator,
)


class MaintenanceService:
    """
    Registers, updates, deletes and reads maintenance records. Every operation
    validates the target vehicle's ownership before touching data — a
    vehicle_id/record_id sourced from LLM output or a stale pending flow must
    never reach another user's records.
    """

    def __init__(
        self,
        maintenance_record_repository: MaintenanceRecordRepository,
        vehicle_read_repository: VehicleReadRepository,
    ):
        self.maintenance_record_repository = maintenance_record_repository
        self.vehicle_read_repository = vehicle_read_repository

    def _owned_vehicle_or_raise(self, vehicle_id: str, user_id: str):
        vehicle = self.vehicle_read_repository.get_by_id(vehicle_id)
        if not vehicle or vehicle.user_id != user_id:
            raise NofFoundValidationError("Vehicle", "id", vehicle_id)
        return vehicle

    def register(self, command: MaintenanceRecordAdd, user_id: str) -> str:
        MaintenanceRecordValidator().validate_vehicle_id(
            command.vehicle_id
        ).validate_description(command.description).validate_performed_at(
            command.performed_at
        ).validate_odometer_km(
            command.odometer_km
        ).validate()

        self._owned_vehicle_or_raise(command.vehicle_id, user_id)

        record = MaintenanceRecord(
            id=str(uuid.uuid4()),
            vehicle_id=command.vehicle_id,
            description=command.description,
            performed_at=command.performed_at,
            odometer_km=command.odometer_km,
            when_created=datetime.now(timezone.utc),
        )
        self.maintenance_record_repository.add(record)
        return record.id

    def update(self, command: MaintenanceRecordUpdate, user_id: str) -> None:
        record = self.maintenance_record_repository.get_by_id(command.id)
        if not record:
            raise NofFoundValidationError("MaintenanceRecord", "id", command.id)

        self._owned_vehicle_or_raise(record.vehicle_id, user_id)

        if command.description is not None:
            record.description = command.description
        if command.performed_at is not None:
            record.performed_at = command.performed_at
        if command.odometer_km is not None:
            record.odometer_km = command.odometer_km

        MaintenanceRecordValidator().validate_id(record.id).validate_vehicle_id(
            record.vehicle_id
        ).validate_description(record.description).validate_performed_at(
            record.performed_at
        ).validate_odometer_km(
            record.odometer_km
        ).validate()

        record.when_updated = datetime.now(timezone.utc)
        self.maintenance_record_repository.update(record)

    def delete(self, record_id: str, user_id: str) -> None:
        record = self.maintenance_record_repository.get_by_id(record_id)
        if not record:
            raise NofFoundValidationError("MaintenanceRecord", "id", record_id)

        self._owned_vehicle_or_raise(record.vehicle_id, user_id)
        self.maintenance_record_repository.delete(record_id)

    def get_by_vehicle(
        self, vehicle_id: str, user_id: str, limit: Optional[int] = None
    ) -> List[MaintenanceRecord]:
        self._owned_vehicle_or_raise(vehicle_id, user_id)
        return self.maintenance_record_repository.get_all_by_vehicle_id(
            vehicle_id=vehicle_id, limit=limit
        )
