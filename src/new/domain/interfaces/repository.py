from abc import ABC, abstractmethod


class LlmRepository(ABC):
    """
    LLM Repository Interface
    """

    @abstractmethod
    async def generate_response(self, prompt: str) -> str:
        """
        Generates a response based on the given prompt.
        """
        pass


class ContextRepository(ABC):
    """
    Interface for LLM Context operations.
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
    async def delete_key(self, key: str) -> bool:
        """
        Deletes a key from the cache.
        """
        pass
