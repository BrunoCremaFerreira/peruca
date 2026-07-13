"""
UserSettingsService tests (TDD) — §10.4 of the user-timezone plan.

Contract:

    UserSettingsService(user_settings_repository, default_timezone: str)
        .get_timezone(user_id) -> str      # falls back to the INJECTED default
        .set_timezone(user_id, tz) -> None # creates (UUID id) or updates; never duplicates

Key invariants pinned here:
  * no "ghost record": a user with no row simply gets the default back — nothing
    is written on a read;
  * the default is injected (from ``infra.settings``), never hardcoded in the domain;
  * only an ALREADY-RESOLVED IANA identifier is accepted — a city name ("Lisboa")
    is rejected, because resolving city -> IANA is the timezone_resolver's job;
  * an invalid timezone never touches the repository.
"""

import uuid
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from domain.entities import UserSettings
from domain.exceptions import ValidationError
from domain.services.user_settings_service import UserSettingsService


DEFAULT_TZ = "America/Sao_Paulo"


def _make_repo(settings=None) -> MagicMock:
    repo = MagicMock()
    repo.get_by_user_id.return_value = settings
    return repo


def _make_service(repo, default_timezone: str = DEFAULT_TZ) -> UserSettingsService:
    return UserSettingsService(
        user_settings_repository=repo, default_timezone=default_timezone
    )


def _sample_settings(user_id: str, tz: str = "Europe/Lisbon") -> UserSettings:
    return UserSettings(id=str(uuid.uuid4()), user_id=user_id, timezone=tz)


def _entity_of(mock_call) -> UserSettings:
    """The entity handed to repo.add/update, positionally or by keyword."""
    args, kwargs = mock_call
    return args[0] if args else next(iter(kwargs.values()))


class TestUserSettingsServiceGetTimezone:
    def test_get__no_settings__returns_default_timezone(self):
        # Arrange
        repo = _make_repo(settings=None)
        service = _make_service(repo)
        # Act
        result = service.get_timezone(str(uuid.uuid4()))
        # Assert — the injected default, and NO ghost record written.
        assert result == DEFAULT_TZ
        repo.add.assert_not_called()
        repo.update.assert_not_called()

    def test_get__no_settings__returns_the_injected_default_not_a_hardcoded_one(self):
        # Arrange
        repo = _make_repo(settings=None)
        service = _make_service(repo, default_timezone="Europe/Lisbon")
        # Act / Assert
        assert service.get_timezone(str(uuid.uuid4())) == "Europe/Lisbon"

    def test_get__existing_settings__returns_the_stored_timezone(self):
        # Arrange
        user_id = str(uuid.uuid4())
        repo = _make_repo(settings=_sample_settings(user_id, "Europe/Lisbon"))
        service = _make_service(repo)
        # Act
        result = service.get_timezone(user_id)
        # Assert
        assert result == "Europe/Lisbon"
        repo.get_by_user_id.assert_called_once_with(user_id)


class TestUserSettingsServiceSetTimezone:
    def test_set__new_user__creates_with_uuid(self):
        # Arrange
        user_id = str(uuid.uuid4())
        repo = _make_repo(settings=None)
        service = _make_service(repo)
        # Act
        service.set_timezone(user_id, "Europe/Lisbon")
        # Assert
        repo.add.assert_called_once()
        repo.update.assert_not_called()
        entity = _entity_of(repo.add.call_args)
        assert uuid.UUID(entity.id)  # project rule: persisted ids are UUIDs
        assert entity.user_id == user_id
        assert entity.timezone == "Europe/Lisbon"

    def test_set__new_user__stamps_when_created_in_utc(self):
        # Arrange
        repo = _make_repo(settings=None)
        service = _make_service(repo)
        # Act
        service.set_timezone(str(uuid.uuid4()), "Europe/Lisbon")
        # Assert
        entity = _entity_of(repo.add.call_args)
        assert entity.when_created.tzinfo is not None
        assert entity.when_created.utcoffset() == timedelta(0)

    def test_set__existing__updates_not_duplicates(self):
        # Arrange
        user_id = str(uuid.uuid4())
        existing = _sample_settings(user_id, "America/Sao_Paulo")
        repo = _make_repo(settings=existing)
        service = _make_service(repo)
        # Act
        service.set_timezone(user_id, "Europe/Lisbon")
        # Assert — 1:1 per user: the row is updated in place, never re-added.
        repo.update.assert_called_once()
        repo.add.assert_not_called()
        entity = _entity_of(repo.update.call_args)
        assert entity.id == existing.id
        assert entity.user_id == user_id
        assert entity.timezone == "Europe/Lisbon"

    def test_set__invalid_tz__raises_validation_error(self):
        # Arrange
        repo = _make_repo(settings=None)
        service = _make_service(repo)
        # Act / Assert
        with pytest.raises(ValidationError):
            service.set_timezone(str(uuid.uuid4()), "America/Sao_Paolo")
        repo.add.assert_not_called()
        repo.update.assert_not_called()

    def test_set__city_name_rejected(self):
        # Arrange — the service only accepts an ALREADY-RESOLVED IANA id;
        # "Lisboa" is the timezone_resolver's input, not the service's.
        repo = _make_repo(settings=None)
        service = _make_service(repo)
        # Act / Assert
        with pytest.raises(ValidationError):
            service.set_timezone(str(uuid.uuid4()), "Lisboa")
        repo.add.assert_not_called()
        repo.update.assert_not_called()

    def test_set__empty_tz__raises_validation_error(self):
        # Arrange
        repo = _make_repo(settings=None)
        service = _make_service(repo)
        # Act / Assert
        with pytest.raises(ValidationError):
            service.set_timezone(str(uuid.uuid4()), "")
        repo.add.assert_not_called()
        repo.update.assert_not_called()

    def test_set__empty_user_id__raises_validation_error(self):
        # Arrange
        repo = _make_repo(settings=None)
        service = _make_service(repo)
        # Act / Assert
        with pytest.raises(ValidationError):
            service.set_timezone("", "Europe/Lisbon")
        repo.add.assert_not_called()
        repo.update.assert_not_called()

    def test_set_then_get__round_trip_through_the_repository(self):
        # Arrange
        user_id = str(uuid.uuid4())
        repo = _make_repo(settings=None)
        service = _make_service(repo)
        # Act
        service.set_timezone(user_id, "Europe/Lisbon")
        repo.get_by_user_id.return_value = _entity_of(repo.add.call_args)
        # Assert
        assert service.get_timezone(user_id) == "Europe/Lisbon"
