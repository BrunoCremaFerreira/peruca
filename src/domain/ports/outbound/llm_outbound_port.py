from abc import ABC, abstractmethod

class LLMOutboundPort(ABC):
    """
    Interface for LLM Provider
    """


    @abstractmethod
    async def generate_response(self, prompt: str) -> str:
        """
        Generates a response based on the given prompt.
        """
        pass