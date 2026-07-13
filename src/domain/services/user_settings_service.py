import uuid
from datetime import datetime, timezone
from typing import Optional

from domain.entities import UserSettings
from domain.interfaces.user_settings_repository import UserSettingsRepository
from domain.validations.user_settings_validation import UserSettingsValidator


class UserSettingsService:
    """
    Per-user settings (1:1). ``default_timezone`` is injected by the composition
    root — the domain never hardcodes it.
    """

    def __init__(
        self,
        user_settings_repository: UserSettingsRepository,
        default_timezone: str,
    ):
        # The default is served RAW to every user without a row, so a misconfigured
        # zone would raise at request time, on every turn. It is a configuration
        # error: fail here, once, at composition.
        UserSettingsValidator().validate_timezone(default_timezone).validate()

        self.user_settings_repository = user_settings_repository
        self.default_timezone = default_timezone

    def get_timezone(self, user_id: str) -> str:
        """
        The user's IANA timezone, falling back to the injected default. A read
        never writes: a user with no row is not given a ghost record.
        """
        settings = self._get(user_id)
        if settings and settings.timezone:
            return settings.timezone
        return self.default_timezone

    def set_timezone(self, user_id: str, user_timezone: str) -> None:
        """
        Store an ALREADY-RESOLVED IANA identifier for a user: creates the row
        (with a UUID id) on the first call, updates it in place afterwards.
        """
        UserSettingsValidator().validate_user_id(user_id).validate_timezone(
            user_timezone
        ).validate()

        settings = self._get(user_id)
        if settings:
            settings.timezone = user_timezone
            settings.when_updated = datetime.now(timezone.utc)
            self.user_settings_repository.update(settings)
            return

        settings = UserSettings(
            id=str(uuid.uuid4()),
            user_id=user_id,
            timezone=user_timezone,
            when_created=datetime.now(timezone.utc),
        )
        self.user_settings_repository.add(settings)

    def _get(self, user_id: str) -> Optional[UserSettings]:
        return self.user_settings_repository.get_by_user_id(user_id)
