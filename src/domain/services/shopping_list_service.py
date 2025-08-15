from datetime import datetime, timezone
from typing import List
import uuid
from domain.commands import ShoppingListItemAdd, ShoppingListItemUpdate
from domain.entities import ShoppingListItem
from domain.exceptions import ValidationError
from domain.interfaces.data_repository import ShoppingListRepository
from domain.validations.shopping_list_item_validation import ShoppingListItemValidator
from infra.utils import auto_map


class ShoppingListService:
    """
    Shopping List Service
    """

    def __init__(self, shopping_list_repository: ShoppingListRepository):
        self.shopping_list_repository = shopping_list_repository

    def add(self, item_add: ShoppingListItemAdd):
        """
        Add a new Item on Shopping List
        """
        
        ShoppingListItemValidator() \
            .validate_name(item_add.name) \
            .validate_quantity(item_add.quantity) \
            .validate()

        db_item = self.shopping_list_repository \
            .get_by_name(item_name=item_add.name)
        
        if db_item:
            raise ValidationError([f"The item '{item_add.name}' is already in the shopping list"])

        item = auto_map(item_add, ShoppingListItem)
        item.id = str(uuid.uuid4())
        item.when_created = datetime.now(timezone.utc)

        self.shopping_list_repository.add(item)

    def get_all(self) -> List[ShoppingListItem]:
        """
        Get all Items from Shopping List
        """

        return self.shopping_list_repository.get_all()

    def update_quantity(self, item: ShoppingListItemUpdate):
        """
        Update a Shopping List Item
        """
        
        ShoppingListItemValidator() \
            .validate_id(item.id) \
            .validate_quantity(item.quantity) \
            .validate()
        
        db_item = self.shopping_list_repository \
            .get_by_id(item_id=item.id)
        
        if not db_item:
            raise ValidationError([f"The item with id '{item.id}' was not found in the shopping list"])
        
        db_item.quantity = item.quantity
        self.shopping_list_repository \
            .update(item=db_item)

    def delete(self, item_id: str):
        """
        Delete a Shopping List Item
        """

        ShoppingListItemValidator() \
            .validate_id(item_id)

        self.shopping_list_repository.delete(item_id=item_id)

    def clear(self): 
        """
        Remove all Shopping List Items
        """

        self.shopping_list_repository.clear()

    def check(self, item_id: str):
        """
        Check an Item from Shopping List
        """

        ShoppingListItemValidator() \
            .validate_id(item_id)
        
        db_item = self.shopping_list_repository \
            .get_by_id(item_id=item_id)
        
        if not db_item:
            raise ValidationError([f"The item with id '{item_id}' was not found in the shopping list"])
        
        db_item.checked = True
        self.shopping_list_repository \
            .update(item=db_item)

    def uncheck(self, item_id: str):
        """
        Uncheck an Shopping List Item
        """

        ShoppingListItemValidator() \
            .validate_id(item_id)
        
        db_item = self.shopping_list_repository \
            .get_by_id(item_id=item_id)
        
        if not db_item:
            raise ValidationError([f"The item with id '{item_id}' was not found in the shopping list"])
        
        db_item.checked = False
        self.shopping_list_repository \
            .update(item=db_item)