from typing import List, Optional
from application.appservices.view_models import ShoppingListCleanType, ShoppingListItemResponse
from domain.commands import ShoppingListItemAdd, ShoppingListItemUpdate
from domain.exceptions import EmptyParamValidationError
from domain.interfaces.repository import ShoppingListRepository
from domain.services.shopping_list_service import ShoppingListService
from infra.utils import auto_map, is_null_or_whitespace

class ShoppingListAppService:
    """
    Shopping List Application Service
    """

    def __init__(self, 
                 shopping_list_repository: ShoppingListRepository,
                 shopping_list_service: ShoppingListService):
        self.shopping_list_repository = shopping_list_repository
        self.shopping_list_service = shopping_list_service

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

    def add(self, item_add: ShoppingListItemAdd) -> str:
        return self.shopping_list_service.add(item_add=item_add)

    def update(self, item: ShoppingListItemUpdate):
        return self.shopping_list_service.update(item=item)

    def delete(self, item_id: str):
        return self.shopping_list_repository.delete(item_id=item_id)

    def clear(self, clean_type: ShoppingListCleanType):

        all_items = self.shopping_list_repository.get_all()
        
        for item in all_items:
            if clean_type == ShoppingListCleanType.CHECKED and item.checked:
                continue
            
            self.shopping_list_repository.delete(item_id=item.id)

    def check(self, item_id: str):
        return self.shopping_list_service.check(item_id=item_id)

    def uncheck(self, item_id: str):
        return self.uncheck(item_id=item_id)