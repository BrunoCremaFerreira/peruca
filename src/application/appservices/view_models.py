from dataclasses import dataclass, field
from enum import Enum


# =====================================
# LLM
# =====================================
@dataclass
class ChatRequest:
    message: str = ""
    external_user_id: str = ""
    chat_id: str = ""
    # Inbound images as full data URIs ("data:image/jpeg;base64,..."). Default
    # empty preserves retro-compatibility with every existing positional call.
    images: list[str] = field(default_factory=list)


@dataclass
class ChatResponse:
    response: str = ""
    external_user_id: str = ""
    chat_id: str = ""


# =====================================
# User
# =====================================
@dataclass
class UserResponse:
    id: str = ""
    external_id: str = ""
    name: str = ""
    summary: str = ""


# =====================================
# User Memory
# =====================================
@dataclass
class UserMemoryResponse:
    id: str = ""
    user_id: str = ""
    content: str = ""


# =====================================
# Shopping List
# =====================================
@dataclass
class ShoppingListItemResponse:
    id: str = ""
    name: str = ""
    quantity: float = 1
    numeric_order: int = 0
    group_name: str = ""


class ShoppingListCleanType(Enum):
    ALL = "ALL"
    CHECKED = "CHECKED"
