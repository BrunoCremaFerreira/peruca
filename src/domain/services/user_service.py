
import uuid
from domain.entities import User
from domain.exceptions import ValidationError
from domain.interfaces.repository import UserRepository
from domain.validations.user_validation import UserValidator


class UserService:
    """
    User Service
    """

    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    def add(self, user: User) -> str:
        """
        Add a new User
        """
        
        if not user:
            raise ValidationError({f"The user is null"})

        if not user.id:
            user.id = str(uuid.uuid4())

        if not user.external_id:
            user.external_id = user.id

        UserValidator() \
            .validate_id(user.id) \
            .validate_external_id(user.external_id) \
            .validate_name(user.name) \
            .validate_summary(user.summary) \
            .validate()
        
        if self.user_repository.get_by_id(user_id=user.id):
            raise ValidationError({f"The user with id {user.id} already exist"})
        
        if self.user_repository.get_by_external_id(external_user_id=user.external_id):
            raise ValidationError({f"The user with external_id {user.external_id} already exist"})

        self.user_repository.add(user=user)
        return user.id
    
    def update(self, user: User) -> None:
        """
        Update a existing User
        """

        UserValidator() \
            .validate_id(user.id) \
            .validate_external_id(user.external_id) \
            .validate_name(user.name) \
            .validate_summary(user.summary) \
            .validate()
        
        db_user = self.user_repository.get_by_id(user_id=user.id)
        if not db_user:
            raise ValidationError({f"The User with id '{user.id}' was not found"})
        
        if self.user_repository.get_by_external_id(external_user_id=user.external_id):
            raise ValidationError({f"The user with external_id {user.external_id} already exist"})

        self.user_repository.update(user=user)


    def Delete(self, user_id: str) -> None:
        """
        Delete a existing User
        """
        
        UserValidator() \
            .validate_id(user_id) \
            .validate()
        
        db_user = self.user_repository.get_by_id(user_id=user_id)
        if not db_user:
            raise ValidationError({f"The User with id '{user_id}' was not found"})

        self.user_repository.delete(user_id=user_id)
