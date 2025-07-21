from typing import List
from application.appservices.view_models import UserResponse
from domain.commands import UserAdd, UserUpdate
from domain.entities import User
from domain.exceptions import EmptyParamValidationError
from domain.interfaces.repository import UserRepository
from domain.services.user_service import UserService
from infra.utils import auto_map, is_null_or_whitespace


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
        
        if is_null_or_whitespace(user_id):
            raise EmptyParamValidationError(param_name="user_id")
        
        user = self.user_repository.get_by_id(user_id=user_id)
        return auto_map(user, UserResponse, True)
    
    def get_by_external_id(self, external_id: str)-> UserResponse:
        
        if is_null_or_whitespace(external_id):
            raise EmptyParamValidationError(param_name="external_id")
        
        user = self.user_repository.get_by_external_id(external_id=external_id)
        return auto_map(user, UserResponse, True)
    
    def get_all(self)-> List[UserResponse]:
        users = self.user_repository.get_all()
        return [auto_map(user, UserResponse) for user in users]

    # =====================================
    # Commands
    # =====================================

    def add(self, user_add: UserAdd) -> str:
        user = auto_map(user_add, User)
        return self.user_service.add(user=user)

    def update(self, user_update: UserUpdate) -> None:
        user = auto_map(user_update, User)
        self.user_service.update(user=user)
        