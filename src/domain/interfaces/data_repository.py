from abc import ABC, abstractmethod
from typing import List, Optional

from domain.commands import LightTurnOn
from domain.entities import (
    ShoppingListItem,
    SmartHomeArea,
    SmartHomeEntityAlias,
    SmartHomeLight,
    User,
    UserMemory,
)


# =====================================
# Data Repository
# =====================================
class UserRepository(ABC):
    """
    User Repository
    """

    @abstractmethod
    def add(self, user: User):
        """
        Add User
        """
        pass

    @abstractmethod
    def get_by_id(self, user_id: str) -> Optional[User]:
        """
        Get User By Id
        """
        pass

    @abstractmethod
    def get_by_external_id(self, external_id: str) -> Optional[User]:
        """
        Get User By external_Id
        """
        pass

    @abstractmethod
    def get_all(self) -> List[User]:
        """
        Get all Users
        """
        pass

    @abstractmethod
    def update(self, user: User):
        """
        Update User
        """
        pass

    @abstractmethod
    def delete(self, user_id: str):
        """
        Delete User
        """
        pass


class UserMemoryRepository(ABC):
    """
    UserMemory Repository
    """

    @abstractmethod
    def add(self, memory: UserMemory):
        """
        Add UserMemory
        """
        pass

    @abstractmethod
    def get_by_id(self, memory_id: str) -> Optional[UserMemory]:
        """
        Get UserMemory By Id
        """
        pass

    @abstractmethod
    def get_all_by_user_id(self, user_id: str) -> List[UserMemory]:
        """
        Get all UserMemory by user_id
        """
        pass

    @abstractmethod
    def delete(self, memory_id: str):
        """
        Delete UserMemory
        """
        pass

    @abstractmethod
    def delete_all_by_user_id(self, user_id: str):
        """
        Delete all UserMemory by user_id
        """
        pass


class ShoppingListRepository(ABC):
    """
    User Repository
    """

    @abstractmethod
    def add(self, item: ShoppingListItem):
        """
        Add Shopping List
        """
        pass

    @abstractmethod
    def get_by_id(self, item_id: str) -> Optional[ShoppingListItem]:
        """
        Get Shopping List Item By Id
        """
        pass

    @abstractmethod
    def get_by_name(self, item_name: str) -> Optional[ShoppingListItem]:
        """
        Get Shopping List Item By name
        """
        pass

    @abstractmethod
    def get_all(self) -> List[ShoppingListItem]:
        """
        List All Shopping List
        """
        pass

    @abstractmethod
    def update(self, item: ShoppingListItem):
        """
        Update Shopping List Item
        """
        pass

    @abstractmethod
    def delete(self, item_id: str):
        """
        Delete Shopping List Item
        """
        pass

    @abstractmethod
    def clear(self):
        """
        Delete all Shopping List Item
        """
        pass

    @abstractmethod
    def check(self, item_id: str) -> None:
        """
        Mark a Shopping List Item as checked
        """
        pass

    @abstractmethod
    def uncheck(self, item_id: str) -> None:
        """
        Mark a Shopping List Item as unchecked
        """
        pass


# =====================================
# Temp Data Repository
# =====================================
class ContextRepository(ABC):
    """
    Interface for LLM Context operations.
    """

    @abstractmethod
    def connect() -> None:
        """
        Connect to database
        """
        pass

    @abstractmethod
    async def set_key(self, key: str, value: str):
        """
        Stores a value associated with a key.
        """
        pass

    @abstractmethod
    async def get_key(self, key: str) -> str:
        """
        Retrieves the value associated with a key.
        """
        pass

    @abstractmethod
    async def delete_key(self, key: str) -> bool:
        """
        Deletes a key from the cache.
        """
        pass


# =====================================
# Conversation Context Store (history + compaction summary)
# =====================================
class ConversationContextStore(ABC):
    """
    Read/compaction contract over a user's conversation context: the raw chat
    history and the summary that stands for the turns already compacted away.

    It operates on the SERIALIZED form of the history — [{"type": "human"|"ai",
    "content": str}] — so the domain stays free of any chat framework type.

    Separate from ContextRepository (a key/value cache) because compaction needs
    a primitive no key/value store has: swapping a prefix of the history for its
    summary atomically, and only if that prefix has not changed meanwhile.
    """

    @abstractmethod
    def get_summary(self, user_id: str) -> Optional[dict]:
        """
        Return {"summary": str, "covers": int, "updated_at": iso} for the turns
        already compacted away, or None when the user has never been compacted.
        """
        pass

    @abstractmethod
    def read_history(self, user_id: str) -> List[dict]:
        """
        Return the raw history as [{"type": "human"|"ai", "content": str}], in
        order; an empty list when there is none.
        """
        pass

    @abstractmethod
    def apply_compaction(
        self,
        user_id: str,
        expected_count: int,
        expected_digest: str,
        summary: str,
    ) -> bool:
        """
        Verify-before-swap: replace the first `expected_count` messages with
        `summary` and keep the current tail, but only while that prefix still
        matches `expected_digest` (the caller snapshotted it before a slow LLM
        call). Return False and change nothing when it no longer matches — a
        reset or a concurrent compaction got there first.
        """
        pass

    @abstractmethod
    def clear(self, user_id: str) -> None:
        """
        Wipe the history AND the summary — a surviving summary would resurrect
        the context the user just reset.
        """
        pass


# =====================================
# Image Store (inbound chat images)
# =====================================
class ImageStore(ABC):
    """
    Blob store for inbound chat images (full data URIs), kept OUT of the
    conversation history so a later turn can re-analyse the pixels on demand.

    Separate from ContextRepository (ISP: a blob store is not a chat history).
    All operations are scoped by ``user_id`` so an image_id from one user can
    never resolve another user's blob.
    """

    @abstractmethod
    def save(self, user_id: str, image_id: str, data_uri: str) -> None:
        """
        Store a data URI under a per-user, per-image handle.
        """
        pass

    @abstractmethod
    def get(self, user_id: str, image_id: str) -> Optional[str]:
        """
        Retrieve a stored data URI, or None when absent/expired.
        """
        pass

    @abstractmethod
    def next_index(self, user_id: str) -> int:
        """
        Return the next stable per-user handle N (the ``#N`` written in the
        history line and used to resolve the blob later).
        """
        pass

    @abstractmethod
    def latest_id(self, user_id: str) -> Optional[str]:
        """
        Return the id of the most recently stored image for the user (the
        "most recent" target of a re-vision request), or None when empty.
        """
        pass


# =====================================
# Smart Home Etity Data Repository
# =====================================
class SmartHomeEntityAliasRepository(ABC):
    """
    Interface for Smart Home Entity  Data Repository
    """

    @abstractmethod
    def add(self, entity_alias: SmartHomeEntityAlias):
        """
        Add Smart Home Entity Alias
        """
        pass

    @abstractmethod
    def get_by_entity_id(self, entity_id: str) -> Optional[SmartHomeEntityAlias]:
        """
        Get Smart Home Entity Alias by Entity Id
        """
        pass

    @abstractmethod
    def get_by_alias(self, alias: str) -> Optional[SmartHomeEntityAlias]:
        """
        Get Smart Home Entity Alias
        """
        pass

    @abstractmethod
    def get_all(self, entity_id_starts_with: str = "") -> List[SmartHomeEntityAlias]:
        """
        Get All Smart Home Entity Alias
        """
        pass

    @abstractmethod
    def delete_all(self) -> None:
        """
        Remove all SmartHomeEntityAlias
        """
        pass


# =====================================
# Smart Home Area Data Repository
# =====================================
class SmartHomeAreaRepository(ABC):
    """
    Interface for Smart Home Area Data Repository
    """

    @abstractmethod
    def add(self, area: SmartHomeArea) -> None:
        """
        Add Smart Home Area
        """
        pass

    @abstractmethod
    def get_all(self) -> List[SmartHomeArea]:
        """
        Get all Smart Home Areas
        """
        pass

    @abstractmethod
    def get_by_area_id(self, area_id: str) -> Optional[SmartHomeArea]:
        """
        Get Smart Home Area by area_id
        """
        pass

    @abstractmethod
    def delete_all(self) -> None:
        """
        Remove all SmartHomeArea
        """
        pass
