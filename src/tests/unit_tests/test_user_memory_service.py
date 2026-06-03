"""
UserMemoryService Unit Tests (TDD - RED phase)

The service orchestrates the UserMemory lifecycle in total isolation from any
real repository (the repository is a MagicMock).

Behaviours covered:
  - add(UserMemoryAdd) -> str
      * generates a uuid4 id, sets when_created, validates, persists, returns id
      * invalid content / user_id raise ValidationError BEFORE persisting
      * dedup: a content already present (case/whitespace insensitive) is NOT
        persisted again (repo.add not called)
  - get_all_by_user(user_id) -> delegates to repo.get_all_by_user_id
  - delete(memory_id) -> validates uuid4 and calls repo.delete
  - clear_by_user(user_id) -> validates user_id and calls repo.delete_all_by_user_id

Expected to FAIL with ImportError until the service/command/entity exist.
"""

import uuid

import pytest

from domain.commands import UserMemoryAdd
from domain.entities import UserMemory
from domain.exceptions import ValidationError
from domain.services.user_memory_service import UserMemoryService


# ===========================================================================
# Helpers
# ===========================================================================


def _sample_memory(user_id=None, content="Prefere café sem açúcar") -> UserMemory:
    return UserMemory(
        id=str(uuid.uuid4()),
        user_id=user_id or str(uuid.uuid4()),
        content=content,
    )


# ===========================================================================
# TestUserMemoryServiceAdd
# ===========================================================================


class TestUserMemoryServiceAdd:
    def test_add__valid_data__returns_uuid_and_persists(self, user_memory_repo_mock):
        # Arrange
        service = UserMemoryService(user_memory_repo_mock)
        user_id = str(uuid.uuid4())
        # Act
        result = service.add(
            UserMemoryAdd(user_id=user_id, content="Prefere café sem açúcar")
        )
        # Assert
        assert uuid.UUID(result)
        user_memory_repo_mock.add.assert_called_once()

    def test_add__valid_data__sets_when_created_on_entity(
        self, user_memory_repo_mock
    ):
        # Arrange
        service = UserMemoryService(user_memory_repo_mock)
        user_id = str(uuid.uuid4())
        # Act
        service.add(UserMemoryAdd(user_id=user_id, content="Tem um gato chamado Mia"))
        # Assert
        persisted = _added_memory(user_memory_repo_mock)
        assert persisted.when_created is not None

    def test_add__empty_content__raises_and_does_not_persist(
        self, user_memory_repo_mock
    ):
        # Arrange
        service = UserMemoryService(user_memory_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.add(UserMemoryAdd(user_id=str(uuid.uuid4()), content=""))
        assert "content" in str(exc.value.errors)
        user_memory_repo_mock.add.assert_not_called()

    def test_add__invalid_user_id__raises_and_does_not_persist(
        self, user_memory_repo_mock
    ):
        # Arrange
        service = UserMemoryService(user_memory_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.add(UserMemoryAdd(user_id="not-a-uuid", content="Fato qualquer"))
        assert "user_id" in str(exc.value.errors)
        user_memory_repo_mock.add.assert_not_called()


# ===========================================================================
# TestUserMemoryServiceDedup
# ===========================================================================


class TestUserMemoryServiceDedup:
    def test_add__new_content__persists(self, user_memory_repo_mock):
        # Arrange
        user_id = str(uuid.uuid4())
        user_memory_repo_mock.get_all_by_user_id.return_value = [
            _sample_memory(user_id=user_id, content="Mora em São Paulo")
        ]
        service = UserMemoryService(user_memory_repo_mock)
        # Act
        service.add(UserMemoryAdd(user_id=user_id, content="Prefere café sem açúcar"))
        # Assert
        user_memory_repo_mock.add.assert_called_once()

    def test_add__exact_duplicate_content__does_not_persist(
        self, user_memory_repo_mock
    ):
        # Arrange
        user_id = str(uuid.uuid4())
        user_memory_repo_mock.get_all_by_user_id.return_value = [
            _sample_memory(user_id=user_id, content="Prefere café sem açúcar")
        ]
        service = UserMemoryService(user_memory_repo_mock)
        # Act
        service.add(UserMemoryAdd(user_id=user_id, content="Prefere café sem açúcar"))
        # Assert
        user_memory_repo_mock.add.assert_not_called()

    def test_add__duplicate_with_case_and_whitespace_variation__does_not_persist(
        self, user_memory_repo_mock
    ):
        # Arrange
        user_id = str(uuid.uuid4())
        user_memory_repo_mock.get_all_by_user_id.return_value = [
            _sample_memory(user_id=user_id, content="Prefere café sem açúcar")
        ]
        service = UserMemoryService(user_memory_repo_mock)
        # Act (different case and surrounding whitespace -> normalized duplicate)
        service.add(
            UserMemoryAdd(user_id=user_id, content="  PREFERE CAFÉ SEM AÇÚCAR  ")
        )
        # Assert
        user_memory_repo_mock.add.assert_not_called()


# ===========================================================================
# TestUserMemoryServiceGetAllByUser
# ===========================================================================


class TestUserMemoryServiceGetAllByUser:
    def test_get_all_by_user__delegates_and_returns_list(self, user_memory_repo_mock):
        # Arrange
        user_id = str(uuid.uuid4())
        memories = [
            _sample_memory(user_id=user_id, content="Fato A"),
            _sample_memory(user_id=user_id, content="Fato B"),
        ]
        user_memory_repo_mock.get_all_by_user_id.return_value = memories
        service = UserMemoryService(user_memory_repo_mock)
        # Act
        result = service.get_all_by_user(user_id)
        # Assert
        assert result == memories
        user_memory_repo_mock.get_all_by_user_id.assert_called_once_with(user_id)


# ===========================================================================
# TestUserMemoryServiceDelete
# ===========================================================================


class TestUserMemoryServiceDelete:
    def test_delete__valid_id__calls_repository(self, user_memory_repo_mock):
        # Arrange
        service = UserMemoryService(user_memory_repo_mock)
        memory_id = str(uuid.uuid4())
        # Act
        service.delete(memory_id)
        # Assert
        user_memory_repo_mock.delete.assert_called_once_with(memory_id)

    def test_delete__invalid_id__raises_and_does_not_call_repository(
        self, user_memory_repo_mock
    ):
        # Arrange
        service = UserMemoryService(user_memory_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError):
            service.delete("not-a-uuid")
        user_memory_repo_mock.delete.assert_not_called()


# ===========================================================================
# TestUserMemoryServiceClearByUser
# ===========================================================================


class TestUserMemoryServiceClearByUser:
    def test_clear_by_user__valid_user_id__calls_repository(
        self, user_memory_repo_mock
    ):
        # Arrange
        service = UserMemoryService(user_memory_repo_mock)
        user_id = str(uuid.uuid4())
        # Act
        service.clear_by_user(user_id)
        # Assert
        user_memory_repo_mock.delete_all_by_user_id.assert_called_once_with(user_id)

    def test_clear_by_user__invalid_user_id__raises(self, user_memory_repo_mock):
        # Arrange
        service = UserMemoryService(user_memory_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError):
            service.clear_by_user("not-a-uuid")
        user_memory_repo_mock.delete_all_by_user_id.assert_not_called()


# ===========================================================================
# Internal helpers
# ===========================================================================


def _added_memory(repo_mock) -> UserMemory:
    """Extract the UserMemory passed to repo.add(...) (positional or keyword)."""
    args, kwargs = repo_mock.add.call_args
    if args:
        return args[0]
    return next(iter(kwargs.values()))
