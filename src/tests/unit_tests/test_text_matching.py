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

from dataclasses import dataclass, field
from typing import List

from domain.services.text_matching import (
    find_by_term,
    is_cancel,
    name_tokens,
    normalize,
    resolve_ordinal,
)


@dataclass
class _Dummy:
    """A minimal item to exercise the generic find_by_term contract."""

    name: str = ""
    aliases: List[str] = field(default_factory=list)


def _searchables(item: "_Dummy") -> List[str]:
    return [item.name, *item.aliases]


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


class TestFindByTerm:
    def test_exact_normalized_match_wins(self):
        caco = _Dummy(name="Caçolin", aliases=["Lilo"])
        cacao = _Dummy(name="Caçolão", aliases=["Lyon"])
        result = find_by_term("cacolin", [caco, cacao], _searchables)
        assert result == [caco]

    def test_exact_match_on_alias(self):
        caco = _Dummy(name="Caçolin", aliases=["Lilo", "Suzu"])
        result = find_by_term("Suzu", [caco], _searchables)
        assert result == [caco]

    def test_partial_token_subset_match(self):
        item = _Dummy(name="Carne de panela")
        result = find_by_term("carne", [item], _searchables)
        assert result == [item]

    def test_fuzzy_typo_with_accent(self):
        # "Caninça" is a phonetic typo of "Caniça" — resolved by the fuzzy layer.
        cani = _Dummy(name="Caniça")
        result = find_by_term("Caninça", [cani], _searchables)
        assert result == [cani]

    def test_no_matches_returns_empty(self):
        item = _Dummy(name="Fusca")
        assert find_by_term("Ferrari", [item], _searchables) == []

    def test_multiple_matches_returned(self):
        a = _Dummy(name="Gato Preto")
        b = _Dummy(name="Gato Branco")
        result = find_by_term("gato", [a, b], _searchables)
        assert result == [a, b]

    def test_empty_term_returns_empty(self):
        item = _Dummy(name="Fusca")
        assert find_by_term("", [item], _searchables) == []

    def test_empty_items_returns_empty(self):
        assert find_by_term("fusca", [], _searchables) == []


class TestFindByTermPetNicknames:
    """
    Pet matching reuses find_by_term with searchables=[p.name, *p.nicknames]
    (§2.1a / requirement 4): a pet is resolvable by any of its nicknames, not
    only the primary one, and matching is accent-insensitive.
    """

    def test_match_on_secondary_nickname(self):
        # The SECOND nickname (not the primary) must still resolve the pet.
        caco = _Dummy(name="Caçolin", aliases=["Lilo", "Caçolinho", "Suzu"])
        cacao = _Dummy(name="Caçolão", aliases=["Lyon"])
        result = find_by_term("Suzu", [caco, cacao], _searchables)
        assert result == [caco]

    def test_match_on_nickname_is_accent_insensitive(self):
        # "cacolinho" (no cedilla) must match the accented nickname "Caçolinho".
        caco = _Dummy(name="Caçolin", aliases=["Lilo", "Caçolinho", "Suzu"])
        result = find_by_term("cacolinho", [caco], _searchables)
        assert result == [caco]

    def test_phonetic_typo_on_name_resolves_via_fuzzy(self):
        # "Câniça" is a phonetic variant of "Caniça" (requirement 4).
        cani = _Dummy(name="Caniça", aliases=["Nick"])
        result = find_by_term("Câniça", [cani], _searchables)
        assert result == [cani]
