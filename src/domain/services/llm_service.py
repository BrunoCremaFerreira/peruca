from domain.ports.inbound.llm_inbound_port import LLMInboundPort
from domain.ports.outbound.cache_outbound_port import CacheOutboundPort
from domain.ports.outbound.llm_outbound_port import LLMOutboundPort


class LLMService(LLMInboundPort):
    """
    LLM Service
    """

    def __init__(self, provider: LLMOutboundPort, cache_database: CacheOutboundPort):
        self.provider = provider
        self.cache_database = cache_database

    async def chat(self, prompt: str) -> str:
        return await self.provider.generate_response(prompt)
