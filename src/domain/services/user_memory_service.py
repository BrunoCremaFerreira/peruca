import uuid
from datetime import datetime, timezone
from typing import List

from domain.commands import UserMemoryAdd
from domain.entities import UserMemory
from domain.exceptions import ValidationError
from domain.interfaces.data_repository import UserMemoryRepository
from domain.validations.user_memory_validation import UserMemoryValidator
from infra.utils import auto_map


class UserMemoryService:
    """
    UserMemory Service
    """

    def __init__(self, user_memory_repository: UserMemoryRepository):
        self.user_memory_repository = user_memory_repository

    def add(self, memory_add: UserMemoryAdd) -> str:
        """
        Add a new UserMemory (skips persistence when content already exists)
        """

        memory = auto_map(memory_add, UserMemory)

        if not memory:
            raise ValidationError({"The memory is null"})

        memory.id = str(uuid.uuid4())
        memory.when_created = datetime.now(timezone.utc)

        UserMemoryValidator().validate_id(memory.id).validate_user_id(
            memory.user_id
        ).validate_content(memory.content).validate()

        normalized = memory.content.strip().lower()
        existing = self.user_memory_repository.get_all_by_user_id(memory.user_id)
        if any(item.content.strip().lower() == normalized for item in existing):
            return memory.id

        self.user_memory_repository.add(memory)
        return memory.id

    def get_all_by_user(self, user_id: str) -> List[UserMemory]:
        """
        Get all memories of a user
        """

        return self.user_memory_repository.get_all_by_user_id(user_id)

    def delete(self, memory_id: str) -> None:
        """
        Delete a UserMemory
        """

        UserMemoryValidator().validate_id(memory_id).validate()
        self.user_memory_repository.delete(memory_id)

    def clear_by_user(self, user_id: str) -> None:
        """
        Delete all memories of a user
        """

        UserMemoryValidator().validate_user_id(user_id).validate()
        self.user_memory_repository.delete_all_by_user_id(user_id)
