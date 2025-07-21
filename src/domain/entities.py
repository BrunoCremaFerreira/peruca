from dataclasses import dataclass
from datetime import datetime, timezone

# ====================================
# Base entities Classes
# ====================================
@dataclass
class BaseEntity:
    id: str = ""
    when_created: datetime = datetime.now(timezone.utc)

# ====================================
# User Related Classes
# ====================================

@dataclass
class User(BaseEntity):
    external_id: str = ""
    name: str = ""
    summary: str = ""

# ====================================
# Shopping List Related Classes
# ====================================
@dataclass
class ShoppingListItem(BaseEntity):
    name: str = ""
    quantity: float = 1
    checked: bool = False

# ====================================
# Graph Related Classes
# ====================================

@dataclass
class GraphInvokeRequest:
    """
    LLM processing request entity
    """

    message: str
    user: User