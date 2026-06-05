"""
ShoppingListGraph._parse_shopping_list_add robustness unit tests.

The classifier emits "name,quantity" pairs joined by "|". When the LLM includes
a unit in the quantity (e.g. "batata,2 kg"), the previous implementation did
``float("2 kg")`` which raised ValueError and silently dropped the whole item.
The parser must instead extract the leading numeric value (defaulting to 1.0)
and keep the item.
"""

from unittest.mock import MagicMock, patch

import pytest

from application.graphs.shopping_list_graph import ShoppingListGraph


def _make_graph() -> ShoppingListGraph:
    llm_chat = MagicMock()
    shopping_list_service = MagicMock()
    with patch.object(ShoppingListGraph, "load_prompt", return_value="{input}"):
        return ShoppingListGraph(
            llm_chat=llm_chat, shopping_list_service=shopping_list_service
        )


class TestParseShoppingListAdd:
    def test_quantity_with_unit__keeps_item_and_extracts_number(self):
        graph = _make_graph()

        items = graph._parse_shopping_list_add("batata,2 kg|cebola,1")

        names = {i.name: i.quantity for i in items}
        assert "batata" in names, f"batata dropped: {names!r}"
        assert names["batata"] == 2.0
        assert names["cebola"] == 1.0

    def test_quantity_non_numeric__defaults_to_one(self):
        graph = _make_graph()

        items = graph._parse_shopping_list_add("sal,a gosto")

        assert len(items) == 1
        assert items[0].name == "sal"
        assert items[0].quantity == 1.0

    def test_quantity_with_decimal_and_unit__extracts_decimal(self):
        graph = _make_graph()

        items = graph._parse_shopping_list_add("queijo,1.5 kg")

        assert len(items) == 1
        assert items[0].quantity == 1.5

    def test_plain_numeric_quantity__unchanged(self):
        graph = _make_graph()

        items = graph._parse_shopping_list_add("leite,3")

        assert len(items) == 1
        assert items[0].name == "leite"
        assert items[0].quantity == 3.0

    def test_item_without_quantity__defaults_to_one(self):
        graph = _make_graph()

        items = graph._parse_shopping_list_add("manteiga")

        assert len(items) == 1
        assert items[0].name == "manteiga"
        assert items[0].quantity == 1.0

    def test_empty_input__returns_empty(self):
        graph = _make_graph()

        assert graph._parse_shopping_list_add("   ") == []
