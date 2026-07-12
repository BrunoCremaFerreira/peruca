from typing import List
from fastapi import APIRouter, BackgroundTasks, Depends
from application.appservices.context_compaction_app_service import (
    ContextCompactionAppService,
)
from application.appservices.llm_app_service import LlmAppService
from application.appservices.memory_app_service import MemoryAppService
from application.appservices.shopping_list_app_service import ShoppingListAppService
from application.appservices.smart_home_app_service import SmartHomeAppService
from application.appservices.pet_app_service import PetAppService
from application.appservices.user_app_service import UserAppService
from application.appservices.user_memory_app_service import UserMemoryAppService
from application.appservices.vehicle_app_service import VehicleAppService
from application.appservices.view_models import (
    ChatRequest,
    ChatResponse,
    MaintenanceRecordResponse,
    PetHealthEventResponse,
    PetResponse,
    ShoppingListCleanType,
    ShoppingListItemResponse,
    UserMemoryResponse,
    UserResponse,
    VehicleResponse,
)
from domain.commands import (
    PetAdd,
    PetUpdate,
    ShoppingListItemAdd,
    ShoppingListItemUpdate,
    UserAdd,
    UserUpdate,
    VehicleAdd,
    VehicleUpdate,
)
from domain.entities import SmartHomeEntityAlias
from infra.ioc import (
    get_context_compaction_app_service,
    get_llm_app_service,
    get_memory_app_service,
    get_pet_app_service,
    get_shopping_list_app_service,
    get_smart_home_app_service,
    get_user_app_service,
    get_user_memory_app_service,
    get_vehicle_app_service,
)

# Public router: routes that must stay reachable without the API key (health
# checks for containers / Home Assistant). Everything else lives on `router`,
# which app.py mounts behind the require_api_key dependency.
public_router = APIRouter()

router = APIRouter()


@public_router.get("/health")
async def health():
    return {"status": "ok"}


# =====================================
# LLM Routes
# =====================================


@router.post("/llm/chat", tags=["LLM"])
def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    llm_app_service: LlmAppService = Depends(get_llm_app_service),
    memory_app_service: MemoryAppService = Depends(get_memory_app_service),
    context_compaction_app_service: ContextCompactionAppService = Depends(
        get_context_compaction_app_service
    ),
) -> ChatResponse:
    result = llm_app_service.chat(request)
    output = result["output"] if isinstance(result, dict) else result
    # Durable-memory extraction runs FIRST: it reads the turn that was just
    # persisted, while compaction may rewrite the head of the history.
    background_tasks.add_task(
        memory_app_service.learn_from_message,
        request.external_user_id,
        request.message,
        output,
    )
    background_tasks.add_task(
        context_compaction_app_service.compact_if_needed,
        request.external_user_id,
    )
    response = ChatResponse(
        response=output,
        chat_id=request.chat_id,
        external_user_id=request.external_user_id,
    )
    return response


# =====================================
# User Routes
# =====================================


@router.get("/user", tags=["User"])
def user_get_all(
    user_app_service: UserAppService = Depends(get_user_app_service),
) -> List[UserResponse]:
    return user_app_service.get_all()


@router.get("/user/{id}", tags=["User"])
def user_get(
    id: str, user_app_service: UserAppService = Depends(get_user_app_service)
) -> UserResponse:
    return user_app_service.get_by_id(user_id=id)


@router.get("/user/external-id/{external_id}", tags=["User"])
def user_get_by_external_id(
    external_id: str, user_app_service: UserAppService = Depends(get_user_app_service)
) -> UserResponse:
    return user_app_service.get_by_external_id(user_external_id=external_id)


@router.post("/user", tags=["User"])
def user_add(
    request: UserAdd, user_app_service: UserAppService = Depends(get_user_app_service)
) -> dict:
    user_id = user_app_service.add(user_add=request)
    return {"user_id": user_id}


@router.put("/user", tags=["User"])
def user_update(
    request: UserUpdate,
    user_app_service: UserAppService = Depends(get_user_app_service),
) -> None:
    user_app_service.update(user_update=request)


# =====================================
# User Memory Routes
# =====================================


@router.get("/user/{id}/memory", tags=["User Memory"])
def user_memory_get_all(
    id: str,
    svc: UserMemoryAppService = Depends(get_user_memory_app_service),
) -> List[UserMemoryResponse]:
    return svc.get_all_by_user(user_id=id)


@router.delete("/user/{id}/memory/{memory_id}", tags=["User Memory"])
def user_memory_delete(
    id: str,
    memory_id: str,
    svc: UserMemoryAppService = Depends(get_user_memory_app_service),
) -> None:
    svc.delete(memory_id=memory_id)


@router.delete("/user/{id}/memory", tags=["User Memory"])
def user_memory_clear(
    id: str,
    svc: UserMemoryAppService = Depends(get_user_memory_app_service),
) -> None:
    svc.clear_by_user(user_id=id)


@router.delete("/user/{id}/chat-history", tags=["User Chat History"])
def user_chat_history_reset(
    id: str,
    llm_app_service: LlmAppService = Depends(get_llm_app_service),
) -> None:
    llm_app_service.reset_context(user_id=id)


# =====================================
# Shopping List Routes
# =====================================


@router.get("/shopping-list", tags=["Shopping List"])
def shopping_list_get_all(
    shopping_list_app_service: ShoppingListAppService = Depends(
        get_shopping_list_app_service
    ),
) -> List[ShoppingListItemResponse]:
    return shopping_list_app_service.get_all()


@router.get("/shopping-list/{id}", tags=["Shopping List"])
def shopping_list_get(
    id: str,
    shopping_list_app_service: ShoppingListAppService = Depends(
        get_shopping_list_app_service
    ),
) -> ShoppingListItemResponse:
    return shopping_list_app_service.get_by_id(item_id=id)


@router.post("/shopping-list", tags=["Shopping List"])
def shopping_list_add(
    request: ShoppingListItemAdd,
    shopping_list_app_service: ShoppingListAppService = Depends(
        get_shopping_list_app_service
    ),
) -> dict:
    item_id = shopping_list_app_service.add(item=request)
    return {"shopping_list_id": item_id}


@router.put("/shopping-list", tags=["Shopping List"])
def shopping_list_update_quantity(
    request: ShoppingListItemUpdate,
    shopping_list_app_service: ShoppingListAppService = Depends(
        get_shopping_list_app_service
    ),
) -> None:
    shopping_list_app_service.update_quantity(item=request)


@router.delete("/shopping-list/{id}", tags=["Shopping List"])
def shopping_list_delete(
    id: str,
    shopping_list_app_service: ShoppingListAppService = Depends(
        get_shopping_list_app_service
    ),
) -> None:
    shopping_list_app_service.delete(item_id=id)


@router.post("/shopping-list/clear/{clean_type}", tags=["Shopping List"])
def shopping_list_clear(
    clean_type: ShoppingListCleanType,
    shopping_list_app_service: ShoppingListAppService = Depends(
        get_shopping_list_app_service
    ),
) -> None:
    shopping_list_app_service.clear(clean_type=clean_type)


@router.put("/shopping-list/{id}/check", tags=["Shopping List"])
def shopping_list_check(
    id: str,
    shopping_list_app_service: ShoppingListAppService = Depends(
        get_shopping_list_app_service
    ),
) -> None:
    shopping_list_app_service.check(item_id=id)


@router.put("/shopping-list/{id}/uncheck", tags=["Shopping List"])
def shopping_list_uncheck(
    id: str,
    shopping_list_app_service: ShoppingListAppService = Depends(
        get_shopping_list_app_service
    ),
) -> None:
    shopping_list_app_service.uncheck(item_id=id)


# =====================================
# Smart Home Routes
# =====================================


@router.get("/smart-home/backend/entity/aliases", tags=["Smart Home"])
def smart_home_back_end_get_all_entity_aliases(
    smart_home_app_service: SmartHomeAppService = Depends(get_smart_home_app_service),
) -> List[SmartHomeEntityAlias]:
    return smart_home_app_service.get_all_entity_aliases()


@router.put("/smart-home/backend/update-aliases", tags=["Smart Home"])
async def smart_home_back_end_update_aliases(
    smart_home_app_service: SmartHomeAppService = Depends(get_smart_home_app_service),
) -> None:
    await smart_home_app_service.update_entity_aliases()


# =====================================
# Vehicle Routes (write is REST-only — never via chat)
# =====================================


@router.get("/user/{id}/vehicle", tags=["Vehicle"])
def vehicle_get_all_by_user(
    id: str,
    vehicle_app_service: VehicleAppService = Depends(get_vehicle_app_service),
) -> List[VehicleResponse]:
    return vehicle_app_service.get_all_by_user(user_id=id)


@router.get("/vehicle/{id}", tags=["Vehicle"])
def vehicle_get(
    id: str,
    vehicle_app_service: VehicleAppService = Depends(get_vehicle_app_service),
) -> VehicleResponse:
    return vehicle_app_service.get_by_id(vehicle_id=id)


@router.get("/vehicle/{id}/maintenance", tags=["Vehicle"])
def vehicle_get_maintenance(
    id: str,
    vehicle_app_service: VehicleAppService = Depends(get_vehicle_app_service),
) -> List[MaintenanceRecordResponse]:
    return vehicle_app_service.get_maintenance(vehicle_id=id)


@router.post("/vehicle", tags=["Vehicle"])
def vehicle_add(
    request: VehicleAdd,
    vehicle_app_service: VehicleAppService = Depends(get_vehicle_app_service),
) -> dict:
    vehicle_id = vehicle_app_service.add(vehicle_add=request)
    return {"vehicle_id": vehicle_id}


@router.put("/vehicle", tags=["Vehicle"])
def vehicle_update(
    request: VehicleUpdate,
    vehicle_app_service: VehicleAppService = Depends(get_vehicle_app_service),
) -> None:
    vehicle_app_service.update(vehicle_update=request)


@router.delete("/vehicle/{id}", tags=["Vehicle"])
def vehicle_delete(
    id: str,
    vehicle_app_service: VehicleAppService = Depends(get_vehicle_app_service),
) -> None:
    vehicle_app_service.delete(vehicle_id=id)


# =====================================
# Pet Routes (write is REST-only — never via chat)
# =====================================


@router.get("/user/{id}/pet", tags=["Pet"])
def pet_get_all_by_user(
    id: str,
    pet_app_service: PetAppService = Depends(get_pet_app_service),
) -> List[PetResponse]:
    return pet_app_service.get_all_by_user(user_id=id)


@router.get("/pet/{id}", tags=["Pet"])
def pet_get(
    id: str,
    pet_app_service: PetAppService = Depends(get_pet_app_service),
) -> PetResponse:
    return pet_app_service.get_by_id(pet_id=id)


@router.get("/pet/{id}/health-event", tags=["Pet"])
def pet_get_health_events(
    id: str,
    pet_app_service: PetAppService = Depends(get_pet_app_service),
) -> List[PetHealthEventResponse]:
    return pet_app_service.get_health_events(pet_id=id)


@router.post("/pet", tags=["Pet"])
def pet_add(
    request: PetAdd,
    pet_app_service: PetAppService = Depends(get_pet_app_service),
) -> dict:
    pet_id = pet_app_service.add(pet_add=request)
    return {"pet_id": pet_id}


@router.put("/pet", tags=["Pet"])
def pet_update(
    request: PetUpdate,
    pet_app_service: PetAppService = Depends(get_pet_app_service),
) -> None:
    pet_app_service.update(pet_update=request)


@router.delete("/pet/{id}", tags=["Pet"])
def pet_delete(
    id: str,
    pet_app_service: PetAppService = Depends(get_pet_app_service),
) -> None:
    pet_app_service.delete(pet_id=id)
