"""
Deterministic text-matching helpers shared across domain services.

This centralizes the normalization/tokenization previously living in
``shopping_list_service`` and the cancel-word/ordinal parsing previously living
in ``disambiguation_service``. Keeping them in one place removes the lateral
coupling (disambiguation importing from shopping list) and lets the vehicle
domain reuse the exact same matching.

It also adds the length guards of the vehicle-maintenance plan (§9.3): an
ordinal or a cancel word is only honored in a short, content-poor message, so a
long legitimate command that merely contains a digit ("coloca 3 leites na
lista") or a cancel word ("... para amanhã") never hijacks a pending choice.
"""

import unicodedata
from difflib import SequenceMatcher
from typing import Callable, List, TypeVar

T = TypeVar("T")

# Fuzzy-match thresholds shared by every deterministic term matcher (vehicles,
# pets, ...). A typo is only honored above this ratio and above a minimum length.
_FUZZY_THRESHOLD = 0.8
_FUZZY_MIN_LENGTH = 4


# Generic Portuguese connective words dropped when tokenizing, so a partial
# query like "carne" matches "Carne de panela". Intentionally small and
# product-neutral.
_NAME_STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos",
    "e", "com", "sem", "para", "por", "no", "na", "nos", "nas", "em",
}

# Words that cancel a pending question.
_CANCEL_WORDS = {
    "cancelar", "cancela", "cancele", "deixa", "nenhum", "nenhuma",
    "esquece", "esqueci", "para",
}

# Portuguese ordinal words mapped to a zero-based position.
_ORDINAL_WORDS = {
    "primeiro": 0, "primeira": 0,
    "segundo": 1, "segunda": 1,
    "terceiro": 2, "terceira": 2,
    "quarto": 3, "quarta": 3,
    "quinto": 4, "quinta": 4,
}

# Words selecting the last candidate.
_LAST_WORDS = {"ultimo", "ultima"}

# A follow-up reply may only be read as an ordinal/cancel when it carries at
# most this many content tokens; longer messages are treated as fresh commands.
_MAX_CHOICE_TOKENS = 3


def normalize(value: str) -> str:
    """
    Normalize a string for deterministic comparison: NFD-strip accents,
    lowercase and trim.
    """
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFD", value)
    stripped = decomposed.encode("ascii", "ignore").decode("ascii")
    return stripped.lower().strip()


def name_tokens(value: str) -> set:
    """
    Break a name/query into comparable content tokens: normalize, split on
    whitespace and hyphens, and drop generic Portuguese stopwords.
    """
    normalized = normalize(value).replace("-", " ")
    return {
        token
        for token in normalized.split()
        if token and token not in _NAME_STOPWORDS
    }


def is_cancel(message: str, max_content_tokens: int = _MAX_CHOICE_TOKENS) -> bool:
    """
    True when a short reply cancels the pending question. Long messages (more
    than ``max_content_tokens`` content tokens) never cancel, even if they
    contain a cancel word.
    """
    tokens = name_tokens(message)
    if not tokens or len(tokens) > max_content_tokens:
        return False
    return bool(tokens & _CANCEL_WORDS)


def resolve_ordinal(
    message: str, count: int, max_content_tokens: int = _MAX_CHOICE_TOKENS
):
    """
    Resolve a short reply to a zero-based candidate index (ordinal word, "último"
    or a bare position digit), or None. Long messages are never read as an
    ordinal — the guard that stops "coloca 3 leites na lista" from selecting
    candidate #3.
    """
    tokens = name_tokens(message)
    if not tokens or len(tokens) > max_content_tokens:
        return None
    for token in tokens:
        if token in _LAST_WORDS:
            return count - 1
        if token in _ORDINAL_WORDS and _ORDINAL_WORDS[token] < count:
            return _ORDINAL_WORDS[token]
        if token.isdigit():
            position = int(token)
            if 1 <= position <= count:
                return position - 1
    return None


def find_by_term(
    term: str, items: List[T], searchables: Callable[[T], List[str]]
) -> List[T]:
    """
    Resolve a user-typed term against already-loaded items, deterministically
    (no LLM, no repository access). ``searchables`` yields every string an item
    may legitimately match by. Three layers in priority order; the first
    non-empty layer wins:

      1. exact normalized match on any searchable field — short-circuits so a
         literal name is never treated as ambiguous;
      2. partial — the query tokens are a subset of a field's tokens;
      3. typo — difflib ratio >= threshold, guarded by a minimum length.

    Returns 0, 1 or many; the caller uses the count to act or disambiguate.
    """
    normalized_query = normalize(term)
    if not normalized_query or not items:
        return []

    exact = [
        item
        for item in items
        if any(normalize(s) == normalized_query for s in searchables(item))
    ]
    if exact:
        return exact

    query_tokens = name_tokens(term)
    if query_tokens:
        partial = [
            item
            for item in items
            if any(query_tokens <= name_tokens(s) for s in searchables(item))
        ]
        if partial:
            return partial

    if len(normalized_query) >= _FUZZY_MIN_LENGTH:
        fuzzy = [
            item
            for item in items
            if any(
                SequenceMatcher(None, normalized_query, normalize(s)).ratio()
                >= _FUZZY_THRESHOLD
                for s in searchables(item)
            )
        ]
        if fuzzy:
            return fuzzy

    return []
