"""
SqliteMaintenanceRecordRepository tests (TDD) — REAL temporary SQLite DB.

Covers add/get round-trip (performed_at is a date), ordering by performed_at
DESC with a limit, per-vehicle filtering and both delete forms.
"""

import uuid
from datetime import date, datetime, timezone

from domain.entities import MaintenanceRecord
from infra.data.sqlite.sqlite_maintenance_record_repository import (
    SqliteMaintenanceRecordRepository,
)


def _make_repo(sqlite_db_path) -> SqliteMaintenanceRecordRepository:
    return SqliteMaintenanceRecordRepository(db_path=f"sqlite://{sqlite_db_path}")


def _rec(vehicle_id, performed_at, description="troca de óleo", km=100000) -> MaintenanceRecord:
    return MaintenanceRecord(
        id=str(uuid.uuid4()), vehicle_id=vehicle_id, description=description,
        performed_at=performed_at, odometer_km=km,
        when_created=datetime.now(timezone.utc),
    )


class TestSqliteMaintenanceRecordRepository:
    def test_add_then_get_by_id__returns_entity_with_date(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        r = _rec(str(uuid.uuid4()), date(2025, 10, 25))
        repo.add(r)

        loaded = repo.get_by_id(r.id)
        assert loaded is not None
        assert loaded.description == "troca de óleo"
        assert loaded.performed_at == date(2025, 10, 25)
        assert loaded.odometer_km == 100000

    def test_get_all_by_vehicle_id__ordered_desc(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        vid = str(uuid.uuid4())
        repo.add(_rec(vid, date(2025, 1, 12), description="antiga"))
        repo.add(_rec(vid, date(2026, 5, 22), description="recente"))
        repo.add(_rec(vid, date(2025, 12, 17), description="meio"))

        records = repo.get_all_by_vehicle_id(vid)
        dates = [r.performed_at for r in records]
        assert dates == [date(2026, 5, 22), date(2025, 12, 17), date(2025, 1, 12)]

    def test_get_all_by_vehicle_id__limit(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        vid = str(uuid.uuid4())
        repo.add(_rec(vid, date(2025, 1, 12)))
        repo.add(_rec(vid, date(2026, 5, 22)))
        repo.add(_rec(vid, date(2025, 12, 17)))

        records = repo.get_all_by_vehicle_id(vid, limit=2)
        assert len(records) == 2
        assert records[0].performed_at == date(2026, 5, 22)

    def test_get_all_by_vehicle_id__filters_by_vehicle(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        vid_a, vid_b = str(uuid.uuid4()), str(uuid.uuid4())
        repo.add(_rec(vid_a, date(2025, 1, 1)))
        repo.add(_rec(vid_b, date(2025, 2, 2)))

        assert len(repo.get_all_by_vehicle_id(vid_a)) == 1

    def test_update__persists(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        r = _rec(str(uuid.uuid4()), date(2025, 12, 17), km=99821)
        repo.add(r)
        r.odometer_km = 100821
        repo.update(r)

        assert repo.get_by_id(r.id).odometer_km == 100821

    def test_delete__removes_record(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        r = _rec(str(uuid.uuid4()), date(2025, 1, 1))
        repo.add(r)
        repo.delete(r.id)
        assert repo.get_by_id(r.id) is None

    def test_delete_all_by_vehicle_id__cascade_helper(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        vid = str(uuid.uuid4())
        repo.add(_rec(vid, date(2025, 1, 1)))
        repo.add(_rec(vid, date(2025, 2, 1)))
        repo.delete_all_by_vehicle_id(vid)
        assert repo.get_all_by_vehicle_id(vid) == []

    def test_null_odometer_roundtrips(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        r = _rec(str(uuid.uuid4()), date(2025, 1, 1), km=None)
        repo.add(r)
        assert repo.get_by_id(r.id).odometer_km is None
