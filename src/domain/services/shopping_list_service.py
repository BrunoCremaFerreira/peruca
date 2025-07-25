from datetime import datetime, timezone
import uuid
from application.appservices.view_models import ShoppingListCleanType
from domain.commands import ShoppingListItemAdd, ShoppingListItemUpdate
from domain.entities import ShoppingListItem
from domain.interfaces.repository import ShoppingListRepository
from domain.validations.shopping_list_item_validation import ShoppingListItemValidator
from infra.utils import auto_map


class ShoppingListService:
    """
    Shopping List Service
    """

    def __init__(self, shopping_list_repository: ShoppingListRepository):
        self.shopping_list_repository = shopping_list_repository

    def add(self, item_add: ShoppingListItemAdd):
        
        ShoppingListItemValidator() \
            .validate_name(item_add.name) \
            .validate_quantity(item_add.quantity) \
            .validate()

        item = auto_map(item_add, ShoppingListItem)
        item.id = str(uuid.uuid4())
        item.when_created = datetime.now(timezone.utc)

        self.shopping_list_repository.add(item)

    def update(self, item: ShoppingListItemUpdate):
        pass

    def delete(self, item_id: str):
        pass

    def check(self, item_id: str):
        pass

    def uncheck(self, item_id: str):
        pass