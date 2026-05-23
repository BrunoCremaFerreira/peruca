import uuid
from unittest.mock import MagicMock
import pytest

from application.appservices.shopping_list_app_service import ShoppingListAppService
from application.appservices.view_models import ShoppingListCleanType, ShoppingListItemResponse
from domain.commands import ShoppingListItemAdd, ShoppingListItemUpdate
from domain.entities import ShoppingListItem
from domain.exceptions import EmptyParamValidationError, ValidationError


"""
ShoppingListAppService Unit Tests
"""


def _sample_item(name="Bread", quantity=1.0, checked=False) -> ShoppingListItem:
    return ShoppingListItem(id=str(uuid.uuid4()), name=name, quantity=quantity, checked=checked)


def _make_app_service(repo=None, service=None):
    if repo is None:
        repo = MagicMock()
        repo.get_all.return_value = []
        repo.get_by_id.return_value = None
    if service is None:
        service = MagicMock()
    return ShoppingListAppService(
        shopping_list_repository=repo,
        shopping_list_service=service,
    )


class TestShoppingListAppServiceGetById:

    def test_get_by_id_returns_mapped_response(self):
        # Arrange
        item = _sample_item("Milk")
        repo = MagicMock()
        repo.get_by_id.return_value = item
        app_service = _make_app_service(repo=repo)
        # Act
        result = app_service.get_by_id(item.id)
        # Assert
        assert isinstance(result, ShoppingListItemResponse)
        assert result.name == "Milk"

    def test_get_by_id_returns_none_when_not_found(self):
        # Arrange
        repo = MagicMock()
        repo.get_by_id.return_value = None
        app_service = _make_app_service(repo=repo)
        # Act
        result = app_service.get_by_id(str(uuid.uuid4()))
        # Assert
        assert result is None

    def test_get_by_id_raises_when_id_is_empty(self):
        # Arrange
        app_service = _make_app_service()
        # Act / Assert
        with pytest.raises(EmptyParamValidationError):
            app_service.get_by_id("")

    def test_get_by_id_raises_when_id_is_whitespace(self):
        # Arrange
        app_service = _make_app_service()
        # Act / Assert
        with pytest.raises(EmptyParamValidationError):
            app_service.get_by_id("   ")


class TestShoppingListAppServiceGetAll:

    def test_get_all_returns_list_of_responses(self):
        # Arrange
        repo = MagicMock()
        repo.get_all.return_value = [_sample_item("Apple"), _sample_item("Banana")]
        app_service = _make_app_service(repo=repo)
        # Act
        result = app_service.get_all()
        # Assert
        assert len(result) == 2
        assert all(isinstance(r, ShoppingListItemResponse) for r in result)

    def test_get_all_returns_empty_list_when_empty(self):
        # Arrange
        repo = MagicMock()
        repo.get_all.return_value = []
        app_service = _make_app_service(repo=repo)
        # Act
        result = app_service.get_all()
        # Assert
        assert result == []


class TestShoppingListAppServiceAdd:

    def test_add_delegates_to_domain_service(self):
        # Arrange
        svc = MagicMock()
        app_service = _make_app_service(service=svc)
        cmd = ShoppingListItemAdd(name="Cheese", quantity=2)
        # Act
        app_service.add(cmd)
        # Assert
        svc.add.assert_called_once_with(item_add=cmd)


class TestShoppingListAppServiceUpdateQuantity:

    def test_update_quantity_delegates_to_domain_service(self):
        # Arrange
        svc = MagicMock()
        app_service = _make_app_service(service=svc)
        cmd = ShoppingListItemUpdate(id=str(uuid.uuid4()), name="Milk", quantity=3)
        # Act
        app_service.update_quantity(cmd)
        # Assert
        svc.update_quantity.assert_called_once_with(item=cmd)


class TestShoppingListAppServiceDelete:

    def test_delete_delegates_to_repository(self):
        # Arrange
        repo = MagicMock()
        app_service = _make_app_service(repo=repo)
        item_id = str(uuid.uuid4())
        # Act
        app_service.delete(item_id)
        # Assert
        repo.delete.assert_called_once_with(item_id=item_id)


class TestShoppingListAppServiceClear:

    def test_clear_all_deletes_every_item(self):
        # Arrange
        repo = MagicMock()
        items = [_sample_item("A", checked=False), _sample_item("B", checked=True)]
        repo.get_all.return_value = items
        app_service = _make_app_service(repo=repo)
        # Act
        app_service.clear(ShoppingListCleanType.ALL)
        # Assert — every item is deleted
        assert repo.delete.call_count == 2

    def test_clear_checked_deletes_only_unchecked_items(self):
        # Arrange
        repo = MagicMock()
        unchecked = _sample_item("Yogurt", checked=False)
        checked_item = _sample_item("Butter", checked=True)
        repo.get_all.return_value = [unchecked, checked_item]
        app_service = _make_app_service(repo=repo)
        # Act
        app_service.clear(ShoppingListCleanType.CHECKED)
        # Assert — only the unchecked item is deleted (checked ones are kept)
        repo.delete.assert_called_once_with(item_id=unchecked.id)

    def test_clear_all_with_empty_list_does_not_call_delete(self):
        # Arrange
        repo = MagicMock()
        repo.get_all.return_value = []
        app_service = _make_app_service(repo=repo)
        # Act
        app_service.clear(ShoppingListCleanType.ALL)
        # Assert
        repo.delete.assert_not_called()


class TestShoppingListAppServiceCheck:

    def test_check_delegates_to_domain_service(self):
        # Arrange
        svc = MagicMock()
        app_service = _make_app_service(service=svc)
        item_id = str(uuid.uuid4())
        # Act
        app_service.check(item_id)
        # Assert
        svc.check.assert_called_once_with(item_id=item_id)


class TestShoppingListAppServiceUncheck:

    def test_uncheck_delegates_to_domain_service(self):
        # Arrange
        svc = MagicMock()
        app_service = _make_app_service(service=svc)
        item_id = str(uuid.uuid4())
        # Act
        app_service.uncheck(item_id)
        # Assert
        svc.uncheck.assert_called_once_with(item_id=item_id)
