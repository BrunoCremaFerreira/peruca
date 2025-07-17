from abc import ABC, abstractmethod
from typing import List, Optional

from domain.entities import User


class UserRepository(ABC):
    """
    User Repository
    """

    @abstractmethod
    def connect() -> None:
        """
        Connect to database
        """
        pass

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
    def get_by_external_id(self, user_external_id: str) -> Optional[User]:
        """
        Get User By external_Id
        """
        pass

    @abstractmethod
    def list(self) -> List[User]:
        """
        List User
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