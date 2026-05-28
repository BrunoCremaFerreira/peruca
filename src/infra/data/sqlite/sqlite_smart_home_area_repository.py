from typing import List, Optional

from domain.entities import SmartHomeArea
from domain.interfaces.data_repository import SmartHomeAreaRepository
from infra.data.sqlite.sqlite_base_repository import SqliteBaseRepository


class SqliteSmartHomeAreaRepository(SqliteBaseRepository, SmartHomeAreaRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path=db_path)

    def _startup(self) -> None:
        self.connect()
        self._create_table()

    def _create_table(self) -> None:
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS smart_home_area (
                    area_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    when_created TIMESTAMP,
                    when_updated TIMESTAMP DEFAULT NULL,
                    when_deleted TIMESTAMP DEFAULT NULL
                )
                """
            )

    def add(self, area: SmartHomeArea) -> None:
        """
        Add Smart Home Area
        """
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO smart_home_area
                    (area_id, name, when_created)
                VALUES (?, ?, ?)
                """,
                (
                    area.area_id,
                    area.name,
                    area.when_created,
                ),
            )

    def get_all(self) -> List[SmartHomeArea]:
        """
        Get all Smart Home Areas
        """
        with self.conn as conn:
            cursor = conn.execute(
                """
                SELECT
                    area_id,
                    name,
                    when_created,
                    when_updated,
                    when_deleted
                FROM smart_home_area
                """
            )
            rows = cursor.fetchall()

        return [self._map_smart_home_area(row) for row in rows]

    def get_by_area_id(self, area_id: str) -> Optional[SmartHomeArea]:
        """
        Get Smart Home Area by area_id
        """
        cursor = self.conn.execute(
            """
            SELECT
                area_id,
                name,
                when_created,
                when_updated,
                when_deleted
            FROM smart_home_area
            WHERE area_id = ?
            """,
            (area_id,),
        )
        row = cursor.fetchone()
        return self._map_smart_home_area(row) if row else None

    def delete_all(self) -> None:
        """
        Remove all SmartHomeArea
        """
        with self.conn:
            self.conn.execute("DELETE FROM smart_home_area")

    def _map_smart_home_area(self, row) -> SmartHomeArea:
        return SmartHomeArea(
            area_id=row["area_id"],
            name=row["name"],
            when_created=row["when_created"],
            when_updated=row["when_updated"],
            when_deleted=row["when_deleted"],
        )
