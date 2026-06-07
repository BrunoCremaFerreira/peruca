"""
SqliteBaseRepository WAL mode unit tests.

Contract:
  After `connect()` is called on a file-backed DB, the SQLite connection must
  have WAL journal mode active. SQLite :memory: databases always use the
  "memory" journal mode and cannot be switched to WAL — that is a hard engine
  constraint, not a bug in the implementation.

A minimal concrete subclass (_NoOpRepository) satisfies the ABC without any
startup side effects so tests can call connect() directly and in isolation.
"""

import tempfile
import os

from infra.data.sqlite.sqlite_base_repository import SqliteBaseRepository


class _NoOpRepository(SqliteBaseRepository):
    """Minimal concrete subclass that satisfies the SqliteBaseRepository ABC."""

    def _startup(self) -> None:
        pass

    def _create_table(self) -> None:
        pass


class TestSqliteBaseRepositoryConnectEnablesWAL:
    """After connect() on a file-backed DB, the journal_mode must be 'wal'."""

    def test_connect__file_db__journal_mode_is_wal(self, tmp_path):
        db_file = str(tmp_path / "test.db")
        repo = _NoOpRepository(db_path=db_file)
        repo.connect()

        try:
            cursor = repo.conn.execute("PRAGMA journal_mode")
            row = cursor.fetchone()
            journal_mode = row[0] if row else None
        finally:
            repo.close()

        assert journal_mode == "wal", (
            f"Expected journal_mode='wal' after connect() with a file-backed DB, "
            f"got {journal_mode!r}. SqliteBaseRepository.connect() must execute "
            "'PRAGMA journal_mode=WAL'."
        )

    def test_connect__called_twice__still_journal_mode_wal(self, tmp_path):
        """WAL must remain active after closing and reopening the connection."""
        db_file = str(tmp_path / "reconnect.db")
        repo = _NoOpRepository(db_path=db_file)
        repo.connect()
        repo.close()
        repo.connect()

        try:
            cursor = repo.conn.execute("PRAGMA journal_mode")
            row = cursor.fetchone()
            journal_mode = row[0] if row else None
        finally:
            repo.close()

        assert journal_mode == "wal", (
            f"After a reconnect, journal_mode should still be 'wal', got {journal_mode!r}."
        )
