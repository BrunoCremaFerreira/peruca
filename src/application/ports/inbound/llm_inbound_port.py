from abc import ABC, abstractmethod

class LLMInboundPort(ABC):
    @abstractmethod
    async def generate_response(self, prompt: str) -> str:
        pass
