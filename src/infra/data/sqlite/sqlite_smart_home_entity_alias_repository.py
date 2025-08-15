from typing import List, Optional
from domain.entities import SmartHomeEntityAlias
from domain.interfaces.data_repository import SmartHomeEntityAliasRepository
from infra.data.sqlite.sqlite_base_repository import SqliteBaseRepository


class SqliteSmartHomeEntityAliasRepository(SqliteBaseRepository, SmartHomeEntityAliasRepository):
    
    def __init__(self, db_path: str):
        super().__init__(db_path=db_path)

    def _startup(self) -> None:
        self.connect()
        self._create_table()

    def _create_table(self) -> None:
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS smart_home_entity_alias (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    alias TEXT NOT NULL,
                    when_created TIMESTAMP,
                    when_updated TIMESTAMP DEFAULT NULL,
                    when_deleted TIMESTAMP DEFAULT NULL
                )
            """)
    
    def add(self, entity_alias: SmartHomeEntityAlias):
        """
        Add Smart Home Entity Alias
        """
        with self.conn:
            self.conn.execute(
                "INSERT INTO smart_home_entity_alias (id, external_id, alias, when_created) VALUES (?, ?, ?, ?)",
                (entity_alias.id, entity_alias.entity_id, entity_alias.alias, entity_alias.when_created)
            )

    def get_by_entity_id(self, entity_id: str) -> Optional[SmartHomeEntityAlias]:
        """
        Get Smart Home Entity Alias by Entity Id
        """
        cursor = self.conn.execute(
            """SELECT 
                id, 
                entity_id, 
                alias,
                when_created, 
                when_updated, 
                when_deleted 
            FROM 
                smart_home_entity_alias
            WHERE 
                entity_id = ?
            """, (entity_id,))
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
                when_created, 
                when_updated, 
                when_deleted 
            FROM 
                smart_home_entity_alias
            WHERE 
                alias like ?
            """, (f"%{alias}%",))
        rows = cursor.fetchall

        if not rows:
            return {}

        return [self._map_smart_home_entity_alias(row) for row in rows]

    def delete_all(self) -> None:
        """
        Remove all SmartHomeEntityAlias
        """
        with self.conn:
            self.conn.execute("DELETE FROM smart_home_entity_alias")

    def _map_smart_home_entity_alias(self, row):
        return SmartHomeEntityAlias(
            id=row["id"],
            entity_id=row["entity_id"],
            alias=row["alias"],
            when_created=row["when_created"],
            when_updated=row["when_updated"],
            when_deleted=row["when_deleted"])
