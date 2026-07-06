from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import List
import uuid
from domain.commands import ShoppingListItemAdd, ShoppingListItemUpdate
from domain.entities import ShoppingListItem
from domain.exceptions import ValidationError
from domain.interfaces.data_repository import ShoppingListRepository
from domain.validations.shopping_list_item_validation import ShoppingListItemValidator
from domain.services.text_matching import normalize as _normalize
from domain.services.text_matching import name_tokens as _name_tokens
from infra.utils import auto_map


# Normalization/tokenization now live in domain.services.text_matching; the
# module-level aliases above are kept so existing importers (and this module)
# keep working unchanged.

# difflib ratio threshold for a typo to count as the same item.
_FUZZY_THRESHOLD = 0.8
# Words shorter than this are not fuzzy-matched — short tokens produce too many
# false positives (e.g. "carne" vs "leite").
_FUZZY_MIN_LENGTH = 4


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

        ShoppingListItemValidator().validate_name(item_add.name).validate_quantity(
            item_add.quantity
        ).validate()

        db_item = self.shopping_list_repository.get_by_name(item_name=item_add.name)

        if db_item:
            raise ValidationError(
                [f"The item '{item_add.name}' is already in the shopping list"]
            )

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

        ShoppingListItemValidator().validate_id(item.id).validate_quantity(
            item.quantity
        ).validate()

        db_item = self.shopping_list_repository.get_by_id(item_id=item.id)

        if not db_item:
            raise ValidationError(
                [f"The item with id '{item.id}' was not found in the shopping list"]
            )

        db_item.quantity = item.quantity
        self.shopping_list_repository.update(item=db_item)

    def delete(self, item_id: str):
        """
        Delete a Shopping List Item
        """

        ShoppingListItemValidator().validate_id(item_id).validate()

        self.shopping_list_repository.delete(item_id=item_id)

    def find_items_by_name(
        self, query: str, items: List[ShoppingListItem]
    ) -> List[ShoppingListItem]:
        """
        Resolve a user-typed term against already-loaded shopping list items,
        deterministically (no LLM, no repository access). Matching layers are
        applied in priority order; the first non-empty layer wins:

          1. exact normalized (accent/case-insensitive) — short-circuits, so a
             literal name is never treated as ambiguous;
          2. partial — the query tokens are a subset of an item's name tokens
             ("carne"/"panela" -> "Carne de panela");
          3. typo — difflib ratio >= threshold, guarded by a minimum length.

        Returns every item matched by the winning layer: 0, 1 or many. The
        caller uses the count to decide whether to act or ask.
        """
        normalized_query = _normalize(query)
        if not normalized_query or not items:
            return []

        # 1. Exact normalized match — highest priority.
        exact = [item for item in items if _normalize(item.name) == normalized_query]
        if exact:
            return exact

        # 2. Partial (token subset) match.
        query_tokens = _name_tokens(query)
        if query_tokens:
            partial = [
                item
                for item in items
                if query_tokens <= _name_tokens(item.name)
            ]
            if partial:
                return partial

        # 3. Typo (fuzzy) match — only for long-enough queries.
        if len(normalized_query) >= _FUZZY_MIN_LENGTH:
            fuzzy = [
                item
                for item in items
                if SequenceMatcher(
                    None, normalized_query, _normalize(item.name)
                ).ratio()
                >= _FUZZY_THRESHOLD
            ]
            if fuzzy:
                return fuzzy

        return []

    def clear(self):
        """
        Remove all Shopping List Items
        """

        self.shopping_list_repository.clear()

    def check(self, item_id: str):
        """
        Check an Item from Shopping List
        """

        ShoppingListItemValidator().validate_id(item_id).validate()

        db_item = self.shopping_list_repository.get_by_id(item_id=item_id)

        if not db_item:
            raise ValidationError(
                [f"The item with id '{item_id}' was not found in the shopping list"]
            )

        db_item.checked = True
        self.shopping_list_repository.update(item=db_item)

    def uncheck(self, item_id: str):
        """
        Uncheck an Shopping List Item
        """

        ShoppingListItemValidator().validate_id(item_id).validate()

        db_item = self.shopping_list_repository.get_by_id(item_id=item_id)

        if not db_item:
            raise ValidationError(
                [f"The item with id '{item_id}' was not found in the shopping list"]
            )

        db_item.checked = False
        self.shopping_list_repository.update(item=db_item)
