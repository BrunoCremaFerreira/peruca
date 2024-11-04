from domain.services.llm_service import LlmService


class LlmAppService:
    """
    LLM Application Service
    """

    def __init__(self, llm_service: LlmService) -> None:
        self.llm_service = llm_service

    async def chat(self, prompt: str) -> str:
        return await self.llm_service.chat(prompt=prompt)
