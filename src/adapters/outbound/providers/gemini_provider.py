from domain.ports.outbound.llm_outbound_port import LLMOutboundPort

class GeminiProvider(LLMOutboundPort):
    def __init__(self, api_key: str):
        # Configuration for Google Gemini
        pass

    async def generate_response(self, prompt: str) -> str:
        # Implementation for Google Gemini
        pass
