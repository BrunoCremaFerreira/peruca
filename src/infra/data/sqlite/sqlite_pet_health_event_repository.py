from datetime import date
from typing import List, Optional

from domain.entities import PetHealthEvent
from domain.interfaces.pet_repository import PetHealthEventRepository
from infra.data.sqlite.sqlite_base_repository import SqliteBaseRepository


class SqlitePetHealthEventRepository(
    SqliteBaseRepository, PetHealthEventRepository
):
    """
    Pet health event Sqlite implementation repository.

    occurred_at is stored as an ISO ``YYYY-MM-DD`` string so lexical ordering
    matches chronological ordering (the DESC index feeds the query graph).
    """

    def __init__(self, db_path: str):
        super().__init__(db_path=db_path)

    def _startup(self) -> None:
        self.connect()
        self._create_table()

    def _create_table(self) -> None:
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS pet_health_events (
                    id TEXT PRIMARY KEY,
                    pet_id TEXT NOT NULL REFERENCES pets(id),
                    event_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    occurred_at DATE NOT NULL,
                    when_created TIMESTAMP,
                    when_updated TIMESTAMP DEFAULT NULL,
                    when_deleted TIMESTAMP DEFAULT NULL
                )
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pet_health_pet_date
                    ON pet_health_events(pet_id, occurred_at DESC)
            """)

    def add(self, event: PetHealthEvent) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO pet_health_events
                    (id, pet_id, event_type, description, occurred_at, when_created)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    event.id,
                    event.pet_id,
                    event.event_type,
                    event.description,
                    self._date_to_str(event.occurred_at),
                    event.when_created,
                ),
            )

    def get_by_id(self, event_id: str) -> Optional[PetHealthEvent]:
        cursor = self.conn.execute(
            self._select_sql() + " WHERE id = ?", (event_id,)
        )
        row = cursor.fetchone()
        return self._map(row) if row else None

    def get_all_by_pet_id(
        self, pet_id: str, limit: Optional[int] = None
    ) -> List[PetHealthEvent]:
        sql = self._select_sql() + (
            " WHERE pet_id = ? ORDER BY occurred_at DESC, when_created DESC"
        )
        params = [pet_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        cursor = self.conn.execute(sql, tuple(params))
        return [self._map(row) for row in cursor.fetchall()]

    def update(self, event: PetHealthEvent) -> None:
        with self.conn:
            self.conn.execute(
                """UPDATE pet_health_events
                    SET event_type = ?, description = ?, occurred_at = ?,
                        when_updated = ?
                    WHERE id = ?""",
                (
                    event.event_type,
                    event.description,
                    self._date_to_str(event.occurred_at),
                    event.when_updated,
                    event.id,
                ),
            )

    def delete(self, event_id: str) -> None:
        with self.conn:
            self.conn.execute(
                "DELETE FROM pet_health_events WHERE id = ?", (event_id,)
            )

    def delete_all_by_pet_id(self, pet_id: str) -> None:
        with self.conn:
            self.conn.execute(
                "DELETE FROM pet_health_events WHERE pet_id = ?", (pet_id,)
            )

    @staticmethod
    def _select_sql() -> str:
        return (
            "SELECT id, pet_id, event_type, description, occurred_at, "
            "when_created, when_updated, when_deleted FROM pet_health_events"
        )

    @staticmethod
    def _date_to_str(value) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _str_to_date(value) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value)[:10])

    def _map(self, row) -> PetHealthEvent:
        return PetHealthEvent(
            id=row["id"],
            pet_id=row["pet_id"],
            event_type=row["event_type"],
            description=row["description"],
            occurred_at=self._str_to_date(row["occurred_at"]),
            when_created=row["when_created"],
            when_updated=row["when_updated"],
            when_deleted=row["when_deleted"],
        )
