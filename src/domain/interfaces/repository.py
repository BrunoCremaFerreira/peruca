from abc import ABC, abstractmethod
from typing import List, Optional

from domain.commands import LightTurnOn
from domain.entities import ShoppingListItem, SmartHomeLight, User

#=====================================
# Data Repository
#=====================================
class UserRepository(ABC):
    """
    User Repository
    """

    @abstractmethod
    def add(self, user: User):
        """
        Add User
        """
        pass

    @abstractmethod
    def get_by_id(self, user_id: str) -> Optional[User]:
        """
        Get User By Id
        """
        pass

    @abstractmethod
    def get_by_external_id(self, external_id: str) -> Optional[User]:
        """
        Get User By external_Id
        """
        pass

    @abstractmethod
    def get_all(self) -> List[User]:
        """
        Get all Users
        """
        pass

    @abstractmethod
    def update(self, user: User):
        """
        Update User
        """
        pass

    @abstractmethod
    def delete(self, user_id: str):
        """
        Delete User
        """
        pass


class ShoppingListRepository(ABC):
    """
    User Repository
    """

    @abstractmethod
    def add(self, item: ShoppingListItem):
        """
        Add Shopping List
        """
        pass

    @abstractmethod
    def get_by_id(self, item_id: str) -> Optional[ShoppingListItem]:
        """
        Get Shopping List Item By Id
        """
        pass

    @abstractmethod
    def get_by_name(self, item_name: str) -> Optional[ShoppingListItem]:
        """
        Get Shopping List Item By name
        """
        pass

    @abstractmethod
    def get_all(self) -> List[ShoppingListItem]:
        """
        List All Shopping List
        """
        pass

    @abstractmethod
    def update(self, item: ShoppingListItem):
        """
        Update Shopping List Item
        """
        pass

    @abstractmethod
    def delete(self, item_id: str):
        """
        Delete Shopping List Item
        """
        pass

    @abstractmethod
    def clear(self):
        """
        Delete all Shopping List Item
        """
        pass

#=====================================
# Temp Data Repository
#=====================================
class ContextRepository(ABC):
    """
    Interface for LLM Context operations.
    """

    @abstractmethod
    def connect() -> None:
        """
        Connect to database
        """
        pass

    @abstractmethod
    async def set_key(self, key: str, value: str):
        """
        Stores a value associated with a key.
        """
        pass

    @abstractmethod
    async def get_key(self, key: str) -> str:
        """
        Retrieves the value associated with a key.
        """
        pass

    @abstractmethod
    async def delete_key(self, key: str) -> bool:
        """
        Deletes a key from the cache.
        """
        pass

#=====================================
# Smart Home Integration Repository
#=====================================
class SmartHomeLightRepository(ABC):
    """
    Interface for Smart Home Lights integration
    """

    @abstractmethod
    async def get_state(self, entity_id: str)-> SmartHomeLight:
        """
        Get entity current state.
        """
        pass

    @abstractmethod
    async def turn_on(self, turn_on_command: LightTurnOn)-> dict:
        """
        Turn on light
        """
        pass