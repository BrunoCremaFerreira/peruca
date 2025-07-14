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
    user_id: str
    chat_id: str


class ChatResponse(BaseModel):
    response: str
    user_id: str
    chat_id: str


@llm_router.post("/chat", tags=["LLM"])
def chat(
    request: ChatRequest,
    llm_app_service: LlmAppService = Depends(get_llm_app_service),
) -> ChatResponse:
    response_str = llm_app_service.chat(
        message=request.message, 
        user_id=request.user_id,
        chat_id=request.chat_id
    )
    response = ChatResponse(
        response=response_str, chat_id=request.chat_id, user_id=request.chat_id
    )
    return response
