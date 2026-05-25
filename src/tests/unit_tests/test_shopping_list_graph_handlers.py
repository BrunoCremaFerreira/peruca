import uuid
from unittest.mock import MagicMock, patch
import pytest

from application.graphs.shopping_list_graph import ShoppingListGraph
from domain.entities import ShoppingListItem
from domain.exceptions import ValidationError


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

def _make_graph() -> ShoppingListGraph:
    """
    Build a ShoppingListGraph with all external dependencies mocked.
    load_prompt is patched to avoid filesystem access.
    """
    llm_chat = MagicMock()
    shopping_list_service = MagicMock()
    shopping_list_service.get_by_name = MagicMock(return_value=None)
    shopping_list_service.get_all = MagicMock(return_value=[])

    with patch.object(ShoppingListGraph, "load_prompt", return_value="{input}"):
        graph = ShoppingListGraph(
            llm_chat=llm_chat,
            shopping_list_service=shopping_list_service,
        )

    return graph


def _sample_item(name="Leite", quantity=1.0) -> ShoppingListItem:
    return ShoppingListItem(id=str(uuid.uuid4()), name=name, quantity=quantity, checked=False)


# ---------------------------------------------------------------------------
# Mudanca 1 — _handle_add_item returns Portuguese string with "Adicionado:"
# ---------------------------------------------------------------------------

class TestHandleAddItemOutputLanguage:

    def test_handle_add_item__single_item__output_contains_adicionado(self):
        graph = _make_graph()
        # "leite,1" is the pipe-delimited format parsed by _parse_shopping_list_add
        state = {"output_add_item": "leite,1"}

        result = graph._handle_add_item(state)

        assert "Adicionado" in result["output_add_item"], (
            f"Expected 'Adicionado' in output, got: {result['output_add_item']!r}"
        )

    def test_handle_add_item__single_item__output_contains_item_name(self):
        graph = _make_graph()
        state = {"output_add_item": "leite,1"}

        result = graph._handle_add_item(state)

        assert "leite" in result["output_add_item"].lower()

    def test_handle_add_item__multiple_items__output_contains_adicionado(self):
        graph = _make_graph()
        state = {"output_add_item": "leite,1|arroz,2"}

        result = graph._handle_add_item(state)

        assert "Adicionado" in result["output_add_item"]

    def test_handle_add_item__single_item__does_not_return_english_prefix(self):
        """Regression: previous implementation used 'Items Add:' prefix."""
        graph = _make_graph()
        state = {"output_add_item": "leite,1"}

        result = graph._handle_add_item(state)

        assert "Items Add" not in result["output_add_item"], (
            "English prefix 'Items Add' must be replaced with Portuguese"
        )

    def test_handle_add_item__service_called_once_per_item(self):
        graph = _make_graph()
        state = {"output_add_item": "leite,1|arroz,2"}

        graph._handle_add_item(state)

        assert graph.shopping_list_service.add.call_count == 2

    def test_handle_add_item__validation_error__returns_error_in_output(self):
        graph = _make_graph()
        graph.shopping_list_service.add.side_effect = ValidationError(errors=["Name is required"])
        state = {"output_add_item": "leite,1"}

        result = graph._handle_add_item(state)

        # Should not raise; error surfaced in the output key
        assert "output_add_item" in result


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
        portuguese_keywords = ["lista", "itens", "removidos", "limpa", "apagados", "vazia"]
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

    def test_handle_check_item__item_found_by_name__calls_service_check_with_item_id(self):
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
        assert "Marcado" in output, (
            f"Expected 'Marcado' in output, got: {output!r}"
        )

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
        item_ovos = ShoppingListItem(id="ovos-id", name="ovos", quantity=1.0, checked=False)
        graph.shopping_list_service.get_all = MagicMock(return_value=[item_leite, item_ovos])
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

    def test_handle_uncheck_item__item_found_by_name__calls_service_uncheck_with_item_id(self):
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
        item_ovos = ShoppingListItem(id="ovos-id", name="ovos", quantity=1.0, checked=True)
        graph.shopping_list_service.get_all = MagicMock(return_value=[item_leite, item_ovos])
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
