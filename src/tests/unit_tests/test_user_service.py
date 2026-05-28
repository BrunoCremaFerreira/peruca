import uuid
from unittest.mock import MagicMock
import pytest

from domain.commands import UserAdd, UserUpdate
from domain.entities import User
from domain.exceptions import ValidationError
from domain.services.user_service import UserService


"""
UserService Unit Tests
"""


def _sample_user(name="Alice", summary="test summary") -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name=name, summary=summary)


class TestUserServiceAdd:
    def test_add_valid_user_returns_uuid(self, user_repo_mock):
        # Arrange
        service = UserService(user_repository=user_repo_mock)
        # Act
        result = service.add(UserAdd(name="Alice", summary="valid summary"))
        # Assert
        assert uuid.UUID(result)
        user_repo_mock.add.assert_called_once()

    def test_add_uses_provided_external_id(self, user_repo_mock):
        # Arrange
        service = UserService(user_repository=user_repo_mock)
        ext_id = str(uuid.uuid4())
        # Act
        service.add(UserAdd(name="Bruno", external_id=ext_id, summary="ok"))
        # Assert
        added_user: User = user_repo_mock.add.call_args[1]["user"]
        assert added_user.external_id == ext_id

    def test_add_generates_external_id_when_missing(self, user_repo_mock):
        # Arrange
        service = UserService(user_repository=user_repo_mock)
        # Act
        user_id = service.add(UserAdd(name="Carla", summary="no ext_id"))
        # Assert
        added_user: User = user_repo_mock.add.call_args[1]["user"]
        assert (
            added_user.external_id == user_id
        )  # external_id defaults to the generated id

    def test_add_raises_when_name_too_short(self, user_repo_mock):
        # Arrange
        service = UserService(user_repository=user_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.add(UserAdd(name="Jo", summary="short"))
        assert "Name" in str(exc.value.errors)

    def test_add_raises_when_name_contains_numbers(self, user_repo_mock):
        # Arrange
        service = UserService(user_repository=user_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.add(UserAdd(name="Ali3e", summary="bad name"))
        assert "letters" in str(exc.value.errors)

    def test_add_raises_when_id_already_exists(
        self, user_repo_mock, sample_user_entity
    ):
        # Arrange
        user_repo_mock.get_by_id.return_value = sample_user_entity
        service = UserService(user_repository=user_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.add(UserAdd(name="Alice", summary="dup"))
        assert "already exist" in str(exc.value.errors)

    def test_add_raises_when_external_id_already_exists(
        self, user_repo_mock, sample_user_entity
    ):
        # Arrange
        user_repo_mock.get_by_id.return_value = None
        user_repo_mock.get_by_external_id.return_value = sample_user_entity
        service = UserService(user_repository=user_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.add(
                UserAdd(
                    name="Diana",
                    external_id=sample_user_entity.external_id,
                    summary="dup ext",
                )
            )
        assert "already exist" in str(exc.value.errors)

    def test_add_raises_when_summary_too_long(self, user_repo_mock):
        # Arrange
        service = UserService(user_repository=user_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.add(UserAdd(name="Elena", summary="x" * 10001))
        assert "summary" in str(exc.value.errors)


class TestUserServiceUpdate:
    def test_update_valid_user_calls_repository(
        self, user_repo_mock, sample_user_entity
    ):
        # Arrange
        user_repo_mock.get_by_id.return_value = sample_user_entity
        user_repo_mock.get_by_external_id.return_value = None
        service = UserService(user_repository=user_repo_mock)
        cmd = UserUpdate(
            id=sample_user_entity.id,
            external_id=sample_user_entity.external_id,
            name="Alice",
            summary="updated summary",
        )
        # Act
        service.update(cmd)
        # Assert
        user_repo_mock.update.assert_called_once()

    def test_update_raises_when_user_not_found(self, user_repo_mock):
        # Arrange
        user_repo_mock.get_by_id.return_value = None
        service = UserService(user_repository=user_repo_mock)
        cmd = UserUpdate(
            id=str(uuid.uuid4()),
            external_id=str(uuid.uuid4()),
            name="Ghost",
            summary="none",
        )
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.update(cmd)
        assert "was not found" in str(exc.value.errors)

    def test_update_raises_when_name_is_invalid(self, user_repo_mock):
        # Arrange
        service = UserService(user_repository=user_repo_mock)
        cmd = UserUpdate(
            id=str(uuid.uuid4()),
            external_id=str(uuid.uuid4()),
            name="1nv@lid",
            summary="bad name",
        )
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.update(cmd)
        assert "letters" in str(exc.value.errors)

    def test_update_raises_when_external_id_taken_by_another_user(self, user_repo_mock):
        # Arrange
        existing_user = _sample_user(name="Alice")
        other_user = _sample_user(name="Bob")
        user_repo_mock.get_by_id.return_value = existing_user
        user_repo_mock.get_by_external_id.return_value = (
            other_user  # different user owns that ext id
        )
        service = UserService(user_repository=user_repo_mock)
        cmd = UserUpdate(
            id=existing_user.id,
            external_id=other_user.external_id,
            name="Alice",
            summary="steal ext id",
        )
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.update(cmd)
        assert "already exist" in str(exc.value.errors)

    def test_update_allows_same_external_id_for_same_user(
        self, user_repo_mock, sample_user_entity
    ):
        # Arrange
        user_repo_mock.get_by_id.return_value = sample_user_entity
        # Returning the same user (same id) – this is allowed
        user_repo_mock.get_by_external_id.return_value = sample_user_entity
        service = UserService(user_repository=user_repo_mock)
        cmd = UserUpdate(
            id=sample_user_entity.id,
            external_id=sample_user_entity.external_id,
            name="Alice",
            summary="same ext id is fine",
        )
        # Act
        service.update(cmd)
        # Assert
        user_repo_mock.update.assert_called_once()


class TestUserServiceDelete:
    def test_delete_existing_user_calls_repository(
        self, user_repo_mock, sample_user_entity
    ):
        # Arrange
        user_repo_mock.get_by_id.return_value = sample_user_entity
        service = UserService(user_repository=user_repo_mock)
        # Act
        service.Delete(user_id=sample_user_entity.id)
        # Assert
        user_repo_mock.delete.assert_called_once_with(user_id=sample_user_entity.id)

    def test_delete_raises_when_user_not_found(self, user_repo_mock):
        # Arrange
        user_repo_mock.get_by_id.return_value = None
        service = UserService(user_repository=user_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.Delete(user_id=str(uuid.uuid4()))
        assert "was not found" in str(exc.value.errors)

    def test_delete_raises_when_id_is_invalid(self, user_repo_mock):
        # Arrange
        service = UserService(user_repository=user_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError):
            service.Delete(user_id="not-a-uuid")
