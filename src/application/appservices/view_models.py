from dataclasses import dataclass

# =====================================
# LLM 
# =====================================
@dataclass
class ChatRequest:
    message: str
    user_id: str
    chat_id: str

@dataclass
class ChatResponse:
    response: str
    user_id: str
    chat_id: str

# =====================================
# User
# =====================================
@dataclass
class UserAdd:
    name: str = ""
    summary: str = ""

@dataclass
class UserUpdate:
    id: str = ""
    name: str = ""
    summary: str = ""

@dataclass
class UserResponse:
    id: str = ""
    name: str = ""
    summary: str = ""