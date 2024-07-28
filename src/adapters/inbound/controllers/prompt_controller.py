from fastapi import APIRouter, Depends
from pydantic import BaseModel
from application.services.llm_service import LLMService
from config.dependencies import get_llm_service

router = APIRouter()

class PromptRequest(BaseModel):
    prompt: str

@router.post("/generate", tags=["LLM"])
async def generate_response(request: PromptRequest, llm_service: LLMService = Depends(get_llm_service)):
    response = await llm_service.generate_response(request.prompt)
    return {"response": response}
