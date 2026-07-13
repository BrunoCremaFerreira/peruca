from typing import Optional

from domain.entities import UserSettings
from domain.interfaces.user_settings_repository import UserSettingsRepository
from infra.data.sqlite.sqlite_base_repository import SqliteBaseRepository


class SqliteUserSettingsRepository(SqliteBaseRepository, UserSettingsRepository):
    """
    User settings Sqlite implementation repository.

    ``user_id`` is UNIQUE: the settings are 1:1 with a user, so a second ``add``
    for the same user is a bug, not a second row.
    """

    def __init__(self, db_path: str):
        super().__init__(db_path=db_path)

    def _startup(self) -> None:
        self.connect()
        self._create_table()

    def _create_table(self) -> None:
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL UNIQUE REFERENCES users(id),
                    timezone TEXT NOT NULL,
                    when_created TIMESTAMP,
                    when_updated TIMESTAMP DEFAULT NULL,
                    when_deleted TIMESTAMP DEFAULT NULL
                )
            """)

    def get_by_user_id(self, user_id: str) -> Optional[UserSettings]:
        cursor = self.conn.execute(
            self._select_sql() + " WHERE user_id = ?", (user_id,)
        )
        row = cursor.fetchone()
        return self._map(row) if row else None

    def add(self, user_settings: UserSettings) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO user_settings
                    (id, user_id, timezone, when_created)
                    VALUES (?, ?, ?, ?)""",
                (
                    user_settings.id,
                    user_settings.user_id,
                    user_settings.timezone,
                    user_settings.when_created,
                ),
            )

    def update(self, user_settings: UserSettings) -> None:
        with self.conn:
            self.conn.execute(
                """UPDATE user_settings
                    SET timezone = ?, when_updated = ?
                    WHERE id = ?""",
                (
                    user_settings.timezone,
                    user_settings.when_updated,
                    user_settings.id,
                ),
            )

    @staticmethod
    def _select_sql() -> str:
        return (
            "SELECT id, user_id, timezone, when_created, when_updated, "
            "when_deleted FROM user_settings"
        )

    def _map(self, row) -> UserSettings:
        return UserSettings(
            id=row["id"],
            user_id=row["user_id"],
            timezone=row["timezone"],
            when_created=row["when_created"],
            when_updated=row["when_updated"],
            when_deleted=row["when_deleted"],
        )
