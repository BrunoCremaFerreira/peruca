"""
VehicleAppService unit tests (TDD).

Maps entities to VehicleResponse/MaintenanceRecordResponse, enforces per-user
listing, rejects empty ids, and refuses to create a vehicle for a non-existent
user.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from application.appservices.view_models import (
    MaintenanceRecordResponse,
    VehicleResponse,
)
from domain.commands import VehicleAdd
from domain.entities import MaintenanceRecord, User, Vehicle
from domain.exceptions import EmptyParamValidationError, ValidationError
from application.appservices.vehicle_app_service import VehicleAppService


def _uuid() -> str:
    return str(uuid.uuid4())


def _vehicle(user_id, name="Mitsubishi Outlander") -> Vehicle:
    return Vehicle(id=_uuid(), user_id=user_id, name=name, brand="Mitsubishi",
                   model="Outlander", year=2018)


def _make():
    vehicle_service = MagicMock()
    vehicle_repository = MagicMock()
    vehicle_repository.get_by_id.return_value = None
    vehicle_repository.get_all_by_user_id.return_value = []
    maintenance_record_repository = MagicMock()
    maintenance_record_repository.get_all_by_vehicle_id.return_value = []
    user_repository = MagicMock()
    user_repository.get_by_id.return_value = None
    return (
        VehicleAppService(
            vehicle_service=vehicle_service,
            vehicle_repository=vehicle_repository,
            maintenance_record_repository=maintenance_record_repository,
            user_repository=user_repository,
        ),
        vehicle_service,
        vehicle_repository,
        maintenance_record_repository,
        user_repository,
    )


class TestAdd:
    def test_add_existing_user__delegates_and_returns_id(self):
        svc, vehicle_service, _, _, user_repository = _make()
        user_id = _uuid()
        user_repository.get_by_id.return_value = User(id=user_id, name="Bruno")
        vehicle_service.add.return_value = "veh-id"

        result = svc.add(VehicleAdd(user_id=user_id, name="Fiat Uno",
                                    brand="Fiat", model="Uno", year=2012))

        assert result == "veh-id"
        vehicle_service.add.assert_called_once()

    def test_add_unknown_user__raises_and_does_not_delegate(self):
        svc, vehicle_service, _, _, user_repository = _make()
        user_repository.get_by_id.return_value = None
        with pytest.raises(ValidationError):
            svc.add(VehicleAdd(user_id=_uuid(), name="Fiat Uno",
                               brand="Fiat", model="Uno", year=2012))
        vehicle_service.add.assert_not_called()


class TestQueries:
    def test_get_all_by_user__maps_and_scopes(self):
        svc, _, vehicle_repository, _, _ = _make()
        user_id = _uuid()
        vehicle_repository.get_all_by_user_id.return_value = [_vehicle(user_id)]

        result = svc.get_all_by_user(user_id)

        assert all(isinstance(r, VehicleResponse) for r in result)
        assert result[0].name == "Mitsubishi Outlander"
        vehicle_repository.get_all_by_user_id.assert_called_once_with(user_id)

    def test_get_by_id_empty__raises(self):
        svc, *_ = _make()
        with pytest.raises(EmptyParamValidationError):
            svc.get_by_id("   ")

    def test_get_maintenance__maps(self):
        svc, _, vehicle_repository, record_repo, _ = _make()
        from datetime import date

        vehicle = _vehicle(_uuid())
        vehicle_repository.get_by_id.return_value = vehicle
        record_repo.get_all_by_vehicle_id.return_value = [
            MaintenanceRecord(id=_uuid(), vehicle_id=vehicle.id,
                              description="troca de óleo",
                              performed_at=date(2025, 10, 25), odometer_km=100000)
        ]

        result = svc.get_maintenance(vehicle.id)

        assert all(isinstance(r, MaintenanceRecordResponse) for r in result)
        assert result[0].description == "troca de óleo"


class TestDelete:
    def test_delete__loads_owner_and_delegates(self):
        svc, vehicle_service, vehicle_repository, _, _ = _make()
        user_id = _uuid()
        vehicle = _vehicle(user_id)
        vehicle_repository.get_by_id.return_value = vehicle

        svc.delete(vehicle.id)

        vehicle_service.delete.assert_called_once_with(vehicle.id, user_id)

    def test_delete_missing__raises(self):
        svc, vehicle_service, vehicle_repository, _, _ = _make()
        vehicle_repository.get_by_id.return_value = None
        with pytest.raises(ValidationError):
            svc.delete(_uuid())
        vehicle_service.delete.assert_not_called()
