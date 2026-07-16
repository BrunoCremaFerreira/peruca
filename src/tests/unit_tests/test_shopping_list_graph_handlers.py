import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from application.graphs.shopping_list_graph import ShoppingListGraph
from domain.entities import GraphInvokeRequest, ShoppingListItem, User
from domain.exceptions import ValidationError
from domain.services.shopping_list_service import ShoppingListService


"""
ShoppingListGraph handler unit tests.

Covers the following behaviour changes (TDD — written before implementation):

  1. _handle_add_item must return a string containing "Adicionado:" instead of
     the English "Items Add:".

  2. _handle_delete_item must return a string containing "Removido:" instead of
     the English "Items Removeds:".

  3. _handle_clear_items must return a Portuguese string instead of the English
     "The Shopping List was cleared and all items was removed".
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph(disambiguation_service=None) -> ShoppingListGraph:
    """
    Build a ShoppingListGraph with all external dependencies mocked.
    load_prompt is patched to avoid filesystem access.

    The mocked service delegates find_items_by_name to a real (pure)
    ShoppingListService instance so handlers can resolve item names, while the
    CRUD methods (add/delete/check/uncheck) stay MagicMocks for assertions.
    """
    llm_chat = MagicMock()
    shopping_list_service = MagicMock()
    shopping_list_service.get_by_name = MagicMock(return_value=None)
    shopping_list_service.get_all = MagicMock(return_value=[])
    _matcher = ShoppingListService(shopping_list_repository=MagicMock())
    shopping_list_service.find_items_by_name.side_effect = _matcher.find_items_by_name

    with patch.object(ShoppingListGraph, "load_prompt", return_value="{input}"):
        graph = ShoppingListGraph(
            llm_chat=llm_chat,
            shopping_list_service=shopping_list_service,
            disambiguation_service=disambiguation_service,
        )

    return graph


def _input(message="faça algo", user_id="user-1") -> GraphInvokeRequest:
    return GraphInvokeRequest(message=message, user=User(id=user_id))


def _sample_item(name="Leite", quantity=1.0) -> ShoppingListItem:
    return ShoppingListItem(
        id=str(uuid.uuid4()), name=name, quantity=quantity, checked=False
    )


# ---------------------------------------------------------------------------
# Mudanca 1 — _handle_add_item returns Portuguese string with "Adicionado:"
# ---------------------------------------------------------------------------


class TestHandleAddItemOutputLanguage:
    def test_handle_add_item__single_item__output_contains_adicionado(self):
        graph = _make_graph()
        graph.shopping_list_service.add_items.return_value = _add_result(
            added=[_add_cmd("leite", 1.0)]
        )
        # "leite,1" is the pipe-delimited format parsed by _parse_shopping_list_add
        state = {"output_add_item": "leite,1"}

        result = graph._handle_add_item(state)

        assert "Adicionado" in result["output_add_item"], (
            f"Expected 'Adicionado' in output, got: {result['output_add_item']!r}"
        )

    def test_handle_add_item__single_item__output_contains_item_name(self):
        graph = _make_graph()
        graph.shopping_list_service.add_items.return_value = _add_result(
            added=[_add_cmd("leite", 1.0)]
        )
        state = {"output_add_item": "leite,1"}

        result = graph._handle_add_item(state)

        assert "leite" in result["output_add_item"].lower()

    def test_handle_add_item__multiple_items__output_contains_adicionado(self):
        graph = _make_graph()
        graph.shopping_list_service.add_items.return_value = _add_result(
            added=[_add_cmd("leite", 1.0), _add_cmd("arroz", 2.0)]
        )
        state = {"output_add_item": "leite,1|arroz,2"}

        result = graph._handle_add_item(state)

        assert "Adicionado" in result["output_add_item"]

    def test_handle_add_item__single_item__does_not_return_english_prefix(self):
        """Regression: previous implementation used 'Items Add:' prefix."""
        graph = _make_graph()
        graph.shopping_list_service.add_items.return_value = _add_result(
            added=[_add_cmd("leite", 1.0)]
        )
        state = {"output_add_item": "leite,1"}

        result = graph._handle_add_item(state)

        assert "Items Add" not in result["output_add_item"], (
            "English prefix 'Items Add' must be replaced with Portuguese"
        )

    def test_handle_add_item__service_called_once_with_whole_batch(self):
        """The write path is a SINGLE batch call, never one add per item."""
        graph = _make_graph()
        graph.shopping_list_service.add_items.return_value = _add_result(
            added=[_add_cmd("leite", 1.0), _add_cmd("arroz", 2.0)]
        )
        state = {"output_add_item": "leite,1|arroz,2"}

        graph._handle_add_item(state)

        graph.shopping_list_service.add_items.assert_called_once()
        graph.shopping_list_service.add.assert_not_called()
        batch = graph.shopping_list_service.add_items.call_args[0][0]
        assert [item.name for item in batch] == ["leite", "arroz"]

    def test_handle_add_item__validation_error__returns_error_in_output(self):
        graph = _make_graph()
        graph.shopping_list_service.add_items.side_effect = ValidationError(
            errors=["Name is required"]
        )
        state = {"output_add_item": "leite,1"}

        result = graph._handle_add_item(state)

        # Should not raise; error surfaced in the output key as a STRING
        assert "output_add_item" in result
        assert isinstance(result["output_add_item"], str)


# ---------------------------------------------------------------------------
# Mudanca 2 — _handle_delete_item returns Portuguese string with "Removido:"
# ---------------------------------------------------------------------------


class TestHandleDeleteItemOutputLanguage:
    def test_handle_delete_item__existing_item__output_contains_removido(self):
        graph = _make_graph()
        item = _sample_item(name="leite")
        graph.shopping_list_service.get_all.return_value = [item]
        state = {"output_delete_item": "leite,1"}

        result = graph._handle_delete_item(state)

        assert "Removido" in result["output_delete_item"], (
            f"Expected 'Removido' in output, got: {result['output_delete_item']!r}"
        )

    def test_handle_delete_item__existing_item__output_contains_item_name(self):
        graph = _make_graph()
        item = _sample_item(name="leite")
        graph.shopping_list_service.get_all.return_value = [item]
        state = {"output_delete_item": "leite,1"}

        result = graph._handle_delete_item(state)

        assert "leite" in result["output_delete_item"].lower()

    def test_handle_delete_item__existing_item__does_not_return_english_prefix(self):
        """Regression: previous implementation used 'Items Removeds:' prefix."""
        graph = _make_graph()
        item = _sample_item(name="leite")
        graph.shopping_list_service.get_all.return_value = [item]
        state = {"output_delete_item": "leite,1"}

        result = graph._handle_delete_item(state)

        assert "Items Removeds" not in result["output_delete_item"], (
            "English prefix 'Items Removeds' must be replaced with Portuguese"
        )

    def test_handle_delete_item__item_not_in_list__returns_portuguese_message(self):
        graph = _make_graph()
        graph.shopping_list_service.get_all.return_value = []
        state = {"output_delete_item": "leite,1"}

        result = graph._handle_delete_item(state)

        # When list is empty the handler returns early; result must be in Portuguese
        output_value = result.get("output_delete_item", "")
        assert "The list has no items" not in output_value, (
            "English fallback message must be replaced with Portuguese"
        )

    def test_handle_delete_item__calls_service_delete_for_matched_item(self):
        graph = _make_graph()
        item = _sample_item(name="leite")
        graph.shopping_list_service.get_all.return_value = [item]
        state = {"output_delete_item": "leite,1"}

        graph._handle_delete_item(state)

        graph.shopping_list_service.delete.assert_called_once_with(item.id)


# ---------------------------------------------------------------------------
# Mudanca 3 — _handle_clear_items returns a Portuguese string
# ---------------------------------------------------------------------------


class TestHandleClearItemsOutputLanguage:
    def test_handle_clear_items__calls_service_clear(self):
        graph = _make_graph()

        graph._handle_clear_items({})

        graph.shopping_list_service.clear.assert_called_once()

    def test_handle_clear_items__output_is_in_portuguese(self):
        graph = _make_graph()

        result = graph._handle_clear_items({})

        output = result.get("output_clear_items", "")
        assert isinstance(output, str)
        # Must contain at least one Portuguese keyword
        portuguese_keywords = [
            "lista",
            "itens",
            "removidos",
            "limpa",
            "apagados",
            "vazia",
        ]
        assert any(kw in output.lower() for kw in portuguese_keywords), (
            f"Expected a Portuguese string, got: {output!r}"
        )

    def test_handle_clear_items__does_not_return_english_message(self):
        """Regression: previous implementation returned an English string."""
        graph = _make_graph()

        result = graph._handle_clear_items({})

        output = result.get("output_clear_items", "")
        assert "The Shopping List was cleared" not in output, (
            "English message must be replaced with a Portuguese equivalent"
        )


# ---------------------------------------------------------------------------
# Mudanca 4 — _handle_check_item lookup by name, calls service.check(), Portuguese output
# ---------------------------------------------------------------------------


class TestHandleCheckItemOutput:
    def test_handle_check_item__single_item_name__calls_service_get_all(self):
        # Arrange
        graph = _make_graph()
        graph.shopping_list_service.get_all = MagicMock(return_value=[])
        state = {"output_check_item": "leite"}
        # Act
        graph._handle_check_item(state)
        # Assert
        graph.shopping_list_service.get_all.assert_called_once()

    def test_handle_check_item__item_found_by_name__calls_service_check_with_item_id(
        self,
    ):
        # Arrange
        graph = _make_graph()
        item = _sample_item(name="leite")
        graph.shopping_list_service.get_all = MagicMock(return_value=[item])
        graph.shopping_list_service.check = MagicMock()
        state = {"output_check_item": "leite"}
        # Act
        graph._handle_check_item(state)
        # Assert
        graph.shopping_list_service.check.assert_called_once_with(item.id)

    def test_handle_check_item__item_found__output_contains_marcado(self):
        # Arrange
        graph = _make_graph()
        item = _sample_item(name="leite")
        graph.shopping_list_service.get_all = MagicMock(return_value=[item])
        graph.shopping_list_service.check = MagicMock()
        state = {"output_check_item": "leite"}
        # Act
        result = graph._handle_check_item(state)
        # Assert
        output = result.get("output_check_item", "")
        assert "Marcado" in output, f"Expected 'Marcado' in output, got: {output!r}"

    def test_handle_check_item__item_found__output_contains_item_name(self):
        # Arrange
        graph = _make_graph()
        item = _sample_item(name="leite")
        graph.shopping_list_service.get_all = MagicMock(return_value=[item])
        graph.shopping_list_service.check = MagicMock()
        state = {"output_check_item": "leite"}
        # Act
        result = graph._handle_check_item(state)
        # Assert
        output = result.get("output_check_item", "")
        assert "leite" in output.lower()

    def test_handle_check_item__item_not_found_in_list__output_is_in_portuguese(self):
        # Arrange — empty list, item cannot be matched
        graph = _make_graph()
        graph.shopping_list_service.get_all = MagicMock(return_value=[])
        graph.shopping_list_service.check = MagicMock()
        state = {"output_check_item": "leite"}
        # Act
        result = graph._handle_check_item(state)
        # Assert — output must be in Portuguese, not English
        output = result.get("output_check_item", "")
        portuguese_keywords = ["lista", "vazia", "encontrado", "não", "nenhum", "item"]
        assert any(kw in output.lower() for kw in portuguese_keywords), (
            f"Expected a Portuguese fallback message, got: {output!r}"
        )

    def test_handle_check_item__does_not_return_english_prefix(self):
        # Arrange
        graph = _make_graph()
        item = _sample_item(name="leite")
        graph.shopping_list_service.get_all = MagicMock(return_value=[item])
        graph.shopping_list_service.check = MagicMock()
        state = {"output_check_item": "leite"}
        # Act
        result = graph._handle_check_item(state)
        # Assert — regression: stub returned "Items Checked: ..."
        output = result.get("output_check_item", "")
        assert "Items Checked" not in output, (
            "English prefix 'Items Checked' must be replaced with Portuguese"
        )

    def test_handle_check_item__multiple_items__calls_check_for_each(self):
        # Arrange
        graph = _make_graph()
        item_leite = _sample_item(name="leite")
        item_ovos = ShoppingListItem(
            id="ovos-id", name="ovos", quantity=1.0, checked=False
        )
        graph.shopping_list_service.get_all = MagicMock(
            return_value=[item_leite, item_ovos]
        )
        graph.shopping_list_service.check = MagicMock()
        state = {"output_check_item": "leite|ovos"}
        # Act
        graph._handle_check_item(state)
        # Assert — check must be called once for each item in the payload
        assert graph.shopping_list_service.check.call_count == 2
        graph.shopping_list_service.check.assert_any_call(item_leite.id)
        graph.shopping_list_service.check.assert_any_call(item_ovos.id)

    def test_handle_check_item__case_insensitive_match(self):
        # Arrange — payload in uppercase, list item in lowercase
        graph = _make_graph()
        item = _sample_item(name="leite")
        graph.shopping_list_service.get_all = MagicMock(return_value=[item])
        graph.shopping_list_service.check = MagicMock()
        state = {"output_check_item": "LEITE"}
        # Act
        graph._handle_check_item(state)
        # Assert — match must be case-insensitive
        graph.shopping_list_service.check.assert_called_once_with(item.id)


# ---------------------------------------------------------------------------
# Mudanca 5 — _handle_uncheck_item lookup by name, calls service.uncheck(), Portuguese output
# ---------------------------------------------------------------------------


class TestHandleUncheckItemOutput:
    def test_handle_uncheck_item__item_found_by_name__calls_service_uncheck_with_item_id(
        self,
    ):
        # Arrange
        graph = _make_graph()
        item = _sample_item(name="leite")
        graph.shopping_list_service.get_all = MagicMock(return_value=[item])
        graph.shopping_list_service.uncheck = MagicMock()
        state = {"output_uncheck_item": "leite"}
        # Act
        graph._handle_uncheck_item(state)
        # Assert
        graph.shopping_list_service.uncheck.assert_called_once_with(item.id)

    def test_handle_uncheck_item__item_found__output_contains_desmarcado(self):
        # Arrange
        graph = _make_graph()
        item = _sample_item(name="leite")
        graph.shopping_list_service.get_all = MagicMock(return_value=[item])
        graph.shopping_list_service.uncheck = MagicMock()
        state = {"output_uncheck_item": "leite"}
        # Act
        result = graph._handle_uncheck_item(state)
        # Assert
        output = result.get("output_uncheck_item", "")
        assert "Desmarcado" in output, (
            f"Expected 'Desmarcado' in output, got: {output!r}"
        )

    def test_handle_uncheck_item__item_found__output_contains_item_name(self):
        # Arrange
        graph = _make_graph()
        item = _sample_item(name="leite")
        graph.shopping_list_service.get_all = MagicMock(return_value=[item])
        graph.shopping_list_service.uncheck = MagicMock()
        state = {"output_uncheck_item": "leite"}
        # Act
        result = graph._handle_uncheck_item(state)
        # Assert
        output = result.get("output_uncheck_item", "")
        assert "leite" in output.lower()

    def test_handle_uncheck_item__item_not_found_in_list__output_is_in_portuguese(self):
        # Arrange — empty list, item cannot be matched
        graph = _make_graph()
        graph.shopping_list_service.get_all = MagicMock(return_value=[])
        graph.shopping_list_service.uncheck = MagicMock()
        state = {"output_uncheck_item": "leite"}
        # Act
        result = graph._handle_uncheck_item(state)
        # Assert — output must be in Portuguese, not English
        output = result.get("output_uncheck_item", "")
        portuguese_keywords = ["lista", "vazia", "encontrado", "não", "nenhum", "item"]
        assert any(kw in output.lower() for kw in portuguese_keywords), (
            f"Expected a Portuguese fallback message, got: {output!r}"
        )

    def test_handle_uncheck_item__does_not_return_english_prefix(self):
        # Arrange
        graph = _make_graph()
        item = _sample_item(name="leite")
        graph.shopping_list_service.get_all = MagicMock(return_value=[item])
        graph.shopping_list_service.uncheck = MagicMock()
        state = {"output_uncheck_item": "leite"}
        # Act
        result = graph._handle_uncheck_item(state)
        # Assert — regression: stub returned "Items Unchecked: ..."
        output = result.get("output_uncheck_item", "")
        assert "Items Unchecked" not in output, (
            "English prefix 'Items Unchecked' must be replaced with Portuguese"
        )

    def test_handle_uncheck_item__multiple_items__calls_uncheck_for_each(self):
        # Arrange
        graph = _make_graph()
        item_leite = _sample_item(name="leite")
        item_ovos = ShoppingListItem(
            id="ovos-id", name="ovos", quantity=1.0, checked=True
        )
        graph.shopping_list_service.get_all = MagicMock(
            return_value=[item_leite, item_ovos]
        )
        graph.shopping_list_service.uncheck = MagicMock()
        state = {"output_uncheck_item": "leite|ovos"}
        # Act
        graph._handle_uncheck_item(state)
        # Assert — uncheck must be called once for each item in the payload
        assert graph.shopping_list_service.uncheck.call_count == 2
        graph.shopping_list_service.uncheck.assert_any_call(item_leite.id)
        graph.shopping_list_service.uncheck.assert_any_call(item_ovos.id)

    def test_handle_uncheck_item__case_insensitive_match(self):
        # Arrange — payload in uppercase, list item in lowercase
        graph = _make_graph()
        item = _sample_item(name="leite")
        graph.shopping_list_service.get_all = MagicMock(return_value=[item])
        graph.shopping_list_service.uncheck = MagicMock()
        state = {"output_uncheck_item": "LEITE"}
        # Act
        graph._handle_uncheck_item(state)
        # Assert — match must be case-insensitive
        graph.shopping_list_service.uncheck.assert_called_once_with(item.id)


# ---------------------------------------------------------------------------
# Bug 2 — _handle_delete_item must strip whitespace from extracted item names
#
# _handle_check_item already uses .strip() when splitting by "|"; _handle_delete_item
# does not. When the LLM returns payloads like "cerveja,1 | carvão,1" the extra
# spaces around "|" cause the name comparison to fail and items are never deleted.
# ---------------------------------------------------------------------------


class TestHandleDeleteItemWhitespaceTolerance:
    def test_handle_delete_item__payload_with_spaces_around_pipe__both_items_deleted(
        self,
    ):
        """
        Payload "cerveja,1 | carvão,1" — spaces surround the pipe separator.
        After splitting by "|" the fragments are "cerveja,1 " and " carvão,1".
        Without .strip() on the extracted name, " carvão" != "carvão" and the
        second item is never deleted.

        Expected: shopping_list_service.delete is called exactly twice (once per item).
        FAILS with current implementation (no .strip() on name after split by ",").
        """
        # Arrange
        graph = _make_graph()
        item_cerveja = _sample_item(name="cerveja")
        item_carvao = ShoppingListItem(
            id="carvao-id", name="carvão", quantity=1.0, checked=False
        )
        graph.shopping_list_service.get_all = MagicMock(
            return_value=[item_cerveja, item_carvao]
        )
        graph.shopping_list_service.delete = MagicMock()
        state = {"output_delete_item": "cerveja,1 | carvão,1"}
        # Act
        graph._handle_delete_item(state)
        # Assert — both items must have been deleted
        assert graph.shopping_list_service.delete.call_count == 2, (
            f"Expected delete called 2 times, got {graph.shopping_list_service.delete.call_count}. "
            "Likely cause: missing .strip() on item name extracted from pipe-split payload."
        )
        graph.shopping_list_service.delete.assert_any_call(item_cerveja.id)
        graph.shopping_list_service.delete.assert_any_call(item_carvao.id)

    def test_handle_delete_item__payload_with_leading_space_in_name__item_matched_and_deleted(
        self,
    ):
        """
        Payload " leite,1" — leading space before the item name.
        Without .strip() on the name extracted after split(",", 1)[0], the
        comparison " leite".lower() == "leite".lower() is False.

        Expected: shopping_list_service.delete is called exactly once.
        FAILS with current implementation.
        """
        # Arrange
        graph = _make_graph()
        item_leite = _sample_item(name="leite")
        graph.shopping_list_service.get_all = MagicMock(return_value=[item_leite])
        graph.shopping_list_service.delete = MagicMock()
        state = {"output_delete_item": " leite,1"}
        # Act
        graph._handle_delete_item(state)
        # Assert — item must have been deleted despite the leading space
        graph.shopping_list_service.delete.assert_called_once_with(item_leite.id)


# ---------------------------------------------------------------------------
# Bug 3 — handlers must never leak raw ShoppingListItem entities into the state.
#
# _handle_list_items and _handle_delete_item currently place
# List[ShoppingListItem] under "output_list_items". _handle_final_response then
# joins/echoes whatever it finds, serialising the dataclasses into the API
# response (e.g. "ShoppingListItem(id=..., name='leite', ...)"). The graph state
# must only carry human-readable strings.
# ---------------------------------------------------------------------------


class TestHandleListItemsOutputType:
    def test_handle_list_items__with_items__output_is_str_not_list(self):
        """
        output_list_items must be a human-readable string, never a
        List[ShoppingListItem]. FAILS with current implementation which
        returns the raw entity list.
        """
        # Arrange
        graph = _make_graph()
        item_leite = _sample_item(name="leite")
        item_arroz = ShoppingListItem(
            id="arroz-id", name="arroz", quantity=2.0, checked=False
        )
        graph.shopping_list_service.get_all = MagicMock(
            return_value=[item_leite, item_arroz]
        )
        # Act
        result = graph._handle_list_items({})
        # Assert — must be a string, not a list of entities
        assert isinstance(result["output_list_items"], str), (
            f"Expected str, got {type(result['output_list_items']).__name__}"
        )
        assert not isinstance(result["output_list_items"], list)

    def test_handle_list_items__with_items__output_contains_item_names(self):
        # Arrange
        graph = _make_graph()
        item_leite = _sample_item(name="leite")
        item_arroz = ShoppingListItem(
            id="arroz-id", name="arroz", quantity=2.0, checked=False
        )
        graph.shopping_list_service.get_all = MagicMock(
            return_value=[item_leite, item_arroz]
        )
        # Act
        result = graph._handle_list_items({})
        # Assert
        output = result["output_list_items"]
        assert "leite" in output.lower()
        assert "arroz" in output.lower()

    def test_handle_list_items__with_items__does_not_leak_entity_repr(self):
        """Regression: the raw dataclass repr must never reach the output."""
        # Arrange
        graph = _make_graph()
        item_leite = _sample_item(name="leite")
        graph.shopping_list_service.get_all = MagicMock(return_value=[item_leite])
        # Act
        result = graph._handle_list_items({})
        # Assert
        assert "ShoppingListItem(" not in result["output_list_items"], (
            "Raw ShoppingListItem entity leaked into output_list_items"
        )


class TestHandleListItemsEmpty:
    def test_handle_list_items__empty_list__output_is_str(self):
        # Arrange
        graph = _make_graph()
        graph.shopping_list_service.get_all = MagicMock(return_value=[])
        # Act
        result = graph._handle_list_items({})
        # Assert
        assert isinstance(result["output_list_items"], str)
        assert not isinstance(result["output_list_items"], list)

    def test_handle_list_items__empty_list__output_is_in_portuguese(self):
        # Arrange
        graph = _make_graph()
        graph.shopping_list_service.get_all = MagicMock(return_value=[])
        # Act
        result = graph._handle_list_items({})
        # Assert
        output = result["output_list_items"]
        portuguese_keywords = ["vazia", "nenhum", "lista", "sem itens"]
        assert any(kw in output.lower() for kw in portuguese_keywords), (
            f"Expected a Portuguese message, got: {output!r}"
        )

    def test_handle_list_items__empty_list__does_not_return_english_message(self):
        """Regression: previous implementation returned an English string."""
        # Arrange
        graph = _make_graph()
        graph.shopping_list_service.get_all = MagicMock(return_value=[])
        # Act
        result = graph._handle_list_items({})
        # Assert
        assert "The Shopping List is empty" not in result["output_list_items"], (
            "English message must be replaced with a Portuguese equivalent"
        )


class TestHandleDeleteItemDoesNotLeakEntities:
    def test_handle_delete_item__does_not_leak_entity_list_into_state(self):
        """
        After deleting, the handler must not place a raw List[ShoppingListItem]
        under output_list_items. It may omit the key or carry a string.
        FAILS with current implementation which injects the entity list.
        """
        # Arrange
        graph = _make_graph()
        item_leite = _sample_item(name="leite")
        graph.shopping_list_service.get_all = MagicMock(return_value=[item_leite])
        graph.shopping_list_service.delete = MagicMock()
        state = {"output_delete_item": "leite,1"}
        # Act
        result = graph._handle_delete_item(state)
        # Assert — output_list_items must be absent or a string, never a list
        out_list = result.get("output_list_items")
        assert out_list is None or isinstance(out_list, str), (
            f"output_list_items must be None or str, got "
            f"{type(out_list).__name__}"
        )
        assert not isinstance(result.get("output_list_items"), list)

    def test_handle_delete_item__delete_output_remains_string_with_removido(self):
        # Arrange
        graph = _make_graph()
        item_leite = _sample_item(name="leite")
        graph.shopping_list_service.get_all = MagicMock(return_value=[item_leite])
        graph.shopping_list_service.delete = MagicMock()
        state = {"output_delete_item": "leite,1"}
        # Act
        result = graph._handle_delete_item(state)
        # Assert
        assert isinstance(result["output_delete_item"], str)
        assert "Removido" in result["output_delete_item"], (
            f"Expected 'Removido' in output, got: {result['output_delete_item']!r}"
        )


# ---------------------------------------------------------------------------
# Mudanca 6 — _handle_final_response must NOT prefix outputs with numbering.
#
# Today, with more than one non-null output, _handle_final_response joins them
# with f"{i + 1}. {s}" (lines ~92-93), producing "1. ...", "2. ...". This breaks
# the listing rendering (a listing already has its own hyphen bullets) and leaks
# numbering into the user-facing text. The combined output must contain no
# "1. " / "2. " prefixes, and the listing's own hyphen lines must stay intact.
# ---------------------------------------------------------------------------


class TestHandleFinalResponseNoNumbering:
    def test_final_response__multiple_outputs__no_numbered_prefix(self):
        """
        RED: with two non-null outputs the current implementation prefixes each
        with "1. " / "2. ". No line in the combined output may start with a
        numbered prefix.
        """
        graph = _make_graph()
        listing = "Aqui está sua lista de compras:\n- leite\n- arroz (2)"
        state = {
            "output_add_item": "Adicionado: leite",
            "output_list_items": listing,
        }

        result = graph._handle_final_response(state)

        output = result["output"]
        for line in output.splitlines():
            assert not line.startswith("1. "), (
                f"Numbered prefix leaked into final response: {line!r}"
            )
            assert not line.startswith("2. "), (
                f"Numbered prefix leaked into final response: {line!r}"
            )

    def test_final_response__multiple_outputs__listing_hyphen_lines_intact(self):
        """
        RED: the listing's own hyphen bullet lines must survive verbatim inside
        the combined output (they must not be turned into "1. - leite" etc.).
        """
        graph = _make_graph()
        listing = "Aqui está sua lista de compras:\n- leite\n- arroz (2)"
        state = {
            "output_add_item": "Adicionado: leite",
            "output_list_items": listing,
        }

        result = graph._handle_final_response(state)

        output = result["output"]
        assert "- leite" in output, (
            f"Listing hyphen line '- leite' missing from output: {output!r}"
        )
        assert "- arroz (2)" in output, (
            f"Listing hyphen line '- arroz (2)' missing from output: {output!r}"
        )


# ---------------------------------------------------------------------------
# Mudanca 7 — _handle_edit_item / _handle_not_recognized output in Portuguese,
# and _handle_add_item generic-exception fallback in Portuguese.
# ---------------------------------------------------------------------------


class TestHandleEditItemOutputLanguage:
    def test_handle_edit_item__does_not_return_english_prefix(self):
        """RED: stub currently returns 'Items Edited: ...'."""
        graph = _make_graph()
        state = {"output_edit_item": "leite"}

        result = graph._handle_edit_item(state)

        assert "Items Edited" not in result["output_edit_item"], (
            "English prefix 'Items Edited' must be replaced with Portuguese"
        )

    def test_handle_edit_item__output_is_in_portuguese(self):
        graph = _make_graph()
        state = {"output_edit_item": "leite"}

        result = graph._handle_edit_item(state)

        output = result["output_edit_item"]
        assert isinstance(output, str)
        portuguese_keywords = ["editar", "ainda", "sei", "não", "consigo"]
        assert any(kw in output.lower() for kw in portuguese_keywords), (
            f"Expected a Portuguese string, got: {output!r}"
        )


class TestHandleNotRecognizedOutputLanguage:
    def test_handle_not_recognized__does_not_return_english_message(self):
        """RED: stub currently returns 'Not Recognized Triggered'."""
        graph = _make_graph()

        result = graph._handle_not_recognized({})

        assert "Not Recognized" not in result["output_not_recognized"], (
            "English message 'Not Recognized' must be replaced with Portuguese"
        )

    def test_handle_not_recognized__output_is_in_portuguese(self):
        graph = _make_graph()

        result = graph._handle_not_recognized({})

        output = result["output_not_recognized"]
        assert isinstance(output, str)
        portuguese_keywords = ["entendi", "não", "lista", "compras"]
        assert any(kw in output.lower() for kw in portuguese_keywords), (
            f"Expected a Portuguese string, got: {output!r}"
        )


class TestHandleAddItemExceptionLanguage:
    def test_handle_add_item__generic_exception__does_not_return_english(self):
        """
        RED: when shopping_list_service.add_items raises a non-validation
        Exception the handler currently returns 'An internal error was ocurred'.
        The fallback message must be in Portuguese.
        """
        graph = _make_graph()
        graph.shopping_list_service.add_items.side_effect = Exception("boom")
        state = {"output_add_item": "leite,1"}

        result = graph._handle_add_item(state)

        assert "An internal error" not in result["output_add_item"], (
            "English error fallback must be replaced with Portuguese"
        )

    def test_handle_add_item__generic_exception__output_is_in_portuguese(self):
        graph = _make_graph()
        graph.shopping_list_service.add_items.side_effect = Exception("boom")
        state = {"output_add_item": "leite,1"}

        result = graph._handle_add_item(state)

        output = result["output_add_item"]
        assert isinstance(output, str)
        # Note: avoid "erro" here — it is a substring of the English "error",
        # which would falsely pass against "An internal error was ocurred".
        portuguese_keywords = ["problema", "tente", "novamente", "ocorreu", "interno"]
        assert any(kw in output.lower() for kw in portuguese_keywords), (
            f"Expected a Portuguese error message, got: {output!r}"
        )


# ---------------------------------------------------------------------------
# Bug 4 — _handle_final_response must tolerate non-string / empty state values.
#
# _classify_intent stores the raw classifier fields in the state
# (output_edit_item, output_check_item, ...). gemma sometimes returns one of
# them as a list (e.g. []) or an empty string. The old filter kept every value
# where ``e is not None``, so a list reached ``"\n\n".join(outputs)`` and blew
# up with "TypeError: sequence item 0: expected str instance, list found"
# (shopping_list_graph.py line 94), and empty strings polluted the reply with
# blank lines. The filter must keep only non-empty strings.
# ---------------------------------------------------------------------------


class TestHandleFinalResponseFiltersNonStrings:
    def test_final_response__list_value_in_state__does_not_raise_and_is_excluded(self):
        """A list value (e.g. output_check_item == []) must be filtered out, not
        joined — reproduces the TypeError at the join (line 94)."""
        graph = _make_graph()
        state = {
            "output_add_item": "Adicionado: ovos",
            "output_edit_item": [],  # gemma returned a list here
            "output_check_item": [],
        }

        result = graph._handle_final_response(state)

        assert isinstance(result["output"], str)
        assert result["output"] == "Adicionado: ovos"

    def test_final_response__empty_string_values__filtered_no_blank_lines(self):
        """Empty/whitespace strings must not pollute the reply with blank lines."""
        graph = _make_graph()
        state = {
            "output_add_item": "Adicionado: ovos",
            "output_edit_item": "",
            "output_delete_item": "   ",
            "output_check_item": "",
        }

        result = graph._handle_final_response(state)

        assert result["output"] == "Adicionado: ovos", (
            f"Empty values leaked blank lines: {result['output']!r}"
        )

    def test_final_response__all_empty_or_none__returns_empty_string_no_indexerror(self):
        """With nothing usable the node must return '' instead of raising
        IndexError on outputs[0]."""
        graph = _make_graph()
        state = {
            "output_add_item": None,
            "output_edit_item": "",
            "output_check_item": [],
        }

        result = graph._handle_final_response(state)

        assert result["output"] == ""


class TestHandleFinalResponseOnlyStrings:
    def test_final_response__after_list_items__output_is_str_without_entity_repr(self):
        """
        Short flow: _handle_list_items -> _handle_final_response. The final
        output must be a string with no leaked entity repr. FAILS today because
        _handle_list_items leaks the entity list, which _handle_final_response
        then serialises.
        """
        # Arrange
        graph = _make_graph()
        item_leite = _sample_item(name="leite")
        graph.shopping_list_service.get_all = MagicMock(return_value=[item_leite])
        # Act
        s1 = graph._handle_list_items({})
        final = graph._handle_final_response(s1)
        # Assert
        assert isinstance(final["output"], str)
        assert "ShoppingListItem(" not in final["output"], (
            "Raw ShoppingListItem entity leaked into the final response"
        )

    def test_final_response__after_delete_item__output_is_str_without_entity_repr(self):
        """
        Short flow: _handle_delete_item -> _handle_final_response. The final
        output must be a string with no leaked entity repr.
        """
        # Arrange
        graph = _make_graph()
        item_leite = _sample_item(name="leite")
        graph.shopping_list_service.get_all = MagicMock(return_value=[item_leite])
        graph.shopping_list_service.delete = MagicMock()
        # Act
        s1 = graph._handle_delete_item({"output_delete_item": "leite,1"})
        final = graph._handle_final_response(s1)
        # Assert
        assert isinstance(final["output"], str)
        assert "ShoppingListItem(" not in final["output"], (
            "Raw ShoppingListItem entity leaked into the final response"
        )


# ---------------------------------------------------------------------------
# Feature — non-literal resolution + disambiguation with state.
#
# Handlers resolve item names via shopping_list_service.find_items_by_name:
#   0 candidates -> "not found" (Portuguese), never a lying "Removido"
#   1 candidate  -> apply on the matched item.id
#   >1 candidates -> do NOT apply; store a pending disambiguation and ask.
# ---------------------------------------------------------------------------


def _two_carnes():
    panela = ShoppingListItem(id="p-id", name="Carne de panela", quantity=1.0)
    seca = ShoppingListItem(id="s-id", name="Carne seca", quantity=1.0)
    return panela, seca


class TestHandleDeleteItemResolution:
    def test_typo__resolves_and_deletes_matched_item(self):
        graph = _make_graph()
        crepom = ShoppingListItem(id="c-id", name="Crepom", quantity=1.0)
        graph.shopping_list_service.get_all.return_value = [crepom]
        graph.shopping_list_service.delete = MagicMock()
        state = {"output_delete_item": "grepom", "input": _input()}

        result = graph._handle_delete_item(state)

        graph.shopping_list_service.delete.assert_called_once_with("c-id")
        assert "Removido" in result["output_delete_item"]
        assert "Crepom" in result["output_delete_item"]

    def test_partial__resolves_and_deletes_matched_item(self):
        graph = _make_graph()
        item = ShoppingListItem(id="c-id", name="Carne de panela", quantity=1.0)
        graph.shopping_list_service.get_all.return_value = [item]
        graph.shopping_list_service.delete = MagicMock()
        state = {"output_delete_item": "panela", "input": _input()}

        result = graph._handle_delete_item(state)

        graph.shopping_list_service.delete.assert_called_once_with("c-id")
        assert "Removido" in result["output_delete_item"]

    def test_clean_term_passed_to_resolver__without_quantity(self):
        graph = _make_graph()
        item = ShoppingListItem(id="c-id", name="Crepom", quantity=1.0)
        graph.shopping_list_service.get_all.return_value = [item]
        graph.shopping_list_service.delete = MagicMock()
        state = {"output_delete_item": "crepom, 2", "input": _input()}

        graph._handle_delete_item(state)

        first_call_query = (
            graph.shopping_list_service.find_items_by_name.call_args_list[0][0][0]
        )
        assert first_call_query == "crepom"

    def test_no_match__does_not_delete_and_does_not_say_removido(self):
        graph = _make_graph()
        graph.shopping_list_service.get_all.return_value = [
            ShoppingListItem(id="x", name="Leite", quantity=1.0)
        ]
        graph.shopping_list_service.delete = MagicMock()
        state = {"output_delete_item": "chocolate", "input": _input()}

        result = graph._handle_delete_item(state)

        graph.shopping_list_service.delete.assert_not_called()
        out = result["output_delete_item"]
        assert "Removido" not in out
        # Portuguese "not found" message
        assert any(kw in out.lower() for kw in ["não encontr", "nao encontr"])

    def test_ambiguous__does_not_delete_asks_with_both_names_and_stores_pending(self):
        disambig = MagicMock()
        disambig.set_pending = AsyncMock()
        graph = _make_graph(disambiguation_service=disambig)
        panela, seca = _two_carnes()
        graph.shopping_list_service.get_all.return_value = [panela, seca]
        graph.shopping_list_service.delete = MagicMock()
        state = {
            "output_delete_item": "carne",
            "input": _input(message="remova a carne", user_id="user-42"),
        }

        result = graph._handle_delete_item(state)

        # Must not apply anything on an ambiguous match.
        graph.shopping_list_service.delete.assert_not_called()
        out = result["output_delete_item"]
        assert "Carne de panela" in out
        assert "Carne seca" in out
        assert "?" in out
        # Pending disambiguation stored for the user.
        disambig.set_pending.assert_called_once()
        stored_user_id = disambig.set_pending.call_args[0][0]
        stored_pending = disambig.set_pending.call_args[0][1]
        assert stored_user_id == "user-42"
        assert stored_pending.operation == "delete"
        assert {c.id for c in stored_pending.candidates} == {"p-id", "s-id"}

    def test_mixed_payload__applies_unambiguous_and_reports_not_found(self):
        graph = _make_graph()
        leite = ShoppingListItem(id="l-id", name="Leite", quantity=1.0)
        graph.shopping_list_service.get_all.return_value = [leite]
        graph.shopping_list_service.delete = MagicMock()
        state = {"output_delete_item": "leite|chocolate", "input": _input()}

        result = graph._handle_delete_item(state)

        graph.shopping_list_service.delete.assert_called_once_with("l-id")
        out = result["output_delete_item"]
        assert "Leite" in out
        assert any(kw in out.lower() for kw in ["não encontr", "nao encontr"])


class TestHandleCheckItemResolution:
    def test_typo__resolves_and_checks_matched_item(self):
        graph = _make_graph()
        crepom = ShoppingListItem(id="c-id", name="Crepom", quantity=1.0)
        graph.shopping_list_service.get_all.return_value = [crepom]
        graph.shopping_list_service.check = MagicMock()
        state = {"output_check_item": "grepom", "input": _input()}

        result = graph._handle_check_item(state)

        graph.shopping_list_service.check.assert_called_once_with("c-id")
        assert "Marcado" in result["output_check_item"]

    def test_ambiguous__does_not_check_and_stores_pending(self):
        disambig = MagicMock()
        disambig.set_pending = AsyncMock()
        graph = _make_graph(disambiguation_service=disambig)
        panela, seca = _two_carnes()
        graph.shopping_list_service.get_all.return_value = [panela, seca]
        graph.shopping_list_service.check = MagicMock()
        state = {"output_check_item": "carne", "input": _input(user_id="u9")}

        result = graph._handle_check_item(state)

        graph.shopping_list_service.check.assert_not_called()
        assert "?" in result["output_check_item"]
        disambig.set_pending.assert_called_once()
        assert disambig.set_pending.call_args[0][1].operation == "check"


class TestHandleUncheckItemResolution:
    def test_typo__resolves_and_unchecks_matched_item(self):
        graph = _make_graph()
        crepom = ShoppingListItem(id="c-id", name="Crepom", quantity=1.0, checked=True)
        graph.shopping_list_service.get_all.return_value = [crepom]
        graph.shopping_list_service.uncheck = MagicMock()
        state = {"output_uncheck_item": "grepom", "input": _input()}

        result = graph._handle_uncheck_item(state)

        graph.shopping_list_service.uncheck.assert_called_once_with("c-id")
        assert "Desmarcado" in result["output_uncheck_item"]

    def test_ambiguous__does_not_uncheck_and_stores_pending(self):
        disambig = MagicMock()
        disambig.set_pending = AsyncMock()
        graph = _make_graph(disambiguation_service=disambig)
        panela, seca = _two_carnes()
        graph.shopping_list_service.get_all.return_value = [panela, seca]
        graph.shopping_list_service.uncheck = MagicMock()
        state = {"output_uncheck_item": "carne", "input": _input(user_id="u9")}

        result = graph._handle_uncheck_item(state)

        graph.shopping_list_service.uncheck.assert_not_called()
        assert "?" in result["output_uncheck_item"]
        disambig.set_pending.assert_called_once()
        assert disambig.set_pending.call_args[0][1].operation == "uncheck"


# ---------------------------------------------------------------------------
# Feature — _handle_add_item uses ShoppingListService.add_items and formats the
# "Adicionado" / "Já estava na lista" sections (TDD — RED phase).
#
# New behaviour under test:
#   - the handler calls shopping_list_service.add_items (batch, dedup in the
#     domain) instead of one shopping_list_service.add per item;
#   - the reply has an "Adicionado" section for result.added, a "Já estava na
#     lista" section for result.duplicates, and always ends with the question
#     "Deseja mais alguma coisa?" when an operation happened;
#   - a section with no entries is omitted entirely;
#   - quantity formatting reuses the listing convention: integers without
#     ".0" and quantity 1 without any suffix.
# ---------------------------------------------------------------------------


def _add_result(added=None, duplicates=None):
    """
    Build the domain result DTO. Imported lazily so this module stays
    collectable while ShoppingListItemsAddResult does not exist yet (RED).
    """
    from domain.commands import ShoppingListItemsAddResult

    return ShoppingListItemsAddResult(
        added=added or [], duplicates=duplicates or []
    )


def _add_cmd(name, quantity=1.0):
    from domain.commands import ShoppingListItemAdd

    return ShoppingListItemAdd(name=name, quantity=quantity)


class TestHandleAddItemSections:
    def test_handle_add_item__calls_add_items_not_add(self):
        # Arrange
        graph = _make_graph()
        graph.shopping_list_service.add_items.return_value = _add_result(
            added=[_add_cmd("leite", 1.0)]
        )
        state = {"output_add_item": "leite,1"}
        # Act
        graph._handle_add_item(state)
        # Assert — the batch domain method is the single write path
        graph.shopping_list_service.add_items.assert_called_once()
        graph.shopping_list_service.add.assert_not_called()
        batch = graph.shopping_list_service.add_items.call_args[0][0]
        assert [item.name for item in batch] == ["leite"]

    def test_handle_add_item__only_added__formats_adicionado_section(self):
        # Arrange
        graph = _make_graph()
        graph.shopping_list_service.add_items.return_value = _add_result(
            added=[_add_cmd("ovos", 3.0), _add_cmd("açúcar", 1.0)]
        )
        state = {"output_add_item": "ovos,3|açúcar,1"}
        # Act
        result = graph._handle_add_item(state)
        # Assert
        output = result["output_add_item"]
        assert "Adicionado" in output
        assert "- ovos (3)" in output
        assert "Já estava na lista" not in output, (
            f"Duplicates section must be omitted when empty: {output!r}"
        )
        assert "Deseja mais alguma coisa?" in output

    def test_handle_add_item__added_and_duplicates__formats_both_sections(self):
        # Arrange
        graph = _make_graph()
        graph.shopping_list_service.add_items.return_value = _add_result(
            added=[_add_cmd("ovos", 3.0)],
            duplicates=[_add_cmd("farinha de trigo", 1.0)],
        )
        state = {"output_add_item": "ovos,3|farinha de trigo,1"}
        # Act
        result = graph._handle_add_item(state)
        # Assert
        output = result["output_add_item"]
        assert "Adicionado" in output
        assert "- ovos (3)" in output
        assert "Já estava na lista" in output
        assert "- farinha de trigo" in output
        assert "Deseja mais alguma coisa?" in output
        # "Adicionado" comes before "Já estava na lista"
        assert output.index("Adicionado") < output.index("Já estava na lista")

    def test_handle_add_item__only_duplicates__formats_only_duplicates_section(self):
        # Arrange
        graph = _make_graph()
        graph.shopping_list_service.add_items.return_value = _add_result(
            duplicates=[_add_cmd("farinha de trigo", 1.0)]
        )
        state = {"output_add_item": "farinha de trigo,1"}
        # Act
        result = graph._handle_add_item(state)
        # Assert
        output = result["output_add_item"]
        assert "Já estava na lista" in output
        assert "- farinha de trigo" in output
        assert "Adicionado" not in output, (
            f"'Adicionado' section must be omitted when nothing was added: {output!r}"
        )
        assert "Deseja mais alguma coisa?" in output

    def test_handle_add_item__quantity_formatting__integer_without_decimal(self):
        # Arrange — 3.0 renders as "(3)", 1.0 has no suffix, 1.5 stays "(1.5)"
        graph = _make_graph()
        graph.shopping_list_service.add_items.return_value = _add_result(
            added=[
                _add_cmd("ovos", 3.0),
                _add_cmd("leite", 1.0),
                _add_cmd("queijo", 1.5),
            ]
        )
        state = {"output_add_item": "ovos,3|leite,1|queijo,1.5"}
        # Act
        result = graph._handle_add_item(state)
        # Assert
        output = result["output_add_item"]
        assert "- ovos (3)" in output
        assert "(3.0)" not in output
        assert "- queijo (1.5)" in output
        # quantity 1 has no suffix at all
        assert any(
            line.strip() == "- leite" for line in output.splitlines()
        ), f"Expected a bare '- leite' line (no quantity suffix), got: {output!r}"

    def test_handle_add_item__empty_payload__does_not_call_add_items(self):
        # Arrange
        graph = _make_graph()
        state = {"output_add_item": "   "}
        # Act
        result = graph._handle_add_item(state)
        # Assert — nothing to add: no service call, no success claim
        graph.shopping_list_service.add_items.assert_not_called()
        output = result["output_add_item"]
        assert isinstance(output, str)
        assert "Adicionado" not in output, (
            f"Empty payload must not claim anything was added: {output!r}"
        )

    def test_handle_add_item__validation_error_from_service__graceful_message(self):
        # Arrange
        graph = _make_graph()
        graph.shopping_list_service.add_items.side_effect = ValidationError(
            errors=["Name is required"]
        )
        state = {"output_add_item": "leite,1"}
        # Act — must not raise
        result = graph._handle_add_item(state)
        # Assert — the error surfaces as a non-empty STRING (never a raw list)
        graph.shopping_list_service.add_items.assert_called_once()
        output = result["output_add_item"]
        assert isinstance(output, str)
        assert output.strip()
        assert "Adicionado" not in output, (
            f"A failed batch must not claim success: {output!r}"
        )
