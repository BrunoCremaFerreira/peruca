"""
text_matching unit tests (TDD — written before implementation).

text_matching centralizes the deterministic string helpers previously scattered
between shopping_list_service (_normalize / _name_tokens) and
disambiguation_service (cancel words, ordinals), and adds the length guards of
§9.3 (ordinal/cancel only apply to short, content-poor messages) so a long
message that merely contains a digit or a cancel word does not hijack a pending
choice.

API under test:
    normalize(value) -> str
    name_tokens(value) -> set
    is_cancel(message, max_content_tokens=3) -> bool
    resolve_ordinal(message, count, max_content_tokens=3) -> Optional[int]
"""

from domain.services.text_matching import (
    is_cancel,
    name_tokens,
    normalize,
    resolve_ordinal,
)


class TestNormalize:
    def test_strips_accents_lowercases_and_trims(self):
        assert normalize("  Pajerão ") == "pajerao"

    def test_empty_returns_empty(self):
        assert normalize("") == ""


class TestNameTokens:
    def test_drops_stopwords_and_splits(self):
        assert name_tokens("Carne de panela") == {"carne", "panela"}

    def test_keeps_digits(self):
        assert name_tokens("coloca 3 leites na lista") == {"coloca", "3", "leites", "lista"}


class TestIsCancel:
    def test_short_cancel_word__true(self):
        assert is_cancel("cancelar") is True

    def test_deixa_pra_la__true(self):
        assert is_cancel("deixa pra lá") is True

    def test_cancel_word_in_long_message__false(self):
        # "para" appears but the message is a legitimate long command.
        assert is_cancel("põe leite na lista para amanhã") is False

    def test_unrelated_short_message__false(self):
        assert is_cancel("do outlander") is False


class TestResolveOrdinal:
    def test_a_primeira__index_0(self):
        assert resolve_ordinal("a primeira", 2) == 0

    def test_o_segundo__index_1(self):
        assert resolve_ordinal("o segundo", 2) == 1

    def test_digit__index_by_position(self):
        assert resolve_ordinal("1", 2) == 0

    def test_ultimo__last_index(self):
        assert resolve_ordinal("o último", 2) == 1

    def test_digit_in_long_message__none(self):
        # The guard: "coloca 3 leites na lista" must not select candidate #3.
        assert resolve_ordinal("coloca 3 leites na lista", 3) is None

    def test_out_of_range_digit__none(self):
        assert resolve_ordinal("5", 2) is None

    def test_unrelated_message__none(self):
        assert resolve_ordinal("do outlander", 2) is None
