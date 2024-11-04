from fastapi import APIRouter, Depends
from pydantic import BaseModel
from application.appservices.llm_app_service import LlmAppService
from infra.ioc import get_llm_app_service

# =====================================
# LLM Routes
# =====================================

llm_router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    user_name: str
    chat_id: str


class ChatResponse(BaseModel):
    response: str
    for_user: str
    chat_id: str


@llm_router.post("/chat", tags=["LLM"])
async def chat(
    request: ChatRequest,
    llm_app_service: LlmAppService = Depends(get_llm_app_service),
) -> ChatResponse:
    response_str = await llm_app_service.chat(request.message)
    response = ChatResponse(
        response=response_str, chat_id=request.chat_id, for_user=request.user_name
    )
    return response
