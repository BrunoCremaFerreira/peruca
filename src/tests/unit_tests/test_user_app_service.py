import os
from unittest.mock import patch
import uuid
import pytest

from application.appservices.user_app_service import UserAppService
from domain.commands import UserAdd, UserUpdate
from domain.interfaces.repository import UserRepository
from domain.exceptions import ValidationError
from infra.ioc import get_user_app_service, get_user_repository


"""
UserAppService Unit Test
"""

DB_PATH = "/home/brn/tests/data/tests.db"

@pytest.fixture
def setup_app_service():
    with patch.dict(os.environ, {
        "PERUCA_DB_CONNECTION_STRING": f"sqlite://{DB_PATH}",
    }):
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        repo = get_user_repository()
        app_service = get_user_app_service()
        yield app_service, repo
        repo.close()
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)

def test_add_user_success(setup_app_service):
    # Arrange
    app_service, _ = setup_app_service
    user_add = UserAdd(name="Maria", external_id="123", summary="Test user")
    # Act
    user_id = app_service.add(user_add)
    # Assert
    assert uuid.UUID(user_id)  # check if UUID is valid

def test_add_user_with_invalid_name(setup_app_service):
    # Arrange
    app_service, _ = setup_app_service
    # Act
    with pytest.raises(ValidationError) as exc:
        app_service.add(UserAdd(name="Jo", summary="short name"))
    # Assert
    assert "Name" in str(exc.value.errors)

def test_add_user_with_numbers_in_name(setup_app_service):
    # Arrange
    app_service, _ = setup_app_service
    # Act
    with pytest.raises(ValidationError) as exc:
        app_service.add(UserAdd(name="Maria123", summary="invalid name"))
    # Assert
    assert "letters" in str(exc.value.errors)

def test_add_user_with_long_summary(setup_app_service):
    # Arrange
    app_service, _ = setup_app_service
    long_summary = "a" * 10001
    # Act
    with pytest.raises(ValidationError) as exc:
        app_service.add(UserAdd(name="ValidName", summary=long_summary))
    # Assert
    assert "summary" in str(exc.value.errors)

def test_add_user_with_duplicate_external_id(setup_app_service):
    # Arrange
    external_id="123"
    app_service, repo = setup_app_service
    user_add = UserAdd(name="Joana", summary="test user", external_id=external_id)
    app_service.add(user_add)
    
    # Act
    with pytest.raises(ValidationError) as exc:
        app_service.add(UserAdd(name="Joana", summary="Duplicated", external_id=external_id)) # save duplicated
    # Assert
    assert "already exist" in str(exc.value.errors)

def test_get_by_id_success(setup_app_service):
    # Arrange
    app_service, _ = setup_app_service
    user_add = UserAdd(name="Carlos", summary="from test")
    # Act
    user_id = app_service.add(user_add)
    user_resp = app_service.get_by_id(user_id)
    # Assert
    assert user_resp.name == "Carlos"

def test_get_by_external_id_success(setup_app_service):
    # Arrange
    app_service, _ = setup_app_service
    user_add = UserAdd(name="Lucas", summary="external test")
    user_id = app_service.add(user_add)
    # Act
    user_resp = app_service.get_by_external_id(user_id)
    # Assert
    assert user_resp.name == "Lucas"

def test_get_all_users(setup_app_service):
    # Arrange
    app_service, _ = setup_app_service
    app_service.add(UserAdd(name="Aline", summary="a"))
    app_service.add(UserAdd(name="Bruna", summary="b"))
    # Act
    users = app_service.get_all()
    # Assert
    assert len(users) >= 2
    assert any(user.name == "Aline" for user in users)

def test_update_user_success(setup_app_service):
    # Arrange
    app_service, repo = setup_app_service
    user_id = app_service.add(UserAdd(name="Daniela", summary="old summary"))
    user = repo.get_by_id(user_id)
    user_update = UserUpdate(id=user.id, name="Daniela", external_id=user.external_id, summary="new summary")
    # Act
    app_service.update(user_update)
    # Assert
    updated = repo.get_by_id(user_id)
    assert updated.summary == "new summary"

def test_update_user_with_invalid_name(setup_app_service):
    # Arrange
    app_service, repo = setup_app_service
    user_id = app_service.add(UserAdd(name="Beatriz", summary="valid"))
    user = repo.get_by_id(user_id)
    user_update = UserUpdate(id=user.id, name="1nv@lid", external_id=user.external_id, summary="update fail")
    # Act
    with pytest.raises(ValidationError) as exc:
        app_service.update(user_update)
    # Assert
    assert "letters" in str(exc.value.errors)

def test_update_nonexistent_user(setup_app_service):
    # Arrange
    app_service, _ = setup_app_service
    fake_id = str(uuid.uuid4())
    user_update = UserUpdate(id=fake_id, name="Ghost", external_id=fake_id, summary="none")
    # Act
    with pytest.raises(ValidationError) as exc:
        app_service.update(user_update)
    # Assert
    assert "was not found" in str(exc.value.errors)
