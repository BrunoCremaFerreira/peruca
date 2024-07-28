from openai import AsyncOpenAI

aclient = AsyncOpenAI(api_key=self.api_key)
from domain.ports.outbound.llm_outbound_port import LLMOutboundPort

class OpenAIProvider(LLMOutboundPort):
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def generate_response(self, prompt: str) -> str:
        response = await aclient.chat.completions.create(model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150)
        return response['choices'][0]['message']['content'].strip()
