from dataclasses import dataclass

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
