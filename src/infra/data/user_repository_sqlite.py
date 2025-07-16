import sqlite3
from typing import Optional, List
import uuid

from domain.entities import User
from domain.interfaces.repository import UserRepository

class UserRepositorySqlite(UserRepository):
    def __init__(self, db_path: str):
        self.db_path = db_path.replace("sqlite://", "")
        self._startup()

    def _startup(self):
        self.connect()
        self._create_table()
        if not self.list():
            print("[UserRepositorySqlite]: Creating Admin user...")
            admin_user = User(id=str(uuid.uuid4()), name="Admin", summary="")
            self.add(admin_user)
            print(f"[UserRepositorySqlite]: Admin user was created {admin_user}.")

    def _create_table(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    summary TEXT
                )
            """)

    def connect(self):
        print(f"[UserRepositorySqlite]: Connecting to '{self.db_path}'...")
        self.conn = sqlite3.connect(database=self.db_path)

    def add(self, user: User):
        with self.conn:
            self.conn.execute(
                "INSERT INTO users (id, name, summary) VALUES (?, ?, ?)",
                (user.id, user.name, user.summary)
            )

    def get_by_id(self, user_id: str) -> Optional[User]:
        cursor = self.conn.execute(
            "SELECT id, name, summary FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return User(*row) if row else None

    def update(self, user: User):
        with self.conn:
            self.conn.execute(
                "UPDATE users SET name = ?, summary = ? WHERE id = ?",
                (user.name, user.summary, user.id)
            )

    def delete(self, user_id: str):
        with self.conn:
            self.conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def list(self) -> List[User]:
        cursor = self.conn.execute("SELECT id, name, summary FROM users")
        return [User(*row) for row in cursor.fetchall()]

    def close(self):
        self.conn.close()
