from typing import List
from fastapi import APIRouter, Depends
from application.appservices.llm_app_service import LlmAppService
from application.appservices.user_app_service import UserAppService
from application.appservices.view_models import ChatRequest, ChatResponse, UserAdd, UserResponse, UserUpdate
from infra.ioc import get_llm_app_service, get_user_app_service

router = APIRouter()

# =====================================
# LLM Routes
# =====================================

@router.post("/llm/chat", tags=["LLM"])
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

# =====================================
# User Routes
# =====================================

@router.get("/user", tags=["User"])
def user_get_all(user_app_service: UserAppService = Depends(get_user_app_service)) -> List[UserResponse]:
    return user_app_service.get_all()

@router.get("/user/{id}", tags=["User"])
def user_get(id: str,
             user_app_service: UserAppService = Depends(get_user_app_service)) -> UserResponse:
    return user_app_service.get_by_id(user_id=id)

@router.post("/user", tags=["User"])
def user_add(request: UserAdd,
             user_app_service: UserAppService = Depends(get_user_app_service)) -> None:
    user_app_service.add(user_add=request)

@router.put("/user", tags=["User"])
def user_update(request: UserUpdate,
                user_app_service: UserAppService = Depends(get_user_app_service)) -> None:
    user_app_service.update(user_update=request)
