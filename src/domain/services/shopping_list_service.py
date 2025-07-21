from application.appservices.view_models import ShoppingListCleanType
from domain.commands import ShoppingListItemAdd, ShoppingListItemUpdate
from domain.interfaces.repository import ShoppingListRepository


class ShoppingListService:
    """
    Shopping List Service
    """

    def __init__(self, shopping_list_repository: ShoppingListRepository):
        self.shopping_list_repository = shopping_list_repository

    def add(self, item_add: ShoppingListItemAdd):
        pass

    def update(self, item: ShoppingListItemUpdate):
        pass

    def delete(self, item_id: str):
        pass

    def check(self, item_id: str):
        pass

    def uncheck(self, item_id: str):
        pass