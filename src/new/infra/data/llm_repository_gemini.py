from domain.interfaces.repository import LlmRepository


class GeminiLlmRepository(LlmRepository):
    def __init__(self, api_key: str):
        """Configuration for Google Gemini"""
        raise NotImplementedError("Under Construction")

    async def generate_response(self, prompt: str) -> str:
        """Implementation for Google Gemini"""
        raise NotImplementedError("Under Construction")
