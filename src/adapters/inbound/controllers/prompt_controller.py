from fastapi import APIRouter, Depends
from pydantic import BaseModel
from application.use_cases.chat_use_case import ChatUseCase
from config.dependencies import get_chat_response_use_case

router = APIRouter()


class PromptRequest(BaseModel):
    prompt: str


@router.post("/chat", tags=["LLM"])
async def generate_response(
    request: PromptRequest,
    use_case: ChatUseCase = Depends(get_chat_response_use_case),
):
    response = await use_case.execute(request.prompt)
    return {"response": response}
