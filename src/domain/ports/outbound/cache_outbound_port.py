from abc import ABC, abstractmethod


class CacheOutboundPort(ABC):
    """
    Interface for cache operations.
    """

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
    async def delete_key(self, key: str):
        """
        Deletes a key from the cache.
        """
        pass

    @abstractmethod
    async def update_key(self, key: str, value: str):
        """
        Deletes a key from the cache.
        """
        pass
