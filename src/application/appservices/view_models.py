from dataclasses import dataclass
from enum import Enum

# =====================================
# LLM 
# =====================================
@dataclass
class ChatRequest:
    message: str = ""
    external_user_id: str = ""
    chat_id: str = ""

@dataclass
class ChatResponse:
    response: str = ""
    external_user_id: str = ""
    chat_id: str = ""

# =====================================
# User
# =====================================
@dataclass
class UserAdd:
    name: str = ""
    external_id: str = ""
    summary: str = ""

@dataclass
class UserUpdate:
    id: str = ""
    external_id: str = ""
    name: str = ""
    summary: str = ""

@dataclass
class UserResponse:
    id: str = ""
    external_id: str = ""
    name: str = ""
    summary: str = ""

# =====================================
# Shopping List
# =====================================
@dataclass
class ShoppingListItemAdd:
    name : str = ""
    quantity : float = 1

@dataclass
class ShoppingListItemUpdate:
    id: str = ""
    name : str = ""
    quantity : float = 1

@dataclass
class ShoppingListItemResponse:
    id: str = ""
    name : str = ""
    quantity : float = 1
    numeric_order: int = 0
    group_name: str = ""

class ShoppingListCleanType(Enum):
    ALL = "ALL"
    CHECKED = "CHECKED"