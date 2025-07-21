from typing import Optional, List
import uuid

from domain.entities import User
from domain.interfaces.repository import UserRepository
from infra.data.sqlite_base_repository import SqliteBaseRepository

class SqliteUserRepository(SqliteBaseRepository, UserRepository):
    """
    User Sqlite implementation repository
    """

    def __init__(self, db_path: str):
        super().__init__(db_path=db_path)

    def _startup(self) -> None:
        self.connect()
        self._create_table()
        if not self.get_all():
            print("[UserRepositorySqlite]: Creating Admin user...")
            user_id = str(uuid.uuid4())
            admin_user = User(id=user_id, external_id=user_id, name="Admin", summary="")
            self.add(admin_user)
            print(f"[UserRepositorySqlite]: Admin user was created {admin_user}.")

    def _create_table(self) -> None:
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    external_id NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    summary TEXT,
                    when_created TIMESTAMP,
                    when_updated TIMESTAMP DEFAULT NULL,
                    when_deleted TIMESTAMP DEFAULT NULL
                )
            """)

    def add(self, user: User):
        with self.conn:
            self.conn.execute(
                "INSERT INTO users (id, external_id, name, summary, when_created) VALUES (?, ?, ?, ?, ?)",
                (user.id, user.external_id, user.name, user.summary, user.when_created)
            )

    def get_by_id(self, user_id: str) -> Optional[User]:
        cursor = self.conn.execute(
            """SELECT 
                id, 
                external_id, 
                name, 
                summary, 
                when_created, 
                when_updated, 
                when_deleted 
            FROM 
                users 
            WHERE 
                id = ?
            """, (user_id,))
        row = cursor.fetchone()
        return self._map_user(row) if row else None
    
    def get_by_external_id(self, external_id: str) -> Optional[User]:
        cursor = self.conn.execute(
            """SELECT 
                id, 
                external_id, 
                name, 
                summary, 
                when_created, 
                when_updated, 
                when_deleted 
            FROM 
                users 
            WHERE 
                external_id = ?
            """, (external_id,))
        row = cursor.fetchone()
        return self._map_user(row) if row else None

    def update(self, user: User):
        with self.conn:
            self.conn.execute(
                """UPDATE users SET 
                        name = ?, 
                        summary = ?, 
                        external_id = ? 
                    WHERE id = ?
                """,
                (user.name, user.summary, user.external_id, user.id)
            )

    def delete(self, user_id: str):
        with self.conn:
            self.conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def get_all(self) -> List[User]:
        cursor = self.conn.execute("""
                            SELECT 
                                id, 
                                external_id, 
                                name, 
                                summary, 
                                when_created, 
                                when_updated,
                                when_deleted 
                            FROM users
                """)
        return [self._map_user(row) for row in cursor.fetchall()]

    def _map_user(self, row):
        return User(
            id=row["id"],
            external_id=row["external_id"],
            name=row["name"],
            summary=row["summary"],
            when_created=row["when_created"],
            when_updated=row["when_updated"],
            when_deleted=row["when_deleted"])

    def close(self):
        self.conn.close()
