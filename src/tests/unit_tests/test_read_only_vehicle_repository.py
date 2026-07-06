"""
ReadOnlyVehicleRepository (§2.4 nível 1): the object handed to the chat path must
PHYSICALLY lack write methods, so no reachable code — even after a future
refactor — can mutate vehicles via chat. This makes the ISP guarantee structural,
not merely nominal (a type annotation Python does not enforce at runtime).
"""

import uuid
from unittest.mock import MagicMock

from domain.entities import Vehicle
from domain.interfaces.vehicle_repository import VehicleRepository
from infra.data.read_only_vehicle_repository import ReadOnlyVehicleRepository


def _inner():
    inner = MagicMock()
    inner.get_by_id.return_value = Vehicle(id="v1", user_id="u1", name="Pajero")
    inner.get_all_by_user_id.return_value = [Vehicle(id="v1", user_id="u1", name="Pajero")]
    return inner


class TestReadOnly:
    def test_delegates_reads(self):
        inner = _inner()
        repo = ReadOnlyVehicleRepository(inner)
        assert repo.get_by_id("v1").id == "v1"
        assert len(repo.get_all_by_user_id("u1")) == 1
        inner.get_by_id.assert_called_once_with("v1")
        inner.get_all_by_user_id.assert_called_once_with("u1")

    def test_has_no_write_methods(self):
        repo = ReadOnlyVehicleRepository(_inner())
        assert not hasattr(repo, "add")
        assert not hasattr(repo, "update")
        assert not hasattr(repo, "delete")

    def test_is_not_a_write_repository(self):
        repo = ReadOnlyVehicleRepository(_inner())
        assert not isinstance(repo, VehicleRepository)
