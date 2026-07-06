from typing import List, Optional

from application.appservices.view_models import (
    MaintenanceRecordResponse,
    VehicleResponse,
)
from domain.commands import VehicleAdd, VehicleUpdate
from domain.entities import MaintenanceRecord, Vehicle
from domain.exceptions import EmptyParamValidationError, NofFoundValidationError, ValidationError
from domain.interfaces.data_repository import UserRepository
from domain.interfaces.vehicle_repository import (
    MaintenanceRecordRepository,
    VehicleRepository,
)
from domain.services.vehicle_service import VehicleService
from infra.utils import auto_map, is_null_or_whitespace


class VehicleAppService:
    """
    Vehicle CRUD over REST (the only write path for vehicles) plus read-only
    maintenance auditing.
    """

    def __init__(
        self,
        vehicle_service: VehicleService,
        vehicle_repository: VehicleRepository,
        maintenance_record_repository: MaintenanceRecordRepository,
        user_repository: UserRepository,
    ):
        self.vehicle_service = vehicle_service
        self.vehicle_repository = vehicle_repository
        self.maintenance_record_repository = maintenance_record_repository
        self.user_repository = user_repository

    # =====================================
    # Queries
    # =====================================
    def get_all_by_user(self, user_id: str) -> List[VehicleResponse]:
        if is_null_or_whitespace(user_id):
            raise EmptyParamValidationError(param_name="user_id")
        vehicles = self.vehicle_repository.get_all_by_user_id(user_id)
        return [auto_map(v, VehicleResponse) for v in vehicles]

    def get_by_id(self, vehicle_id: str) -> Optional[VehicleResponse]:
        if is_null_or_whitespace(vehicle_id):
            raise EmptyParamValidationError(param_name="vehicle_id")
        vehicle = self.vehicle_repository.get_by_id(vehicle_id)
        return auto_map(vehicle, VehicleResponse) if vehicle else None

    def get_maintenance(self, vehicle_id: str) -> List[MaintenanceRecordResponse]:
        if is_null_or_whitespace(vehicle_id):
            raise EmptyParamValidationError(param_name="vehicle_id")
        vehicle = self.vehicle_repository.get_by_id(vehicle_id)
        if not vehicle:
            raise NofFoundValidationError("Vehicle", "id", vehicle_id)
        records = self.maintenance_record_repository.get_all_by_vehicle_id(vehicle_id)
        return [self._map_record(r) for r in records]

    # =====================================
    # Commands
    # =====================================
    def add(self, vehicle_add: VehicleAdd) -> str:
        if is_null_or_whitespace(vehicle_add.user_id):
            raise EmptyParamValidationError(param_name="user_id")
        if not self.user_repository.get_by_id(user_id=vehicle_add.user_id):
            raise ValidationError(
                [f"The user with id '{vehicle_add.user_id}' does not exist"]
            )
        return self.vehicle_service.add(vehicle_add)

    def update(self, vehicle_update: VehicleUpdate) -> None:
        self.vehicle_service.update(vehicle_update)

    def delete(self, vehicle_id: str) -> None:
        if is_null_or_whitespace(vehicle_id):
            raise EmptyParamValidationError(param_name="vehicle_id")
        vehicle = self.vehicle_repository.get_by_id(vehicle_id)
        if not vehicle:
            raise NofFoundValidationError("Vehicle", "id", vehicle_id)
        # Delegate to the domain service so the cascade + ownership rules run.
        self.vehicle_service.delete(vehicle_id, vehicle.user_id)

    @staticmethod
    def _map_record(record: MaintenanceRecord) -> MaintenanceRecordResponse:
        return MaintenanceRecordResponse(
            id=record.id,
            vehicle_id=record.vehicle_id,
            description=record.description,
            performed_at=record.performed_at.isoformat()
            if record.performed_at
            else "",
            odometer_km=record.odometer_km,
        )
