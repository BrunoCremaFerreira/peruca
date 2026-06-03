from typing import List

from application.appservices.view_models import UserMemoryResponse
from domain.services.user_memory_service import UserMemoryService
from infra.utils import auto_map


class UserMemoryAppService:
    """
    Application User Memory App Service
    """

    def __init__(self, user_memory_service: UserMemoryService):
        self.user_memory_service = user_memory_service

    # =====================================
    # Queries
    # =====================================

    def get_all_by_user(self, user_id: str) -> List[UserMemoryResponse]:
        memories = self.user_memory_service.get_all_by_user(user_id)
        return [auto_map(memory, UserMemoryResponse) for memory in memories]

    # =====================================
    # Commands
    # =====================================

    def delete(self, memory_id: str) -> None:
        self.user_memory_service.delete(memory_id)

    def clear_by_user(self, user_id: str) -> None:
        self.user_memory_service.clear_by_user(user_id)
