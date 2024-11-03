from domain.interfaces.repository import LlmRepository


class Llama3LlmRepository(LlmRepository):
    def __init__(self):
        """Config for LLaMA"""
        raise NotImplementedError("Under Construction")

    async def generate_response(self, prompt: str) -> str:
        """Implementation for LLaMA"""
        raise NotImplementedError("Under Construction")
