from domain.interfaces.repository import ContextRepository, LlmRepository


class LlmService:
    """
    LLM Service
    """

    def __init__(
        self, llm_repository: LlmRepository, context_repository: ContextRepository
    ):
        self.llm_repository = llm_repository
        self.context_repository = context_repository

    async def chat(self, prompt: str) -> str:
        return await self.llm_repository.generate_response(prompt)
