import time
from typing import Dict, List, Optional, Tuple
from domain.entities import SmartHomeEntityAlias
from domain.interfaces.data_repository import SmartHomeEntityAliasRepository
from infra.data.sqlite.sqlite_base_repository import SqliteBaseRepository


class SqliteSmartHomeEntityAliasRepository(
    SqliteBaseRepository, SmartHomeEntityAliasRepository
):
    def __init__(self, db_path: str, aliases_cache_ttl: float = 60.0):
        self.aliases_cache_ttl = aliases_cache_ttl
        self._aliases_cache: Dict[str, Tuple[float, List[SmartHomeEntityAlias]]] = {}
        super().__init__(db_path=db_path)

    def _startup(self) -> None:
        self.connect()
        self._create_table()
        self._ensure_area_id_column()

    def _create_table(self) -> None:
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS smart_home_entity_alias (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    alias TEXT NOT NULL,
                    area_id TEXT,
                    when_created TIMESTAMP,
                    when_updated TIMESTAMP DEFAULT NULL,
                    when_deleted TIMESTAMP DEFAULT NULL
                )
            """)

    def _ensure_area_id_column(self) -> None:
        """
        Idempotent migration: when the table already exists from a previous
        deployment without the area_id column, add it via ALTER TABLE.
        """
        cursor = self.conn.execute("PRAGMA table_info(smart_home_entity_alias)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "area_id" not in columns:
            with self.conn:
                self.conn.execute(
                    "ALTER TABLE smart_home_entity_alias ADD COLUMN area_id TEXT"
                )

    def add(self, entity_alias: SmartHomeEntityAlias):
        """
        Add Smart Home Entity Alias
        """
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO smart_home_entity_alias
                    (id, entity_id, alias, area_id, when_created)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    entity_alias.id,
                    entity_alias.entity_id,
                    entity_alias.alias,
                    entity_alias.area_id,
                    entity_alias.when_created,
                ),
            )
        self._aliases_cache.clear()

    def get_by_entity_id(self, entity_id: str) -> Optional[SmartHomeEntityAlias]:
        """
        Get Smart Home Entity Alias by Entity Id
        """
        cursor = self.conn.execute(
            """SELECT
                id,
                entity_id,
                alias,
                area_id,
                when_created,
                when_updated,
                when_deleted
            FROM
                smart_home_entity_alias
            WHERE
                entity_id = ?
            """,
            (entity_id,),
        )
        row = cursor.fetchone()
        return self._map_smart_home_entity_alias(row) if row else None

    def get_by_alias(self, alias: str) -> List[SmartHomeEntityAlias]:
        """
        Get Smart Home Entity Alias
        """
        cursor = self.conn.execute(
            """SELECT
                id,
                entity_id,
                alias,
                area_id,
                when_created,
                when_updated,
                when_deleted
            FROM
                smart_home_entity_alias
            WHERE
                alias like ?
            """,
            (f"%{alias}%",),
        )

        return [self._map_smart_home_entity_alias(row) for row in cursor.fetchall()]

    def get_all(self, entity_id_starts_with: str = "") -> List[SmartHomeEntityAlias]:
        """
        Retrieve all SmartHomeEntityAlias records from the database.
        """
        now = time.monotonic()
        cache_entry = self._aliases_cache.get(entity_id_starts_with)
        if cache_entry is not None:
            cached_at, cached_result = cache_entry
            if now - cached_at < self.aliases_cache_ttl:
                return cached_result

        base_query = """
            SELECT
                id,
                entity_id,
                alias,
                area_id,
                when_created,
                when_updated,
                when_deleted
            FROM
                smart_home_entity_alias
        """

        params: Optional[tuple] = None
        if entity_id_starts_with:
            base_query += " WHERE entity_id LIKE ?"
            params = (f"{entity_id_starts_with}%",)

        with self.conn as conn:
            cursor = conn.execute(base_query, params or ())
            rows = cursor.fetchall()

        result = [self._map_smart_home_entity_alias(row) for row in rows]
        self._aliases_cache[entity_id_starts_with] = (time.monotonic(), result)
        return result

    def delete_all(self) -> None:
        """
        Remove all SmartHomeEntityAlias
        """
        with self.conn:
            self.conn.execute("DELETE FROM smart_home_entity_alias")
        self._aliases_cache.clear()

    def _map_smart_home_entity_alias(self, row):
        return SmartHomeEntityAlias(
            id=row["id"],
            entity_id=row["entity_id"],
            alias=row["alias"],
            area_id=row["area_id"],
            when_created=row["when_created"],
            when_updated=row["when_updated"],
            when_deleted=row["when_deleted"],
        )
