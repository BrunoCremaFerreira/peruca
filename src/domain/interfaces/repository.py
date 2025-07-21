from abc import ABC, abstractmethod
from typing import List, Optional

from domain.entities import ShoppingListItem, User


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

    def delete(self, item_id: str):
        """
        Delete Shopping List Item
        """
        pass


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