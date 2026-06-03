from typing import List, Optional

from domain.entities import UserMemory
from domain.interfaces.data_repository import UserMemoryRepository
from infra.data.sqlite.sqlite_base_repository import SqliteBaseRepository


class SqliteUserMemoryRepository(SqliteBaseRepository, UserMemoryRepository):
    """
    UserMemory Sqlite implementation repository
    """

    def __init__(self, db_path: str):
        super().__init__(db_path=db_path)

    def _startup(self) -> None:
        self.connect()
        self._create_table()

    def _create_table(self) -> None:
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS user_memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    when_created TIMESTAMP,
                    when_updated TIMESTAMP DEFAULT NULL,
                    when_deleted TIMESTAMP DEFAULT NULL
                )
            """)

    def add(self, memory: UserMemory):
        with self.conn:
            self.conn.execute(
                "INSERT INTO user_memories (id, user_id, content, when_created) VALUES (?, ?, ?, ?)",
                (memory.id, memory.user_id, memory.content, memory.when_created),
            )

    def get_by_id(self, memory_id: str) -> Optional[UserMemory]:
        cursor = self.conn.execute(
            """SELECT
                id,
                user_id,
                content,
                when_created,
                when_updated,
                when_deleted
            FROM
                user_memories
            WHERE
                id = ?
            """,
            (memory_id,),
        )
        row = cursor.fetchone()
        return self._map_user_memory(row) if row else None

    def get_all_by_user_id(self, user_id: str) -> List[UserMemory]:
        cursor = self.conn.execute(
            """SELECT
                id,
                user_id,
                content,
                when_created,
                when_updated,
                when_deleted
            FROM
                user_memories
            WHERE
                user_id = ?
            """,
            (user_id,),
        )
        return [self._map_user_memory(row) for row in cursor.fetchall()]

    def delete(self, memory_id: str):
        with self.conn:
            self.conn.execute(
                "DELETE FROM user_memories WHERE id = ?", (memory_id,)
            )

    def delete_all_by_user_id(self, user_id: str):
        with self.conn:
            self.conn.execute(
                "DELETE FROM user_memories WHERE user_id = ?", (user_id,)
            )

    def _map_user_memory(self, row):
        return UserMemory(
            id=row["id"],
            user_id=row["user_id"],
            content=row["content"],
            when_created=row["when_created"],
            when_updated=row["when_updated"],
            when_deleted=row["when_deleted"],
        )

    def close(self):
        self.conn.close()
