from domain.ports.outbound.llm_outbound_port import LLMOutboundPort


class LLaMAProvider(LLMOutboundPort):
    def __init__(self):
        """Config for LLaMA"""
        raise NotImplementedError("Under Construction")

    async def generate_response(self, prompt: str) -> str:
        """Implementation for LLaMA"""
        raise NotImplementedError("Under Construction")
