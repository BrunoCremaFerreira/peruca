from dataclasses import dataclass
from enum import Enum
import uuid

# ========================
# User Related Classes
# ========================

@dataclass
class User:
    id: str = str(uuid.uuid4())
    name: str = ""
    summary: str = ""


# ========================
# Graph Related Classes
# ========================

@dataclass
class GraphInvokeRequest:
    """
    LLM processing request entity
    """

    message: str
    user: User