from domain.services.llm_service import LLMService

class GenerateResponseUseCase:
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service

    async def execute(self, prompt: str) -> str:
        return await self.llm_service.generate_response(prompt)
