"""
SqliteVehicleRepository tests (TDD) — REAL temporary SQLite DB via sqlite_db_path.

Covers add/get round-trip, per-user isolation (user A never sees user B's
vehicles) and update/delete.
"""

import uuid
from datetime import datetime, timezone

from domain.entities import Vehicle
from infra.data.sqlite.sqlite_vehicle_repository import SqliteVehicleRepository


def _make_repo(sqlite_db_path) -> SqliteVehicleRepository:
    return SqliteVehicleRepository(db_path=f"sqlite://{sqlite_db_path}")


def _sample(user_id, name="Mitsubishi Outlander", brand="Mitsubishi",
            model="Outlander", year=2018) -> Vehicle:
    return Vehicle(
        id=str(uuid.uuid4()), user_id=user_id, name=name, brand=brand,
        model=model, year=year, when_created=datetime.now(timezone.utc),
    )


class TestSqliteVehicleRepository:
    def test_add_then_get_by_id__returns_entity(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        v = _sample(str(uuid.uuid4()))
        repo.add(v)

        loaded = repo.get_by_id(v.id)
        assert loaded is not None
        assert loaded.id == v.id
        assert loaded.name == "Mitsubishi Outlander"
        assert loaded.brand == "Mitsubishi"
        assert loaded.model == "Outlander"
        assert loaded.year == 2018

    def test_get_all_by_user_id__isolates_users(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
        repo.add(_sample(user_a, name="Mitsubishi Outlander"))
        repo.add(_sample(user_b, name="Fiat Uno", brand="Fiat", model="Uno"))

        a_vehicles = repo.get_all_by_user_id(user_a)
        assert len(a_vehicles) == 1
        assert a_vehicles[0].user_id == user_a
        assert all(v.user_id == user_a for v in a_vehicles)

    def test_update__persists_changes(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        v = _sample(str(uuid.uuid4()))
        repo.add(v)
        v.model = "Outlander PHEV"
        v.year = 2020
        repo.update(v)

        loaded = repo.get_by_id(v.id)
        assert loaded.model == "Outlander PHEV"
        assert loaded.year == 2020

    def test_delete__removes_vehicle(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        v = _sample(str(uuid.uuid4()))
        repo.add(v)
        repo.delete(v.id)
        assert repo.get_by_id(v.id) is None

    def test_get_by_id_missing__returns_none(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        assert repo.get_by_id(str(uuid.uuid4())) is None
