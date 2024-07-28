from abc import ABC, abstractmethod

class LLMOutboundPort(ABC):
    @abstractmethod
    async def generate_response(self, prompt: str) -> str:
        pass
