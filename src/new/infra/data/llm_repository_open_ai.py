from domain.interfaces.repository import LlmRepository
from openai import AsyncOpenAI


class OpenAiLlmRepository(LlmRepository):
    """Implementation of OpenAi LLM Repository"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.aclient = AsyncOpenAI(api_key=self.api_key)

    async def generate_response(self, prompt: str) -> str:
        response = await self.aclient.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
        )
        result = response.choices[0].message.content
        return result.strip() if result else ""
