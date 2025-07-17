from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import uuid

# ========================
# Base entities Classes
# ========================
@dataclass
class BaseEntity:
    id: str = ""
    when_created: datetime = datetime.now(timezone.utc)

# ========================
# User Related Classes
# ========================

@dataclass
class User(BaseEntity):
    external_id: str = ""
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