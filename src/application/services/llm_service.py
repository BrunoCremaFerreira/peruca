from application.ports.inbound.llm_inbound_port import LLMInboundPort
from application.ports.outbound.llm_outbound_port import LLMOutboundPort

class LLMService(LLMInboundPort):
    def __init__(self, provider: LLMOutboundPort):
        self.provider = provider

    async def generate_response(self, prompt: str) -> str:
        return await self.provider.generate_response(prompt)
