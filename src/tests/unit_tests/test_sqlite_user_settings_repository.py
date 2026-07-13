"""
SqliteUserSettingsRepository tests (TDD) — §10.4 of the user-timezone plan.

REAL temporary SQLite DB via the ``sqlite_db_path`` fixture (same mold as
test_sqlite_pet_repository.py). Covers the add/get round trip, the unknown-user
read, the in-place update (1:1 per user — never a second row) and per-user
isolation.
"""

import uuid
from datetime import datetime, timezone

from domain.entities import UserSettings
from infra.data.sqlite.sqlite_user_settings_repository import (
    SqliteUserSettingsRepository,
)


def _make_repo(sqlite_db_path) -> SqliteUserSettingsRepository:
    return SqliteUserSettingsRepository(db_path=f"sqlite://{sqlite_db_path}")


def _sample(user_id, timezone_name="America/Sao_Paulo") -> UserSettings:
    return UserSettings(
        id=str(uuid.uuid4()),
        user_id=user_id,
        timezone=timezone_name,
        when_created=datetime.now(timezone.utc),
    )


def _row_count(repo, user_id) -> int:
    cursor = repo.conn.execute(
        "SELECT COUNT(*) AS total FROM user_settings WHERE user_id = ?", (user_id,)
    )
    return cursor.fetchone()["total"]


class TestSqliteUserSettingsRepository:
    def test_add_then_get_by_user_id__round_trip(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        settings = _sample(str(uuid.uuid4()), "Europe/Lisbon")
        repo.add(settings)

        loaded = repo.get_by_user_id(settings.user_id)
        assert loaded is not None
        assert loaded.id == settings.id
        assert loaded.user_id == settings.user_id
        assert loaded.timezone == "Europe/Lisbon"

    def test_get_by_user_id__unknown_user__returns_none(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        assert repo.get_by_user_id(str(uuid.uuid4())) is None

    def test_update__persists_new_timezone(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        settings = _sample(str(uuid.uuid4()), "America/Sao_Paulo")
        repo.add(settings)

        settings.timezone = "Europe/Lisbon"
        settings.when_updated = datetime.now(timezone.utc)
        repo.update(settings)

        loaded = repo.get_by_user_id(settings.user_id)
        assert loaded.timezone == "Europe/Lisbon"
        assert loaded.id == settings.id
        # 1:1 per user — the update must not have created a second row.
        assert _row_count(repo, settings.user_id) == 1

    def test_isolation__user_a_never_sees_user_b(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
        repo.add(_sample(user_a, "America/Sao_Paulo"))
        repo.add(_sample(user_b, "Europe/Lisbon"))

        loaded_a = repo.get_by_user_id(user_a)
        loaded_b = repo.get_by_user_id(user_b)
        assert loaded_a.timezone == "America/Sao_Paulo"
        assert loaded_a.user_id == user_a
        assert loaded_b.timezone == "Europe/Lisbon"
        assert loaded_b.user_id == user_b
