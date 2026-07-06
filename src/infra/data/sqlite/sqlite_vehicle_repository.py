from typing import List, Optional

from domain.entities import Vehicle
from domain.interfaces.vehicle_repository import VehicleRepository
from infra.data.sqlite.sqlite_base_repository import SqliteBaseRepository


class SqliteVehicleRepository(SqliteBaseRepository, VehicleRepository):
    """
    Vehicle Sqlite implementation repository.
    """

    def __init__(self, db_path: str):
        super().__init__(db_path=db_path)

    def _startup(self) -> None:
        self.connect()
        self._create_table()

    def _create_table(self) -> None:
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS vehicles (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    name TEXT NOT NULL,
                    brand TEXT,
                    model TEXT,
                    year INTEGER,
                    when_created TIMESTAMP,
                    when_updated TIMESTAMP DEFAULT NULL,
                    when_deleted TIMESTAMP DEFAULT NULL,
                    UNIQUE(user_id, name)
                )
            """)

    def add(self, vehicle: Vehicle) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO vehicles
                    (id, user_id, name, brand, model, year, when_created)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    vehicle.id,
                    vehicle.user_id,
                    vehicle.name,
                    vehicle.brand,
                    vehicle.model,
                    vehicle.year,
                    vehicle.when_created,
                ),
            )

    def get_by_id(self, vehicle_id: str) -> Optional[Vehicle]:
        cursor = self.conn.execute(
            self._select_sql() + " WHERE id = ?", (vehicle_id,)
        )
        row = cursor.fetchone()
        return self._map(row) if row else None

    def get_all_by_user_id(self, user_id: str) -> List[Vehicle]:
        cursor = self.conn.execute(
            self._select_sql() + " WHERE user_id = ?", (user_id,)
        )
        return [self._map(row) for row in cursor.fetchall()]

    def update(self, vehicle: Vehicle) -> None:
        with self.conn:
            self.conn.execute(
                """UPDATE vehicles
                    SET name = ?, brand = ?, model = ?, year = ?, when_updated = ?
                    WHERE id = ?""",
                (
                    vehicle.name,
                    vehicle.brand,
                    vehicle.model,
                    vehicle.year,
                    vehicle.when_updated,
                    vehicle.id,
                ),
            )

    def delete(self, vehicle_id: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,))

    @staticmethod
    def _select_sql() -> str:
        return (
            "SELECT id, user_id, name, brand, model, year, "
            "when_created, when_updated, when_deleted FROM vehicles"
        )

    @staticmethod
    def _map(row) -> Vehicle:
        return Vehicle(
            id=row["id"],
            user_id=row["user_id"],
            name=row["name"],
            brand=row["brand"],
            model=row["model"],
            year=row["year"],
            when_created=row["when_created"],
            when_updated=row["when_updated"],
            when_deleted=row["when_deleted"],
        )
