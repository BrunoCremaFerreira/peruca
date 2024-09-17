from abc import ABC, abstractmethod

class LLMInboundPort(ABC):
    @abstractmethod
    async def chat(self, prompt: str) -> str:
        pass
