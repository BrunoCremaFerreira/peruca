"""
SqlitePetHealthEventRepository tests (TDD) — REAL temporary SQLite DB.

Covers add/get round-trip with a date, DESC ordering + limit, filtering by pet,
delete and delete_all_by_pet_id (cascade helper).
"""

import uuid
from datetime import date, datetime, timezone

from domain.entities import PetHealthEvent
from infra.data.sqlite.sqlite_pet_health_event_repository import (
    SqlitePetHealthEventRepository,
)


def _make_repo(sqlite_db_path) -> SqlitePetHealthEventRepository:
    return SqlitePetHealthEventRepository(db_path=f"sqlite://{sqlite_db_path}")


def _event(pet_id, event_type="vaccine", description="DHPPI",
           occurred_at=date(2026, 2, 20)) -> PetHealthEvent:
    return PetHealthEvent(
        id=str(uuid.uuid4()), pet_id=pet_id, event_type=event_type,
        description=description, occurred_at=occurred_at,
        when_created=datetime.now(timezone.utc),
    )


class TestSqlitePetHealthEventRepository:
    def test_add_then_get_by_id__roundtrip(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        e = _event("p1")
        repo.add(e)

        loaded = repo.get_by_id(e.id)
        assert loaded is not None
        assert loaded.pet_id == "p1"
        assert loaded.event_type == "vaccine"
        assert loaded.description == "DHPPI"
        assert loaded.occurred_at == date(2026, 2, 20)

    def test_get_all_by_pet_id__orders_desc(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        repo.add(_event("p1", description="old", occurred_at=date(2025, 1, 1)))
        repo.add(_event("p1", description="new", occurred_at=date(2026, 5, 1)))

        records = repo.get_all_by_pet_id("p1")
        assert [r.description for r in records] == ["new", "old"]

    def test_get_all_by_pet_id__respects_limit(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        for month in range(1, 5):
            repo.add(_event("p1", occurred_at=date(2026, month, 1)))

        records = repo.get_all_by_pet_id("p1", limit=2)
        assert len(records) == 2

    def test_get_all_by_pet_id__filters_by_pet(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        repo.add(_event("p1"))
        repo.add(_event("p2"))
        assert len(repo.get_all_by_pet_id("p1")) == 1

    def test_update__persists(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        e = _event("p1")
        repo.add(e)
        e.description = "Leptospirose"
        repo.update(e)
        assert repo.get_by_id(e.id).description == "Leptospirose"

    def test_delete__removes(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        e = _event("p1")
        repo.add(e)
        repo.delete(e.id)
        assert repo.get_by_id(e.id) is None

    def test_delete_all_by_pet_id__removes_all(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        repo.add(_event("p1"))
        repo.add(_event("p1"))
        repo.add(_event("p2"))
        repo.delete_all_by_pet_id("p1")
        assert repo.get_all_by_pet_id("p1") == []
        assert len(repo.get_all_by_pet_id("p2")) == 1

    def test_get_by_id_missing__returns_none(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        assert repo.get_by_id(str(uuid.uuid4())) is None
