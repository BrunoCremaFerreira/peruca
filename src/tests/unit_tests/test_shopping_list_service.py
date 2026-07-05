import uuid
from unittest.mock import MagicMock, call
import pytest

from domain.commands import ShoppingListItemAdd, ShoppingListItemUpdate
from domain.entities import ShoppingListItem
from domain.exceptions import ValidationError
from domain.services.shopping_list_service import ShoppingListService


"""
ShoppingListService Unit Tests
"""


def _sample_item(name="Bread", quantity=2.0, checked=False) -> ShoppingListItem:
    return ShoppingListItem(
        id=str(uuid.uuid4()), name=name, quantity=quantity, checked=checked
    )


class TestShoppingListServiceAdd:
    def test_add_valid_item_calls_repository(self, shopping_list_repo_mock):
        # Arrange
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act
        service.add(ShoppingListItemAdd(name="Milk", quantity=1))
        # Assert
        shopping_list_repo_mock.add.assert_called_once()

    def test_add_assigns_uuid_to_item(self, shopping_list_repo_mock):
        # Arrange
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act
        service.add(ShoppingListItemAdd(name="Eggs", quantity=12))
        # Assert
        added_item: ShoppingListItem = shopping_list_repo_mock.add.call_args[0][0]
        assert uuid.UUID(added_item.id)

    def test_add_raises_when_name_is_empty(self, shopping_list_repo_mock):
        # Arrange
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.add(ShoppingListItemAdd(name="", quantity=1))
        assert "Name" in str(exc.value.errors)

    def test_add_raises_when_name_too_short(self, shopping_list_repo_mock):
        # Arrange
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.add(ShoppingListItemAdd(name="A", quantity=1))
        assert "2" in str(exc.value.errors) or "characters" in str(exc.value.errors)

    def test_add_raises_when_quantity_is_zero(self, shopping_list_repo_mock):
        # Arrange
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.add(ShoppingListItemAdd(name="Butter", quantity=0))
        assert "quantity" in str(exc.value.errors).lower() or "Invalid" in str(
            exc.value.errors
        )

    def test_add_raises_when_quantity_is_negative(self, shopping_list_repo_mock):
        # Arrange
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError):
            service.add(ShoppingListItemAdd(name="Sugar", quantity=-5))

    def test_add_raises_when_item_already_in_list(self, shopping_list_repo_mock):
        # Arrange
        shopping_list_repo_mock.get_by_name.return_value = _sample_item(name="Milk")
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.add(ShoppingListItemAdd(name="Milk", quantity=1))
        assert "Milk" in str(exc.value.errors)


class TestShoppingListServiceGetAll:
    def test_get_all_returns_list_from_repository(self, shopping_list_repo_mock):
        # Arrange
        items = [_sample_item("Apple"), _sample_item("Banana")]
        shopping_list_repo_mock.get_all.return_value = items
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act
        result = service.get_all()
        # Assert
        assert result == items
        shopping_list_repo_mock.get_all.assert_called_once()

    def test_get_all_returns_empty_list_when_no_items(self, shopping_list_repo_mock):
        # Arrange
        shopping_list_repo_mock.get_all.return_value = []
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act
        result = service.get_all()
        # Assert
        assert result == []


class TestShoppingListServiceUpdateQuantity:
    def test_update_quantity_valid_item_calls_repository(self, shopping_list_repo_mock):
        # Arrange
        item = _sample_item(name="Cheese", quantity=1.0)
        shopping_list_repo_mock.get_by_id.return_value = item
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        cmd = ShoppingListItemUpdate(id=item.id, name=item.name, quantity=3.0)
        # Act
        service.update_quantity(cmd)
        # Assert
        shopping_list_repo_mock.update.assert_called_once()
        assert item.quantity == 3.0

    def test_update_quantity_raises_when_item_not_found(self, shopping_list_repo_mock):
        # Arrange
        shopping_list_repo_mock.get_by_id.return_value = None
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        cmd = ShoppingListItemUpdate(id=str(uuid.uuid4()), name="Ghost", quantity=1)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.update_quantity(cmd)
        assert "was not found" in str(exc.value.errors)

    def test_update_quantity_raises_when_quantity_invalid(
        self, shopping_list_repo_mock
    ):
        # Arrange
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        cmd = ShoppingListItemUpdate(id=str(uuid.uuid4()), name="Yogurt", quantity=-2)
        # Act / Assert
        with pytest.raises(ValidationError):
            service.update_quantity(cmd)


class TestShoppingListServiceCheck:
    def test_check_sets_checked_true_and_updates(self, shopping_list_repo_mock):
        # Arrange
        item = _sample_item(name="Tomato", checked=False)
        shopping_list_repo_mock.get_by_id.return_value = item
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act
        service.check(item.id)
        # Assert
        assert item.checked is True
        shopping_list_repo_mock.update.assert_called_once()

    def test_check_raises_when_item_not_found(self, shopping_list_repo_mock):
        # Arrange
        shopping_list_repo_mock.get_by_id.return_value = None
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.check(str(uuid.uuid4()))
        assert "was not found" in str(exc.value.errors)

    def test_check__already_checked_item__calls_update_again(
        self, shopping_list_repo_mock
    ):
        # Arrange — item already has checked=True; service must still call update
        item = _sample_item(name="Tomato", checked=True)
        shopping_list_repo_mock.get_by_id.return_value = item
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act
        service.check(item.id)
        # Assert — update is called regardless of prior state
        shopping_list_repo_mock.update.assert_called_once()
        assert item.checked is True

    def test_check__invalid_id_empty_string__raises_validation_error(
        self, shopping_list_repo_mock
    ):
        # Arrange
        # This test documents the bug: check() calls validate_id() but omits
        # the final .validate() call, so ValidationError is never raised.
        # The test is expected to FAIL until the bug is fixed.
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError):
            service.check("")


class TestShoppingListServiceUncheck:
    def test_uncheck_sets_checked_false_and_updates(self, shopping_list_repo_mock):
        # Arrange
        item = _sample_item(name="Onion", checked=True)
        shopping_list_repo_mock.get_by_id.return_value = item
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act
        service.uncheck(item.id)
        # Assert
        assert item.checked is False
        shopping_list_repo_mock.update.assert_called_once()

    def test_uncheck_raises_when_item_not_found(self, shopping_list_repo_mock):
        # Arrange
        shopping_list_repo_mock.get_by_id.return_value = None
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.uncheck(str(uuid.uuid4()))
        assert "was not found" in str(exc.value.errors)

    def test_uncheck__already_unchecked_item__calls_update_again(
        self, shopping_list_repo_mock
    ):
        # Arrange — item already has checked=False; service must still call update
        item = _sample_item(name="Onion", checked=False)
        shopping_list_repo_mock.get_by_id.return_value = item
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act
        service.uncheck(item.id)
        # Assert — update is called regardless of prior state
        shopping_list_repo_mock.update.assert_called_once()
        assert item.checked is False

    def test_uncheck__invalid_id_empty_string__raises_validation_error(
        self, shopping_list_repo_mock
    ):
        # Arrange
        # This test documents the bug: uncheck() calls validate_id() but omits
        # the final .validate() call, so ValidationError is never raised.
        # The test is expected to FAIL until the bug is fixed.
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError):
            service.uncheck("")


class TestShoppingListServiceDelete:
    def test_delete_calls_repository_with_correct_id(self, shopping_list_repo_mock):
        # Arrange
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        item_id = str(uuid.uuid4())
        # Act
        service.delete(item_id)
        # Assert
        shopping_list_repo_mock.delete.assert_called_once_with(item_id=item_id)

    def test_delete__invalid_id_empty_string__raises_validation_error(
        self, shopping_list_repo_mock
    ):
        # Arrange
        # Known bug: delete() calls validate_id() but omits the final .validate(),
        # so ValidationError is never raised. Expected to FAIL until fixed.
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act / Assert
        with pytest.raises(ValidationError):
            service.delete("")


class TestShoppingListServiceFindItemsByName:
    """
    find_items_by_name(query, items) resolves a user-typed term against the
    already-loaded shopping list, without touching the repository and without
    any LLM. Matching layers, in priority order (first that matches wins):
      1. exact normalized (accent/case-insensitive) — short-circuits
      2. partial (query tokens are a subset of the item name tokens)
      3. typo (difflib ratio >= 0.8, with a min-length guard)
    """

    def test_exact_baseline__returns_the_single_item(self, shopping_list_repo_mock):
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        leite = _sample_item(name="Leite")
        items = [leite, _sample_item(name="Arroz")]

        result = service.find_items_by_name("Leite", items)

        assert result == [leite]

    def test_exact_is_case_and_accent_insensitive(self, shopping_list_repo_mock):
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        cafe = _sample_item(name="Café")
        result = service.find_items_by_name("cafe", [cafe])
        assert result == [cafe]

    def test_partial__single_token_query_matches_multiword_name(
        self, shopping_list_repo_mock
    ):
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        carne = _sample_item(name="Carne de panela")
        result = service.find_items_by_name("carne", [carne])
        assert result == [carne]

    def test_partial__inner_token_query_matches_multiword_name(
        self, shopping_list_repo_mock
    ):
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        carne = _sample_item(name="Carne de panela")
        result = service.find_items_by_name("panela", [carne])
        assert result == [carne]

    def test_multiple_partial_matches__returns_all(self, shopping_list_repo_mock):
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        panela = _sample_item(name="Carne de panela")
        seca = _sample_item(name="Carne seca")
        result = service.find_items_by_name("carne", [panela, seca])
        assert set(id(i) for i in result) == {id(panela), id(seca)}
        assert len(result) == 2

    def test_exact_has_priority_over_partial(self, shopping_list_repo_mock):
        # "Carne" exists literally AND is a token of "Carne de panela"; the exact
        # match must short-circuit and return ONLY the literal item.
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        carne = _sample_item(name="Carne")
        panela = _sample_item(name="Carne de panela")
        result = service.find_items_by_name("carne", [carne, panela])
        assert result == [carne]

    def test_typo__fuzzy_match_below_edit_distance(self, shopping_list_repo_mock):
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        crepom = _sample_item(name="Crepom")
        result = service.find_items_by_name("grepom", [crepom])
        assert result == [crepom]

    @pytest.mark.parametrize(
        "query,name",
        [
            ("chocolatte", "Chocolate"),
            ("banan", "Banana"),
            ("tomatte", "Tomate"),
        ],
    )
    def test_typo__parametrized(self, shopping_list_repo_mock, query, name):
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        item = _sample_item(name=name)
        result = service.find_items_by_name(query, [item])
        assert result == [item]

    def test_exact_has_priority_over_fuzzy(self, shopping_list_repo_mock):
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # "Crepom" (exact) and "Crespom" (a fuzzy neighbour) both present; exact wins.
        crepom = _sample_item(name="Crepom")
        crespom = _sample_item(name="Crespom")
        result = service.find_items_by_name("Crepom", [crepom, crespom])
        assert result == [crepom]

    def test_no_match__returns_empty(self, shopping_list_repo_mock):
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        result = service.find_items_by_name("chocolate", [_sample_item(name="Leite")])
        assert result == []

    def test_different_word_below_threshold__returns_empty(
        self, shopping_list_repo_mock
    ):
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        result = service.find_items_by_name("carne", [_sample_item(name="leite")])
        assert result == []

    def test_empty_item_list__returns_empty(self, shopping_list_repo_mock):
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        assert service.find_items_by_name("carne", []) == []

    def test_blank_query__returns_empty(self, shopping_list_repo_mock):
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        assert service.find_items_by_name("   ", [_sample_item(name="Leite")]) == []

    def test_does_not_access_repository(self, shopping_list_repo_mock):
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        service.find_items_by_name("carne", [_sample_item(name="Carne de panela")])
        shopping_list_repo_mock.get_all.assert_not_called()
        shopping_list_repo_mock.get_by_id.assert_not_called()
        shopping_list_repo_mock.get_by_name.assert_not_called()


class TestShoppingListServiceClear:
    def test_clear_calls_repository_clear(self, shopping_list_repo_mock):
        # Arrange
        service = ShoppingListService(shopping_list_repository=shopping_list_repo_mock)
        # Act
        service.clear()
        # Assert
        shopping_list_repo_mock.clear.assert_called_once()
