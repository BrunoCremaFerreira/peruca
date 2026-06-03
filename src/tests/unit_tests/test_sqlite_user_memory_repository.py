"""
SqliteUserMemoryRepository Unit Tests (TDD - RED phase)

These use a REAL temporary SQLite database (file at sqlite_db_path fixture,
cleaned before/after). The repository is synchronous and creates the
`user_memories` table on startup, following the SqliteUserRepository pattern.

Behaviours covered:
  - add + get_by_id round-trip returns the entity
  - get_all_by_user_id filters by user (two distinct users inserted)
  - delete removes a single memory
  - delete_all_by_user_id removes only the target user's memories
  - get_by_id for a non-existent id returns None

Expected to FAIL with ImportError until
infra.data.sqlite.sqlite_user_memory_repository.SqliteUserMemoryRepository exists.
"""

import uuid

import pytest

from domain.entities import UserMemory
from infra.data.sqlite.sqlite_user_memory_repository import (
    SqliteUserMemoryRepository,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _make_repo(sqlite_db_path) -> SqliteUserMemoryRepository:
    return SqliteUserMemoryRepository(db_path=f"sqlite://{sqlite_db_path}")


def _sample_memory(user_id, content="Prefere café sem açúcar") -> UserMemory:
    from datetime import datetime, timezone

    return UserMemory(
        id=str(uuid.uuid4()),
        user_id=user_id,
        content=content,
        when_created=datetime.now(timezone.utc),
    )


# ===========================================================================
# TestSqliteUserMemoryRepository
# ===========================================================================


class TestSqliteUserMemoryRepository:
    def test_add_then_get_by_id__returns_entity(self, sqlite_db_path):
        # Arrange
        repo = _make_repo(sqlite_db_path)
        user_id = str(uuid.uuid4())
        memory = _sample_memory(user_id=user_id, content="Tem um gato chamado Mia")
        try:
            # Act
            repo.add(memory)
            fetched = repo.get_by_id(memory.id)
            # Assert
            assert fetched is not None
            assert fetched.id == memory.id
            assert fetched.user_id == user_id
            assert fetched.content == "Tem um gato chamado Mia"
        finally:
            repo.close()

    def test_get_by_id__non_existent__returns_none(self, sqlite_db_path):
        # Arrange
        repo = _make_repo(sqlite_db_path)
        try:
            # Act
            result = repo.get_by_id(str(uuid.uuid4()))
            # Assert
            assert result is None
        finally:
            repo.close()

    def test_get_all_by_user_id__filters_by_user(self, sqlite_db_path):
        # Arrange
        repo = _make_repo(sqlite_db_path)
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())
        try:
            repo.add(_sample_memory(user_id=user_a, content="Fato A1"))
            repo.add(_sample_memory(user_id=user_a, content="Fato A2"))
            repo.add(_sample_memory(user_id=user_b, content="Fato B1"))
            # Act
            result_a = repo.get_all_by_user_id(user_a)
            result_b = repo.get_all_by_user_id(user_b)
            # Assert
            assert len(result_a) == 2
            assert len(result_b) == 1
            assert all(m.user_id == user_a for m in result_a)
            assert all(m.user_id == user_b for m in result_b)
        finally:
            repo.close()

    def test_delete__removes_single_memory(self, sqlite_db_path):
        # Arrange
        repo = _make_repo(sqlite_db_path)
        user_id = str(uuid.uuid4())
        memory = _sample_memory(user_id=user_id, content="Fato a remover")
        try:
            repo.add(memory)
            # Act
            repo.delete(memory.id)
            # Assert
            assert repo.get_by_id(memory.id) is None
        finally:
            repo.close()

    def test_delete_all_by_user_id__removes_only_target_user(self, sqlite_db_path):
        # Arrange
        repo = _make_repo(sqlite_db_path)
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())
        try:
            repo.add(_sample_memory(user_id=user_a, content="A1"))
            repo.add(_sample_memory(user_id=user_a, content="A2"))
            repo.add(_sample_memory(user_id=user_b, content="B1"))
            # Act
            repo.delete_all_by_user_id(user_a)
            # Assert
            assert repo.get_all_by_user_id(user_a) == []
            assert len(repo.get_all_by_user_id(user_b)) == 1
        finally:
            repo.close()
