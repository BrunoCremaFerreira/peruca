from typing import List, Optional
from application.appservices.view_models import ShoppingListCleanType, ShoppingListItemResponse
from domain.commands import ShoppingListItemAdd, ShoppingListItemUpdate
from domain.exceptions import EmptyParamValidationError
from domain.interfaces.repository import ShoppingListRepository
from infra.utils import auto_map, is_null_or_whitespace

class ShoppingListAppService:
    """
    Shopping List Application Service
    """

    def __init__(self, shopping_list_repository: ShoppingListRepository):
        self.shopping_list_repository = shopping_list_repository

    # =====================================
    # Queries
    # =====================================

    def get_by_id(self, item_id: str) -> Optional[ShoppingListItemResponse]:
        if is_null_or_whitespace(item_id):
            raise EmptyParamValidationError(param_name="item_id")
        
        item = self.shopping_list_repository.get_by_id(item_id=item_id)
        return auto_map(item, ShoppingListItemResponse)

    def get_all(self) -> List[ShoppingListItemResponse]:
        items = self.shopping_list_repository.get_all()
        return [auto_map(item, ShoppingListItemResponse) for item in items]

    # =====================================
    # Commands
    # =====================================

    def add(self, item_add: ShoppingListItemAdd):
        pass

    def update(self, item: ShoppingListItemUpdate):
        pass

    def delete(self, item: str):
        pass

    def clear(self, clean_type: ShoppingListCleanType):
        pass

    def check(self, item_id: str):
        pass

    def uncheck(self, item_id: str):
        pass