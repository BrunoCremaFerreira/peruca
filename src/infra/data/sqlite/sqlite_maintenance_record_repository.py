from datetime import date
from typing import List, Optional

from domain.entities import MaintenanceRecord
from domain.interfaces.vehicle_repository import MaintenanceRecordRepository
from infra.data.sqlite.sqlite_base_repository import SqliteBaseRepository


class SqliteMaintenanceRecordRepository(
    SqliteBaseRepository, MaintenanceRecordRepository
):
    """
    Maintenance record Sqlite implementation repository.

    performed_at is stored as an ISO ``YYYY-MM-DD`` string so lexical ordering
    matches chronological ordering (the DESC index feeds "últimas manutenções").
    """

    def __init__(self, db_path: str):
        super().__init__(db_path=db_path)

    def _startup(self) -> None:
        self.connect()
        self._create_table()

    def _create_table(self) -> None:
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS maintenance_records (
                    id TEXT PRIMARY KEY,
                    vehicle_id TEXT NOT NULL REFERENCES vehicles(id),
                    description TEXT NOT NULL,
                    performed_at DATE NOT NULL,
                    odometer_km INTEGER,
                    when_created TIMESTAMP,
                    when_updated TIMESTAMP DEFAULT NULL,
                    when_deleted TIMESTAMP DEFAULT NULL
                )
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_maintenance_vehicle_date
                    ON maintenance_records(vehicle_id, performed_at DESC)
            """)

    def add(self, record: MaintenanceRecord) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO maintenance_records
                    (id, vehicle_id, description, performed_at, odometer_km, when_created)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    record.id,
                    record.vehicle_id,
                    record.description,
                    self._date_to_str(record.performed_at),
                    record.odometer_km,
                    record.when_created,
                ),
            )

    def get_by_id(self, record_id: str) -> Optional[MaintenanceRecord]:
        cursor = self.conn.execute(
            self._select_sql() + " WHERE id = ?", (record_id,)
        )
        row = cursor.fetchone()
        return self._map(row) if row else None

    def get_all_by_vehicle_id(
        self, vehicle_id: str, limit: Optional[int] = None
    ) -> List[MaintenanceRecord]:
        sql = self._select_sql() + (
            " WHERE vehicle_id = ? ORDER BY performed_at DESC, when_created DESC"
        )
        params = [vehicle_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        cursor = self.conn.execute(sql, tuple(params))
        return [self._map(row) for row in cursor.fetchall()]

    def update(self, record: MaintenanceRecord) -> None:
        with self.conn:
            self.conn.execute(
                """UPDATE maintenance_records
                    SET description = ?, performed_at = ?, odometer_km = ?,
                        when_updated = ?
                    WHERE id = ?""",
                (
                    record.description,
                    self._date_to_str(record.performed_at),
                    record.odometer_km,
                    record.when_updated,
                    record.id,
                ),
            )

    def delete(self, record_id: str) -> None:
        with self.conn:
            self.conn.execute(
                "DELETE FROM maintenance_records WHERE id = ?", (record_id,)
            )

    def delete_all_by_vehicle_id(self, vehicle_id: str) -> None:
        with self.conn:
            self.conn.execute(
                "DELETE FROM maintenance_records WHERE vehicle_id = ?", (vehicle_id,)
            )

    @staticmethod
    def _select_sql() -> str:
        return (
            "SELECT id, vehicle_id, description, performed_at, odometer_km, "
            "when_created, when_updated, when_deleted FROM maintenance_records"
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

    def _map(self, row) -> MaintenanceRecord:
        return MaintenanceRecord(
            id=row["id"],
            vehicle_id=row["vehicle_id"],
            description=row["description"],
            performed_at=self._str_to_date(row["performed_at"]),
            odometer_km=row["odometer_km"],
            when_created=row["when_created"],
            when_updated=row["when_updated"],
            when_deleted=row["when_deleted"],
        )
