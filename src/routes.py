from typing import List
from fastapi import APIRouter, Depends
from application.appservices.llm_app_service import LlmAppService
from application.appservices.shopping_list_app_service import ShoppingListAppService
from application.appservices.user_app_service import UserAppService
from application.appservices.view_models import ChatRequest, ChatResponse, ShoppingListCleanType, ShoppingListItemResponse,UserResponse
from domain.commands import ShoppingListItemAdd, ShoppingListItemUpdate, UserAdd, UserUpdate
from infra.ioc import get_llm_app_service, get_shopping_list_app_service, get_user_app_service

router = APIRouter()

# =====================================
# LLM Routes
# =====================================

@router.post("/llm/chat", tags=["LLM"])
def chat(
    request: ChatRequest,
    llm_app_service: LlmAppService = Depends(get_llm_app_service),
) -> ChatResponse:
    response_str = llm_app_service.chat(request)
    response = ChatResponse(
        response=response_str, chat_id=request.chat_id, external_user_id=request.external_user_id
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

@router.get("/user/external-id/{external_id}", tags=["User"])
def user_get(external_id: str,
             user_app_service: UserAppService = Depends(get_user_app_service)) -> UserResponse:
    return user_app_service.get_by_external_id(user_external_id=external_id)

@router.post("/user", tags=["User"])
def user_add(request: UserAdd,
             user_app_service: UserAppService = Depends(get_user_app_service)) -> dict:
    user_id = user_app_service.add(user_add=request)
    return {"user_id": user_id}

@router.put("/user", tags=["User"])
def user_update(request: UserUpdate,
                user_app_service: UserAppService = Depends(get_user_app_service)) -> None:
    user_app_service.update(user_update=request)


# =====================================
# Shopping List Routes
# =====================================

@router.get("/shopping-list", tags=["Shopping List"])
def shopping_list_get_all(
        shopping_list_app_service: ShoppingListAppService = Depends(get_shopping_list_app_service)
                          ) -> List[ShoppingListItemResponse]:
    return shopping_list_app_service.get_all()

@router.get("/shopping-list/{id}", tags=["Shopping List"])
def shopping_list_get(id: str,
             shopping_list_app_service: ShoppingListAppService = Depends(get_shopping_list_app_service)
             ) -> ShoppingListItemResponse:
    return shopping_list_app_service.get_by_id(item_id=id)

@router.post("/shopping-list", tags=["Shopping List"])
def shopping_list_add(request: ShoppingListItemAdd,
             shopping_list_app_service: ShoppingListAppService = Depends(get_shopping_list_app_service)
             ) -> dict:
    item_id = shopping_list_app_service.add(item=request)
    return {"shopping_list_id": item_id}

@router.put("/shopping-list", tags=["Shopping List"])
def shopping_list_update_quantity(request: ShoppingListItemUpdate,
                shopping_list_app_service: ShoppingListAppService = Depends(get_shopping_list_app_service)
                ) -> None:
    shopping_list_app_service.update_quantity(item=request)

@router.delete("/shopping-list/{id}", tags=["Shopping List"])
def shopping_list_delete(id: str,
                shopping_list_app_service: ShoppingListAppService = Depends(get_shopping_list_app_service)
                ) -> None:
    shopping_list_app_service.delete(item_id=id)

@router.post("/shopping-list/clear/{clean_type}", tags=["Shopping List"])
def shopping_list_clear(clean_type: ShoppingListCleanType,
             shopping_list_app_service: ShoppingListAppService = Depends(get_shopping_list_app_service)
             ) -> None:
    shopping_list_app_service.clear(clean_type=clean_type)

@router.put("/shopping-list/{id}/check", tags=["Shopping List"])
def shopping_list_ckeck(id: str,
             shopping_list_app_service: ShoppingListAppService = Depends(get_shopping_list_app_service)
             ) -> None:
    shopping_list_app_service.check(item_id=id)

@router.put("/shopping-list/{id}/uncheck", tags=["Shopping List"])
def shopping_list_ckeck(id: str,
             shopping_list_app_service: ShoppingListAppService = Depends(get_shopping_list_app_service)
             ) -> None:
    shopping_list_app_service.uncheck(item_id=id)