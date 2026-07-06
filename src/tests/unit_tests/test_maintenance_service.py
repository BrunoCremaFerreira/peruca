"""
MaintenanceService unit tests (TDD — written before implementation).

MaintenanceService registers/updates/deletes maintenance records and reads them
back per vehicle. Every operation validates the record AND the ownership of the
target vehicle (a vehicle_id/record_id from LLM output or a stale pending flow
must never touch another user's data).
"""

import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from domain.commands import MaintenanceRecordAdd, MaintenanceRecordUpdate
from domain.entities import MaintenanceRecord, Vehicle
from domain.exceptions import ValidationError
from domain.services.maintenance_service import MaintenanceService


def _uuid() -> str:
    return str(uuid.uuid4())


def _vehicle(user_id) -> Vehicle:
    return Vehicle(id=_uuid(), user_id=user_id, name="Mitsubishi Outlander",
                   brand="Mitsubishi", model="Outlander", year=2018)


def _record(vehicle_id) -> MaintenanceRecord:
    return MaintenanceRecord(
        id=_uuid(), vehicle_id=vehicle_id, description="troca de óleo",
        performed_at=date(2025, 10, 25), odometer_km=100232,
    )


def _make():
    record_repo = MagicMock()
    record_repo.get_by_id.return_value = None
    record_repo.get_all_by_vehicle_id.return_value = []
    vehicle_read_repo = MagicMock()
    vehicle_read_repo.get_by_id.return_value = None
    return record_repo, vehicle_read_repo


class TestRegister:
    def test_register_valid__returns_uuid_and_persists(self):
        record_repo, vehicle_read_repo = _make()
        user_id = _uuid()
        vehicle = _vehicle(user_id)
        vehicle_read_repo.get_by_id.return_value = vehicle
        service = MaintenanceService(record_repo, vehicle_read_repo)

        new_id = service.register(
            MaintenanceRecordAdd(vehicle_id=vehicle.id, description="troca dos 4 pneus",
                                 performed_at=date(2026, 7, 5), odometer_km=101127),
            user_id,
        )

        assert uuid.UUID(new_id)
        record_repo.add.assert_called_once()

    def test_register_unknown_vehicle__raises_and_does_not_persist(self):
        record_repo, vehicle_read_repo = _make()
        vehicle_read_repo.get_by_id.return_value = None
        service = MaintenanceService(record_repo, vehicle_read_repo)
        with pytest.raises(ValidationError):
            service.register(
                MaintenanceRecordAdd(vehicle_id=_uuid(), description="x",
                                     performed_at=date(2025, 1, 1), odometer_km=1000),
                _uuid(),
            )
        record_repo.add.assert_not_called()

    def test_register_vehicle_of_other_user__raises(self):
        record_repo, vehicle_read_repo = _make()
        vehicle = _vehicle(_uuid())  # owned by someone else
        vehicle_read_repo.get_by_id.return_value = vehicle
        service = MaintenanceService(record_repo, vehicle_read_repo)
        with pytest.raises(ValidationError):
            service.register(
                MaintenanceRecordAdd(vehicle_id=vehicle.id, description="x",
                                     performed_at=date(2025, 1, 1), odometer_km=1000),
                _uuid(),  # a different user
            )
        record_repo.add.assert_not_called()

    def test_register_future_date__raises(self):
        record_repo, vehicle_read_repo = _make()
        user_id = _uuid()
        vehicle = _vehicle(user_id)
        vehicle_read_repo.get_by_id.return_value = vehicle
        service = MaintenanceService(record_repo, vehicle_read_repo)
        with pytest.raises(ValidationError):
            service.register(
                MaintenanceRecordAdd(vehicle_id=vehicle.id, description="x",
                                     performed_at=date.today() + timedelta(days=1),
                                     odometer_km=1000),
                user_id,
            )

    def test_register_negative_km__raises(self):
        record_repo, vehicle_read_repo = _make()
        user_id = _uuid()
        vehicle = _vehicle(user_id)
        vehicle_read_repo.get_by_id.return_value = vehicle
        service = MaintenanceService(record_repo, vehicle_read_repo)
        with pytest.raises(ValidationError):
            service.register(
                MaintenanceRecordAdd(vehicle_id=vehicle.id, description="x",
                                     performed_at=date(2025, 1, 1), odometer_km=-1),
                user_id,
            )


class TestUpdate:
    def test_update_km__persists(self):
        record_repo, vehicle_read_repo = _make()
        user_id = _uuid()
        vehicle = _vehicle(user_id)
        record = _record(vehicle.id)
        record_repo.get_by_id.return_value = record
        vehicle_read_repo.get_by_id.return_value = vehicle
        service = MaintenanceService(record_repo, vehicle_read_repo)

        service.update(
            MaintenanceRecordUpdate(id=record.id, odometer_km=100821), user_id
        )

        record_repo.update.assert_called_once()
        updated = record_repo.update.call_args[0][0] if record_repo.update.call_args[0] \
            else record_repo.update.call_args[1]["record"]
        assert updated.odometer_km == 100821

    def test_update_not_found__raises(self):
        record_repo, vehicle_read_repo = _make()
        record_repo.get_by_id.return_value = None
        service = MaintenanceService(record_repo, vehicle_read_repo)
        with pytest.raises(ValidationError):
            service.update(MaintenanceRecordUpdate(id=_uuid(), odometer_km=1), _uuid())

    def test_update_record_of_other_user__raises(self):
        record_repo, vehicle_read_repo = _make()
        vehicle = _vehicle(_uuid())  # other user
        record = _record(vehicle.id)
        record_repo.get_by_id.return_value = record
        vehicle_read_repo.get_by_id.return_value = vehicle
        service = MaintenanceService(record_repo, vehicle_read_repo)
        with pytest.raises(ValidationError):
            service.update(MaintenanceRecordUpdate(id=record.id, odometer_km=1), _uuid())
        record_repo.update.assert_not_called()


class TestDelete:
    def test_delete__persists(self):
        record_repo, vehicle_read_repo = _make()
        user_id = _uuid()
        vehicle = _vehicle(user_id)
        record = _record(vehicle.id)
        record_repo.get_by_id.return_value = record
        vehicle_read_repo.get_by_id.return_value = vehicle
        service = MaintenanceService(record_repo, vehicle_read_repo)

        service.delete(record.id, user_id)

        record_repo.delete.assert_called_once()

    def test_delete_not_found__raises(self):
        record_repo, vehicle_read_repo = _make()
        record_repo.get_by_id.return_value = None
        service = MaintenanceService(record_repo, vehicle_read_repo)
        with pytest.raises(ValidationError):
            service.delete(_uuid(), _uuid())


class TestGetByVehicle:
    def test_get_by_vehicle__returns_repo_records_with_limit(self):
        record_repo, vehicle_read_repo = _make()
        user_id = _uuid()
        vehicle = _vehicle(user_id)
        vehicle_read_repo.get_by_id.return_value = vehicle
        records = [_record(vehicle.id), _record(vehicle.id)]
        record_repo.get_all_by_vehicle_id.return_value = records
        service = MaintenanceService(record_repo, vehicle_read_repo)

        result = service.get_by_vehicle(vehicle.id, user_id, limit=2)

        assert result == records
        record_repo.get_all_by_vehicle_id.assert_called_once_with(
            vehicle_id=vehicle.id, limit=2
        )

    def test_get_by_vehicle_of_other_user__raises(self):
        record_repo, vehicle_read_repo = _make()
        vehicle = _vehicle(_uuid())  # other user
        vehicle_read_repo.get_by_id.return_value = vehicle
        service = MaintenanceService(record_repo, vehicle_read_repo)
        with pytest.raises(ValidationError):
            service.get_by_vehicle(vehicle.id, _uuid())
