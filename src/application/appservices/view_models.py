from dataclasses import dataclass

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