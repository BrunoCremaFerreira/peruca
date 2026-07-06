"""
VehicleService unit tests (TDD — written before implementation).

VehicleService owns vehicle CRUD (REST-side), per-user name uniqueness, cascade
delete of maintenance records, and the deterministic fuzzy resolver
find_vehicles_by_term used by the chat graph.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from domain.commands import VehicleAdd, VehicleUpdate
from domain.entities import Vehicle
from domain.exceptions import ValidationError
from domain.services.vehicle_service import VehicleService


def _uuid() -> str:
    return str(uuid.uuid4())


def _sample_vehicle(user_id=None, name="Mitsubishi Outlander", brand="Mitsubishi",
                    model="Outlander", year=2018) -> Vehicle:
    return Vehicle(
        id=_uuid(),
        user_id=user_id or _uuid(),
        name=name,
        brand=brand,
        model=model,
        year=year,
    )


def _make_repos():
    vehicle_repo = MagicMock()
    vehicle_repo.get_all_by_user_id.return_value = []
    vehicle_repo.get_by_id.return_value = None
    record_repo = MagicMock()
    return vehicle_repo, record_repo


class TestVehicleServiceAdd:
    def test_add_valid__returns_uuid_and_persists(self):
        vehicle_repo, record_repo = _make_repos()
        service = VehicleService(vehicle_repo, record_repo)

        new_id = service.add(
            VehicleAdd(user_id=_uuid(), name="Mitsubishi Pajero",
                       brand="Mitsubishi", model="Pajero", year=2015)
        )

        assert uuid.UUID(new_id)
        vehicle_repo.add.assert_called_once()

    def test_add_duplicate_name_same_user__raises(self):
        vehicle_repo, record_repo = _make_repos()
        user_id = _uuid()
        vehicle_repo.get_all_by_user_id.return_value = [
            _sample_vehicle(user_id=user_id, name="Mitsubishi Pajero")
        ]
        service = VehicleService(vehicle_repo, record_repo)

        with pytest.raises(ValidationError):
            service.add(
                VehicleAdd(user_id=user_id, name="Mitsubishi Pajero",
                           brand="Mitsubishi", model="Pajero", year=2015)
            )
        vehicle_repo.add.assert_not_called()

    def test_add_same_name_different_user__passes(self):
        vehicle_repo, record_repo = _make_repos()
        # The other user's list is empty for THIS user_id.
        vehicle_repo.get_all_by_user_id.return_value = []
        service = VehicleService(vehicle_repo, record_repo)

        service.add(
            VehicleAdd(user_id=_uuid(), name="Mitsubishi Pajero",
                       brand="Mitsubishi", model="Pajero", year=2015)
        )
        vehicle_repo.add.assert_called_once()

    def test_add_empty_name__raises(self):
        vehicle_repo, record_repo = _make_repos()
        service = VehicleService(vehicle_repo, record_repo)
        with pytest.raises(ValidationError):
            service.add(VehicleAdd(user_id=_uuid(), name="",
                                   brand="Mitsubishi", model="Pajero", year=2015))


class TestVehicleServiceUpdate:
    def test_update_not_found__raises(self):
        vehicle_repo, record_repo = _make_repos()
        vehicle_repo.get_by_id.return_value = None
        service = VehicleService(vehicle_repo, record_repo)
        with pytest.raises(ValidationError):
            service.update(
                VehicleUpdate(id=_uuid(), user_id=_uuid(), name="Fiat Uno",
                              brand="Fiat", model="Uno", year=2012)
            )


class TestVehicleServiceDelete:
    def test_delete_not_found__raises(self):
        vehicle_repo, record_repo = _make_repos()
        vehicle_repo.get_by_id.return_value = None
        service = VehicleService(vehicle_repo, record_repo)
        with pytest.raises(ValidationError):
            service.delete(_uuid(), _uuid())

    def test_delete_owned_by_other_user__raises(self):
        vehicle_repo, record_repo = _make_repos()
        vehicle_repo.get_by_id.return_value = _sample_vehicle(user_id=_uuid())
        service = VehicleService(vehicle_repo, record_repo)
        with pytest.raises(ValidationError):
            service.delete(vehicle_repo.get_by_id.return_value.id, _uuid())
        vehicle_repo.delete.assert_not_called()

    def test_delete_cascades_records_before_vehicle(self):
        parent = MagicMock()
        vehicle_repo = parent.vehicle_repo
        record_repo = parent.record_repo
        user_id = _uuid()
        vehicle = _sample_vehicle(user_id=user_id)
        vehicle_repo.get_by_id.return_value = vehicle
        service = VehicleService(vehicle_repo, record_repo)

        service.delete(vehicle.id, user_id)

        names = [c[0] for c in parent.mock_calls]
        assert "record_repo.delete_all_by_vehicle_id" in names
        assert "vehicle_repo.delete" in names
        assert names.index("record_repo.delete_all_by_vehicle_id") < names.index(
            "vehicle_repo.delete"
        )


class TestVehicleServiceFindByTerm:
    def _fleet(self):
        user_id = _uuid()
        return [
            _sample_vehicle(user_id=user_id, name="Mitsubishi Outlander",
                            brand="Mitsubishi", model="Outlander"),
            _sample_vehicle(user_id=user_id, name="Mitsubishi Pajero",
                            brand="Mitsubishi", model="Pajero"),
        ]

    def test_model_term_matches_single(self):
        vehicle_repo, record_repo = _make_repos()
        service = VehicleService(vehicle_repo, record_repo)
        matched = service.find_vehicles_by_term("outlander", self._fleet())
        assert len(matched) == 1
        assert matched[0].model == "Outlander"

    def test_brand_term_is_ambiguous(self):
        vehicle_repo, record_repo = _make_repos()
        service = VehicleService(vehicle_repo, record_repo)
        matched = service.find_vehicles_by_term("mitsubishi", self._fleet())
        assert len(matched) == 2

    def test_nickname_fuzzy_matches(self):
        vehicle_repo, record_repo = _make_repos()
        service = VehicleService(vehicle_repo, record_repo)
        matched = service.find_vehicles_by_term("pajerão", self._fleet())
        assert len(matched) == 1
        assert matched[0].model == "Pajero"

    def test_unregistered_term_returns_empty(self):
        vehicle_repo, record_repo = _make_repos()
        service = VehicleService(vehicle_repo, record_repo)
        assert service.find_vehicles_by_term("Porche", self._fleet()) == []
