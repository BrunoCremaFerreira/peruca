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


def _make_repo():
    repo = MagicMock()
    repo.get_by_name.return_value = None
    repo.get_by_id.return_value = None
    return repo


def _sample_item(name="Bread", quantity=2.0, checked=False) -> ShoppingListItem:
    return ShoppingListItem(id=str(uuid.uuid4()), name=name, quantity=quantity, checked=checked)


class TestShoppingListServiceAdd:

    def test_add_valid_item_calls_repository(self):
        # Arrange
        repo = _make_repo()
        service = ShoppingListService(shopping_list_repository=repo)
        # Act
        service.add(ShoppingListItemAdd(name="Milk", quantity=1))
        # Assert
        repo.add.assert_called_once()

    def test_add_assigns_uuid_to_item(self):
        # Arrange
        repo = _make_repo()
        service = ShoppingListService(shopping_list_repository=repo)
        # Act
        service.add(ShoppingListItemAdd(name="Eggs", quantity=12))
        # Assert
        added_item: ShoppingListItem = repo.add.call_args[0][0]
        assert uuid.UUID(added_item.id)

    def test_add_raises_when_name_is_empty(self):
        # Arrange
        repo = _make_repo()
        service = ShoppingListService(shopping_list_repository=repo)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.add(ShoppingListItemAdd(name="", quantity=1))
        assert "Name" in str(exc.value.errors)

    def test_add_raises_when_name_too_short(self):
        # Arrange
        repo = _make_repo()
        service = ShoppingListService(shopping_list_repository=repo)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.add(ShoppingListItemAdd(name="A", quantity=1))
        assert "2" in str(exc.value.errors) or "characters" in str(exc.value.errors)

    def test_add_raises_when_quantity_is_zero(self):
        # Arrange
        repo = _make_repo()
        service = ShoppingListService(shopping_list_repository=repo)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.add(ShoppingListItemAdd(name="Butter", quantity=0))
        assert "quantity" in str(exc.value.errors).lower() or "Invalid" in str(exc.value.errors)

    def test_add_raises_when_quantity_is_negative(self):
        # Arrange
        repo = _make_repo()
        service = ShoppingListService(shopping_list_repository=repo)
        # Act / Assert
        with pytest.raises(ValidationError):
            service.add(ShoppingListItemAdd(name="Sugar", quantity=-5))

    def test_add_raises_when_item_already_in_list(self):
        # Arrange
        repo = _make_repo()
        repo.get_by_name.return_value = _sample_item(name="Milk")
        service = ShoppingListService(shopping_list_repository=repo)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.add(ShoppingListItemAdd(name="Milk", quantity=1))
        assert "Milk" in str(exc.value.errors)


class TestShoppingListServiceGetAll:

    def test_get_all_returns_list_from_repository(self):
        # Arrange
        repo = _make_repo()
        items = [_sample_item("Apple"), _sample_item("Banana")]
        repo.get_all.return_value = items
        service = ShoppingListService(shopping_list_repository=repo)
        # Act
        result = service.get_all()
        # Assert
        assert result == items
        repo.get_all.assert_called_once()

    def test_get_all_returns_empty_list_when_no_items(self):
        # Arrange
        repo = _make_repo()
        repo.get_all.return_value = []
        service = ShoppingListService(shopping_list_repository=repo)
        # Act
        result = service.get_all()
        # Assert
        assert result == []


class TestShoppingListServiceUpdateQuantity:

    def test_update_quantity_valid_item_calls_repository(self):
        # Arrange
        repo = _make_repo()
        item = _sample_item(name="Cheese", quantity=1.0)
        repo.get_by_id.return_value = item
        service = ShoppingListService(shopping_list_repository=repo)
        cmd = ShoppingListItemUpdate(id=item.id, name=item.name, quantity=3.0)
        # Act
        service.update_quantity(cmd)
        # Assert
        repo.update.assert_called_once()
        assert item.quantity == 3.0

    def test_update_quantity_raises_when_item_not_found(self):
        # Arrange
        repo = _make_repo()
        repo.get_by_id.return_value = None
        service = ShoppingListService(shopping_list_repository=repo)
        cmd = ShoppingListItemUpdate(id=str(uuid.uuid4()), name="Ghost", quantity=1)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.update_quantity(cmd)
        assert "was not found" in str(exc.value.errors)

    def test_update_quantity_raises_when_quantity_invalid(self):
        # Arrange
        repo = _make_repo()
        service = ShoppingListService(shopping_list_repository=repo)
        cmd = ShoppingListItemUpdate(id=str(uuid.uuid4()), name="Yogurt", quantity=-2)
        # Act / Assert
        with pytest.raises(ValidationError):
            service.update_quantity(cmd)


class TestShoppingListServiceCheck:

    def test_check_sets_checked_true_and_updates(self):
        # Arrange
        repo = _make_repo()
        item = _sample_item(name="Tomato", checked=False)
        repo.get_by_id.return_value = item
        service = ShoppingListService(shopping_list_repository=repo)
        # Act
        service.check(item.id)
        # Assert
        assert item.checked is True
        repo.update.assert_called_once()

    def test_check_raises_when_item_not_found(self):
        # Arrange
        repo = _make_repo()
        repo.get_by_id.return_value = None
        service = ShoppingListService(shopping_list_repository=repo)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.check(str(uuid.uuid4()))
        assert "was not found" in str(exc.value.errors)


class TestShoppingListServiceUncheck:

    def test_uncheck_sets_checked_false_and_updates(self):
        # Arrange
        repo = _make_repo()
        item = _sample_item(name="Onion", checked=True)
        repo.get_by_id.return_value = item
        service = ShoppingListService(shopping_list_repository=repo)
        # Act
        service.uncheck(item.id)
        # Assert
        assert item.checked is False
        repo.update.assert_called_once()

    def test_uncheck_raises_when_item_not_found(self):
        # Arrange
        repo = _make_repo()
        repo.get_by_id.return_value = None
        service = ShoppingListService(shopping_list_repository=repo)
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            service.uncheck(str(uuid.uuid4()))
        assert "was not found" in str(exc.value.errors)


class TestShoppingListServiceDelete:

    def test_delete_calls_repository_with_correct_id(self):
        # Arrange
        repo = _make_repo()
        service = ShoppingListService(shopping_list_repository=repo)
        item_id = str(uuid.uuid4())
        # Act
        service.delete(item_id)
        # Assert
        repo.delete.assert_called_once_with(item_id=item_id)


class TestShoppingListServiceClear:

    def test_clear_calls_repository_clear(self):
        # Arrange
        repo = _make_repo()
        service = ShoppingListService(shopping_list_repository=repo)
        # Act
        service.clear()
        # Assert
        repo.clear.assert_called_once()
