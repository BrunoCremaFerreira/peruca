from application.ports.outbound.llm_outbound_port import LLMOutboundPort

class LLaMAProvider(LLMOutboundPort):
    def __init__(self):
        # Config for LLaMA
        pass

    async def generate_response(self, prompt: str) -> str:
        # Implementation for LLaMA local
        pass
