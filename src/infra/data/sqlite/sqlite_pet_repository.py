import json
from datetime import date
from typing import List, Optional

from domain.entities import Pet
from domain.interfaces.pet_repository import PetRepository
from infra.data.sqlite.sqlite_base_repository import SqliteBaseRepository


class SqlitePetRepository(SqliteBaseRepository, PetRepository):
    """
    Pet Sqlite implementation repository.

    nicknames are stored as a JSON array in a TEXT column: they are a value object
    of the Pet aggregate (no identity of their own), all matching happens in Python
    (never SQL), and the JSON array preserves order for free (index 0 = primary).
    birth_date is stored as an ISO ``YYYY-MM-DD`` string (nullable).
    """

    def __init__(self, db_path: str):
        super().__init__(db_path=db_path)

    def _startup(self) -> None:
        self.connect()
        self._create_table()

    def _create_table(self) -> None:
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS pets (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    name TEXT NOT NULL,
                    nicknames TEXT,
                    birth_date DATE,
                    sex TEXT,
                    species TEXT,
                    description TEXT,
                    when_created TIMESTAMP,
                    when_updated TIMESTAMP DEFAULT NULL,
                    when_deleted TIMESTAMP DEFAULT NULL,
                    UNIQUE(user_id, name)
                )
            """)

    def add(self, pet: Pet) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO pets
                    (id, user_id, name, nicknames, birth_date, sex, species,
                     description, when_created)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pet.id,
                    pet.user_id,
                    pet.name,
                    self._nicknames_to_str(pet.nicknames),
                    self._date_to_str(pet.birth_date),
                    pet.sex,
                    pet.species,
                    pet.description,
                    pet.when_created,
                ),
            )

    def get_by_id(self, pet_id: str) -> Optional[Pet]:
        cursor = self.conn.execute(
            self._select_sql() + " WHERE id = ?", (pet_id,)
        )
        row = cursor.fetchone()
        return self._map(row) if row else None

    def get_all_by_user_id(self, user_id: str) -> List[Pet]:
        cursor = self.conn.execute(
            self._select_sql() + " WHERE user_id = ?", (user_id,)
        )
        return [self._map(row) for row in cursor.fetchall()]

    def update(self, pet: Pet) -> None:
        with self.conn:
            self.conn.execute(
                """UPDATE pets
                    SET name = ?, nicknames = ?, birth_date = ?, sex = ?,
                        species = ?, description = ?, when_updated = ?
                    WHERE id = ?""",
                (
                    pet.name,
                    self._nicknames_to_str(pet.nicknames),
                    self._date_to_str(pet.birth_date),
                    pet.sex,
                    pet.species,
                    pet.description,
                    pet.when_updated,
                    pet.id,
                ),
            )

    def delete(self, pet_id: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM pets WHERE id = ?", (pet_id,))

    @staticmethod
    def _select_sql() -> str:
        return (
            "SELECT id, user_id, name, nicknames, birth_date, sex, species, "
            "description, when_created, when_updated, when_deleted FROM pets"
        )

    @staticmethod
    def _nicknames_to_str(value) -> str:
        return json.dumps(list(value or []), ensure_ascii=False)

    @staticmethod
    def _str_to_nicknames(value) -> List[str]:
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []

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

    def _map(self, row) -> Pet:
        return Pet(
            id=row["id"],
            user_id=row["user_id"],
            name=row["name"],
            nicknames=self._str_to_nicknames(row["nicknames"]),
            birth_date=self._str_to_date(row["birth_date"]),
            sex=row["sex"],
            species=row["species"],
            description=row["description"],
            when_created=row["when_created"],
            when_updated=row["when_updated"],
            when_deleted=row["when_deleted"],
        )
