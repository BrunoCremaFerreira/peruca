from fastapi import APIRouter, Depends
from pydantic import BaseModel
from application.use_cases.generate_response_use_case import GenerateResponseUseCase
from config.dependencies import get_generate_response_use_case

router = APIRouter()

class PromptRequest(BaseModel):
    prompt: str

@router.post("/generate", tags=["LLM"])
async def generate_response(request: PromptRequest, use_case: GenerateResponseUseCase = Depends(get_generate_response_use_case)):
    response = await use_case.execute(request.prompt)
    return {"response": response}
