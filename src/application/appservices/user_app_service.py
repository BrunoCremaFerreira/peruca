from typing import List
from application.appservices.view_models import UserAdd, UserResponse, UserUpdate
from domain.entities import User
from domain.interfaces.repository import UserRepository
from domain.services.user_service import UserService
from infra.utils import auto_map


class UserAppService:
    """
    Application User App Service
    """

    def __init__(self, user_service: UserService, user_repository: UserRepository):
        self.user_service = user_service
        self.user_repository = user_repository

    # =====================================
    # Queries
    # =====================================

    def get_by_id(self, user_id: str)-> UserResponse:
        user = self.user_repository.get_by_id(user_id=user_id)
        return auto_map(user, UserResponse)
    
    def get_all(self)-> List[UserResponse]:
        users = self.user_repository.list()
        return auto_map(users, List[UserResponse])

    # =====================================
    # Commands
    # =====================================

    def add(self, user_add: UserAdd) -> None:
        user = auto_map(user_add, User)
        self.user_service.add(user=user)

    def update(self, user_update: UserUpdate) -> None:
        user = auto_map(user_update, User)
        self.user_service.add(user=user)
        