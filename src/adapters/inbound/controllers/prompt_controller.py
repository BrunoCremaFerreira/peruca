from fastapi import APIRouter, Depends
from pydantic import BaseModel
from application.use_cases.chat_use_case import ChatUseCase
from config.dependencies import get_chat_response_use_case

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    user_name: str
    chat_id: str


class ChatResponse(BaseModel):
    response: str
    for_user: str
    chat_id: str


@router.post("/chat", tags=["LLM"])
async def chat(
    request: ChatRequest,
    use_case: ChatUseCase = Depends(get_chat_response_use_case),
) -> ChatResponse:
    response_str = await use_case.execute(request.message)
    response = ChatResponse(
        response=response_str, chat_id=request.chat_id, for_user=request.user_name
    )
    return response
