from abc import ABC, abstractmethod
from typing import Optional

from domain.entities import UserSettings


class UserSettingsRepository(ABC):
    """
    Per-user settings persistence (1:1 with a user). There is no ``delete``: the
    row is created on the first ``set`` and updated in place afterwards.
    """

    @abstractmethod
    def get_by_user_id(self, user_id: str) -> Optional[UserSettings]:
        """Get the settings of a user, or None when the user has none yet."""
        pass

    @abstractmethod
    def add(self, user_settings: UserSettings) -> None:
        """Add the settings row of a user."""
        pass

    @abstractmethod
    def update(self, user_settings: UserSettings) -> None:
        """Update the settings row of a user."""
        pass
