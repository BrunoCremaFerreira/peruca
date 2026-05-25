"""
SQLite Repository Integration Tests

These tests exercise the SQLite repositories against a real on-disk database
(path provided by the integration_db_path fixture) and do NOT require Ollama.
"""

import uuid

import pytest

from domain.entities import ShoppingListItem, User
from infra.data.sqlite.sqlite_shopping_list_repository import SqliteShoppingListRepository
from infra.data.sqlite.sqlite_user_repository import SqliteUserRepository


pytestmark = pytest.mark.integration


# ======================================================
# Fixtures
# ======================================================

@pytest.fixture
def user_repo(integration_db_path):
    return SqliteUserRepository(db_path=f"sqlite://{integration_db_path}")


@pytest.fixture
def shopping_repo(integration_db_path):
    return SqliteShoppingListRepository(db_path=f"sqlite://{integration_db_path}")


def _make_user(external_id: str = None, name: str = "Alice") -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=external_id or uid, name=name, summary="")


def _make_item(name: str = "leite", quantity: float = 1.0) -> ShoppingListItem:
    return ShoppingListItem(id=str(uuid.uuid4()), name=name, quantity=quantity)


# ======================================================
# SqliteUserRepository
# ======================================================

class TestSqliteUserRepositoryStartup:

    def test_user_repository_startup__fresh_db__admin_user_is_created_automatically(self, user_repo):
        # _startup calls _create_table and inserts Admin user when table is empty
        all_users = user_repo.get_all()

        assert len(all_users) >= 1, "Expected at least the Admin user to exist after startup"
        admin_users = [u for u in all_users if u.name == "Admin"]
        assert len(admin_users) == 1, f"Expected exactly one Admin user, found: {admin_users}"


class TestSqliteUserRepositoryAdd:

    def test_user_repository_add__valid_user__user_is_retrievable_by_external_id(self, user_repo):
        # Arrange
        user = _make_user(external_id="ext-001", name="Bruno")

        # Act
        user_repo.add(user)
        found = user_repo.get_by_external_id("ext-001")

        # Assert
        assert found is not None
        assert found.external_id == "ext-001"
        assert found.name == "Bruno"

    def test_user_repository_add__duplicate_external_id__raises_integrity_error(self, user_repo):
        import sqlite3

        # Arrange
        user_a = _make_user(external_id="ext-dup")
        user_b = _make_user(external_id="ext-dup")

        # Act & Assert
        user_repo.add(user_a)
        with pytest.raises(sqlite3.IntegrityError):
            user_repo.add(user_b)


class TestSqliteUserRepositoryGetByExternalId:

    def test_user_repository_get_by_external_id__existing_user__returns_user(self, user_repo):
        # Arrange
        user = _make_user(external_id="ext-get-1", name="Carlos")
        user_repo.add(user)

        # Act
        result = user_repo.get_by_external_id("ext-get-1")

        # Assert
        assert result is not None
        assert result.name == "Carlos"

    def test_user_repository_get_by_external_id__nonexistent_user__returns_none(self, user_repo):
        # Act
        result = user_repo.get_by_external_id("does-not-exist-xyz")

        # Assert
        assert result is None


# ======================================================
# SqliteShoppingListRepository
# ======================================================

class TestSqliteShoppingListRepositoryAdd:

    def test_shopping_list_repository_add__valid_item__item_is_retrievable(self, shopping_repo):
        # Arrange
        item = _make_item(name="ovos")

        # Act
        shopping_repo.add(item)
        found = shopping_repo.get_by_name("ovos")

        # Assert
        assert found is not None
        assert found.name == "ovos"

    def test_shopping_list_repository_add__duplicate_name__raises_integrity_error(self, shopping_repo):
        import sqlite3

        # Arrange
        item_a = _make_item(name="leite")
        item_b = _make_item(name="leite")

        # Act & Assert
        shopping_repo.add(item_a)
        with pytest.raises(sqlite3.IntegrityError):
            shopping_repo.add(item_b)


class TestSqliteShoppingListRepositoryGetByName:

    def test_shopping_list_repository_get_by_name__existing_item__returns_item(self, shopping_repo):
        # Arrange
        item = _make_item(name="pão")
        shopping_repo.add(item)

        # Act
        found = shopping_repo.get_by_name("pão")

        # Assert
        assert found is not None
        assert found.name == "pão"

    def test_shopping_list_repository_get_by_name__nonexistent_item__returns_none(self, shopping_repo):
        # Act
        result = shopping_repo.get_by_name("item-que-nao-existe")

        # Assert
        assert result is None

    def test_shopping_list_repository_get_by_name__case_insensitive__returns_item(self, shopping_repo):
        # Arrange — name stored in mixed case
        item = _make_item(name="Arroz")
        shopping_repo.add(item)

        # Act — query with different case
        found = shopping_repo.get_by_name("ARROZ")

        # Assert
        assert found is not None
        assert found.name == "Arroz"


class TestSqliteShoppingListRepositoryGetAll:

    def test_shopping_list_repository_get_all__empty_list__returns_empty(self, shopping_repo):
        # Act
        result = shopping_repo.get_all()

        # Assert
        assert result == []

    def test_shopping_list_repository_get_all__multiple_items__returns_all(self, shopping_repo):
        # Arrange
        items = [_make_item(name=n) for n in ["feijão", "sal", "óleo"]]
        for item in items:
            shopping_repo.add(item)

        # Act
        result = shopping_repo.get_all()

        # Assert
        result_names = {r.name for r in result}
        assert {"feijão", "sal", "óleo"}.issubset(result_names)


class TestSqliteShoppingListRepositoryDelete:

    def test_shopping_list_repository_delete__existing_item__item_is_removed(self, shopping_repo):
        # Arrange
        item = _make_item(name="café")
        shopping_repo.add(item)
        assert shopping_repo.get_by_name("café") is not None

        # Act
        shopping_repo.delete(item.id)

        # Assert
        assert shopping_repo.get_by_name("café") is None

    def test_shopping_list_repository_delete__nonexistent_id__no_exception(self, shopping_repo):
        # Act & Assert — deleting a non-existent id should not raise
        shopping_repo.delete(str(uuid.uuid4()))


class TestSqliteShoppingListRepositoryClear:

    def test_shopping_list_repository_clear__list_with_items__all_items_removed(self, shopping_repo):
        # Arrange
        for name in ["maçã", "banana", "uva"]:
            shopping_repo.add(_make_item(name=name))
        assert len(shopping_repo.get_all()) >= 3

        # Act
        shopping_repo.clear()

        # Assert
        assert shopping_repo.get_all() == []

    def test_shopping_list_repository_clear__empty_list__no_exception(self, shopping_repo):
        # Act & Assert — clearing an already empty list should not raise
        shopping_repo.clear()
        assert shopping_repo.get_all() == []


class TestSqliteShoppingListRepositoryUpdateBug:
    """
    The update method has a bug: it sets when_created instead of when_updated.
    This test detects the bug — it FAILS when the bug is present and PASSES when fixed.
    """

    def test_shopping_list_repository_update__update_quantity__quantity_is_changed_in_db(
        self, shopping_repo
    ):
        # Arrange
        original_item = _make_item(name="manteiga", quantity=1.0)
        shopping_repo.add(original_item)

        # Mutate
        updated_item = ShoppingListItem(
            id=original_item.id,
            name=original_item.name,
            quantity=5.0,
            when_created=original_item.when_created,
        )

        # Act
        shopping_repo.update(updated_item)

        # Assert — quantity must be updated in the database
        found = shopping_repo.get_by_name("manteiga")
        assert found is not None
        assert found.quantity == 5.0, (
            f"Expected quantity=5.0 after update but got {found.quantity}. "
            "Bug in SqliteShoppingListRepository.update: sets when_created instead of when_updated."
        )

    def test_shopping_list_repository_update__update_name__name_is_changed_in_db(
        self, shopping_repo
    ):
        # Arrange
        original_item = _make_item(name="iogurte")
        shopping_repo.add(original_item)

        # Mutate
        updated_item = ShoppingListItem(
            id=original_item.id,
            name="iogurte grego",
            quantity=original_item.quantity,
            when_created=original_item.when_created,
        )

        # Act
        shopping_repo.update(updated_item)

        # Assert — name must be updated in the database
        found = shopping_repo.get_by_name("iogurte grego")
        assert found is not None, (
            "Item with updated name 'iogurte grego' was not found in DB. "
            "Bug in SqliteShoppingListRepository.update."
        )
