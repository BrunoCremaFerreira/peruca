import uuid
from unittest.mock import MagicMock, patch

from application.graphs.shopping_list_graph import ShoppingListGraph
from domain.entities import ShoppingListItem


"""
ShoppingListGraph._format_items unit tests (TDD — RED phase).

These tests are written against the NEW expected behaviour of _format_items and
will FAIL against the current implementation:

    def _format_items(self, items):
        lines = []
        for index, item in enumerate(items, start=1):
            status = " (comprado)" if item.checked else ""
            lines.append(f"{index}. {item.name} ({item.quantity}){status}")
        return "\\n".join(lines)

NEW behaviour expected:
  1. Each item on its own line, prefixed with "- " (hyphen + space), NOT numbered.
  2. Quantity shown only when != 1, formatted without trailing ".0"
     (2.0 -> "2", 1.5 -> "1.5"). For quantity 1 (or 1.0) no quantity is shown.
  3. Items checked == True get the suffix " (comprado)".
  4. A human-readable header line precedes the list; first line contains "lista"
     (case-insensitive) and the output is a single multi-line string.
  5. Output is always str.
  6. Regression: no item line may start with "1. " (old numbering), and the
     output must not contain "(1.0)" nor ".0".
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


def _sample_item(name="Leite", quantity=1.0, checked=False) -> ShoppingListItem:
    return ShoppingListItem(
        id=str(uuid.uuid4()), name=name, quantity=quantity, checked=checked
    )


def _item_lines(output: str):
    """Return only the item lines (lines beginning with '- ')."""
    return [line for line in output.splitlines() if line.startswith("- ")]


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------


class TestFormatItemsOutputType:
    def test_format_items__returns_str(self):
        graph = _make_graph()
        items = [_sample_item(name="leite", quantity=1.0)]

        result = graph._format_items(items)

        assert isinstance(result, str)

    def test_format_items__output_has_multiple_lines(self):
        graph = _make_graph()
        items = [
            _sample_item(name="leite", quantity=1.0),
            _sample_item(name="arroz", quantity=2.0),
        ]

        result = graph._format_items(items)

        # header line + two item lines -> at least 2 newlines / 3 lines
        assert len(result.splitlines()) >= 3


# ---------------------------------------------------------------------------
# Hyphen prefix, no numbering
# ---------------------------------------------------------------------------


class TestFormatItemsHyphenPrefix:
    def test_format_items__item_line_starts_with_hyphen_space(self):
        graph = _make_graph()
        items = [_sample_item(name="leite", quantity=1.0)]

        result = graph._format_items(items)

        item_lines = _item_lines(result)
        assert item_lines, f"No hyphen-prefixed item lines found in: {result!r}"
        for line in item_lines:
            assert line.startswith("- "), f"Item line must start with '- ': {line!r}"

    def test_format_items__quantity_one__line_is_just_dash_and_name(self):
        graph = _make_graph()
        items = [_sample_item(name="leite", quantity=1.0)]

        result = graph._format_items(items)

        assert "- leite" in result

    def test_format_items__not_numbered(self):
        """Regression: old implementation prefixed lines with '1. ', '2. ', ..."""
        graph = _make_graph()
        items = [
            _sample_item(name="leite", quantity=1.0),
            _sample_item(name="arroz", quantity=2.0),
        ]

        result = graph._format_items(items)

        for line in result.splitlines():
            assert not line.startswith("1. "), (
                f"Numbered item line found (old behaviour): {line!r}"
            )
            assert not line.startswith("2. "), (
                f"Numbered item line found (old behaviour): {line!r}"
            )


# ---------------------------------------------------------------------------
# Quantity formatting
# ---------------------------------------------------------------------------


class TestFormatItemsQuantity:
    def test_format_items__quantity_one_is_hidden(self):
        graph = _make_graph()
        items = [_sample_item(name="leite", quantity=1.0)]

        result = graph._format_items(items)

        item_lines = _item_lines(result)
        assert item_lines == ["- leite"], (
            f"Quantity 1 must not be shown, got item lines: {item_lines!r}"
        )

    def test_format_items__quantity_two_shown_without_decimal(self):
        graph = _make_graph()
        items = [_sample_item(name="arroz", quantity=2.0)]

        result = graph._format_items(items)

        assert "- arroz (2)" in result, (
            f"Expected '- arroz (2)' (no decimal), got: {result!r}"
        )

    def test_format_items__fractional_quantity_kept(self):
        graph = _make_graph()
        items = [_sample_item(name="carne", quantity=1.5)]

        result = graph._format_items(items)

        assert "- carne (1.5)" in result, (
            f"Expected '- carne (1.5)', got: {result!r}"
        )

    def test_format_items__no_trailing_dot_zero_anywhere(self):
        """Regression: '2.0' / '1.0' must be rendered as '2' / hidden, never '.0'."""
        graph = _make_graph()
        items = [
            _sample_item(name="leite", quantity=1.0),
            _sample_item(name="arroz", quantity=2.0),
            _sample_item(name="ovos", quantity=12.0),
        ]

        result = graph._format_items(items)

        assert ".0" not in result, f"Found '.0' in output: {result!r}"

    def test_format_items__no_paren_one_point_zero(self):
        """Regression: old implementation rendered '(1.0)'."""
        graph = _make_graph()
        items = [_sample_item(name="leite", quantity=1.0)]

        result = graph._format_items(items)

        assert "(1.0)" not in result, f"Found '(1.0)' in output: {result!r}"


# ---------------------------------------------------------------------------
# Checked items
# ---------------------------------------------------------------------------


class TestFormatItemsChecked:
    def test_format_items__checked_quantity_one__has_comprado_suffix(self):
        graph = _make_graph()
        items = [_sample_item(name="pão", quantity=1.0, checked=True)]

        result = graph._format_items(items)

        assert "- pão (comprado)" in result, (
            f"Expected '- pão (comprado)', got: {result!r}"
        )

    def test_format_items__checked_with_quantity__quantity_then_comprado(self):
        graph = _make_graph()
        items = [_sample_item(name="pão", quantity=3.0, checked=True)]

        result = graph._format_items(items)

        assert "- pão (3) (comprado)" in result, (
            f"Expected '- pão (3) (comprado)', got: {result!r}"
        )

    def test_format_items__unchecked__no_comprado_suffix(self):
        graph = _make_graph()
        items = [_sample_item(name="leite", quantity=1.0, checked=False)]

        result = graph._format_items(items)

        assert "(comprado)" not in result, (
            f"Unchecked item must not have '(comprado)' suffix, got: {result!r}"
        )


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------


class TestFormatItemsHeader:
    def test_format_items__first_line_contains_lista(self):
        graph = _make_graph()
        items = [_sample_item(name="leite", quantity=1.0)]

        result = graph._format_items(items)

        first_line = result.splitlines()[0]
        assert "lista" in first_line.lower(), (
            f"First line must contain 'lista', got: {first_line!r}"
        )

    def test_format_items__header_is_not_an_item_line(self):
        graph = _make_graph()
        items = [_sample_item(name="leite", quantity=1.0)]

        result = graph._format_items(items)

        first_line = result.splitlines()[0]
        assert not first_line.startswith("- "), (
            f"Header line must not be an item line, got: {first_line!r}"
        )


# ---------------------------------------------------------------------------
# Combined / multiple items
# ---------------------------------------------------------------------------


class TestFormatItemsMultiple:
    def test_format_items__multiple_items__each_on_own_line(self):
        graph = _make_graph()
        items = [
            _sample_item(name="leite", quantity=1.0),
            _sample_item(name="arroz", quantity=2.0),
            _sample_item(name="pão", quantity=3.0, checked=True),
        ]

        result = graph._format_items(items)

        item_lines = _item_lines(result)
        assert "- leite" in item_lines
        assert "- arroz (2)" in item_lines
        assert "- pão (3) (comprado)" in item_lines


# ---------------------------------------------------------------------------
# Node-level integration: _handle_list_items reuses _format_items
# ---------------------------------------------------------------------------


class TestHandleListItemsUsesNewFormat:
    def test_handle_list_items__two_items__output_uses_hyphens_no_numbering(self):
        graph = _make_graph()
        item_leite = _sample_item(name="leite", quantity=1.0)
        item_arroz = ShoppingListItem(
            id="arroz-id", name="arroz", quantity=2.0, checked=False
        )
        graph.shopping_list_service.get_all = MagicMock(
            return_value=[item_leite, item_arroz]
        )

        result = graph._handle_list_items({})

        output = result["output_list_items"]
        assert isinstance(output, str)
        assert ".0" not in output, f"Found '.0' in output: {output!r}"
        item_lines = _item_lines(output)
        assert "- leite" in item_lines
        assert "- arroz (2)" in item_lines
        for line in output.splitlines():
            assert not line.startswith("1. "), (
                f"Numbered item line found (old behaviour): {line!r}"
            )
