from typing import List
from application.appservices.view_models import ShoppingListCleanType, ShoppingListItemResponse
from domain.commands import ShoppingListItemAdd, ShoppingListItemUpdate

class ShoppingListAppService:
    """
    Shopping List Application Service
    """

    def __init__(self):
        pass

    def get_by_id(item_id: str) -> ShoppingListItemResponse:
        pass

    def get_all() -> List[ShoppingListItemResponse]:
        pass

    def add(item_add: ShoppingListItemAdd):
        pass

    def update(item: ShoppingListItemUpdate):
        pass

    def delete(item: str):
        pass

    def clear(clean_type: ShoppingListCleanType):
        pass

    def check(item_id: str):
        pass

    def uncheck(item_id: str):
        pass