"""
DisambiguationService unit tests (TDD — written before implementation).

DisambiguationService wraps a ContextRepository to persist a pending
disambiguation question for a user (JSON payload with an embedded TTL), and
resolves a follow-up reply into a concrete choice.

API under test:
    DisambiguationService(context_repository, shopping_list_service, ttl_seconds)
    async set_pending(user_id, pending) -> None
    async get_pending(user_id) -> Optional[PendingDisambiguation]   # expired => None + cleared
    async clear_pending(user_id) -> None
    resolve_choice(message, candidates) -> ChoiceResult             # kind = match|cancel|none
"""

import asyncio
import uuid
from unittest.mock import MagicMock

from domain.entities import DisambiguationCandidate, PendingDisambiguation
from domain.services.disambiguation_service import DisambiguationService, ChoiceResult
from domain.services.shopping_list_service import ShoppingListService


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class FakeContextRepository:
    """Minimal in-test async context repository backed by a dict of strings."""

    def __init__(self):
        self.store: dict = {}

    def connect(self):
        pass

    async def set_key(self, key, value):
        self.store[key] = value

    async def get_key(self, key):
        return self.store.get(key)

    async def delete_key(self, key):
        return self.store.pop(key, None) is not None


def _service(ttl_seconds=120, repo=None):
    return DisambiguationService(
        context_repository=repo or FakeContextRepository(),
        shopping_list_service=ShoppingListService(shopping_list_repository=MagicMock()),
        ttl_seconds=ttl_seconds,
    )


def _candidates():
    return [
        DisambiguationCandidate(id="id-1", name="Carne de panela"),
        DisambiguationCandidate(id="id-2", name="Carne seca"),
    ]


def _pending(operation="delete", query="carne"):
    return PendingDisambiguation(
        operation=operation, query=query, candidates=_candidates()
    )


class TestSetGetRoundtrip:
    def test_set_then_get_returns_equivalent_pending(self):
        service = _service()
        user_id = str(uuid.uuid4())

        _run(service.set_pending(user_id, _pending()))
        loaded = _run(service.get_pending(user_id))

        assert loaded is not None
        assert loaded.operation == "delete"
        assert loaded.query == "carne"
        assert [(c.id, c.name) for c in loaded.candidates] == [
            ("id-1", "Carne de panela"),
            ("id-2", "Carne seca"),
        ]

    def test_get_without_set_returns_none(self):
        service = _service()
        assert _run(service.get_pending(str(uuid.uuid4()))) is None


class TestExpiry:
    def test_expired_pending__returns_none_and_clears(self):
        repo = FakeContextRepository()
        service = _service(ttl_seconds=-10, repo=repo)
        user_id = str(uuid.uuid4())

        _run(service.set_pending(user_id, _pending()))
        loaded = _run(service.get_pending(user_id))

        assert loaded is None
        # Expired entry must be purged from the store.
        assert repo.store == {}


class TestClear:
    def test_clear_removes_pending(self):
        service = _service()
        user_id = str(uuid.uuid4())
        _run(service.set_pending(user_id, _pending()))

        _run(service.clear_pending(user_id))

        assert _run(service.get_pending(user_id)) is None


class TestResolveChoiceCancel:
    def test_cancel_word__returns_cancel(self):
        service = _service()
        result = service.resolve_choice("cancelar", _candidates())
        assert isinstance(result, ChoiceResult)
        assert result.kind == "cancel"

    def test_deixa_pra_la__returns_cancel(self):
        service = _service()
        result = service.resolve_choice("deixa pra lá", _candidates())
        assert result.kind == "cancel"


class TestResolveChoiceOrdinal:
    def test_a_primeira__matches_first_candidate(self):
        service = _service()
        result = service.resolve_choice("a primeira", _candidates())
        assert result.kind == "match"
        assert result.candidate.id == "id-1"

    def test_segundo__matches_second_candidate(self):
        service = _service()
        result = service.resolve_choice("o segundo", _candidates())
        assert result.kind == "match"
        assert result.candidate.id == "id-2"

    def test_digit__matches_by_position(self):
        service = _service()
        result = service.resolve_choice("1", _candidates())
        assert result.kind == "match"
        assert result.candidate.id == "id-1"

    def test_ultimo__matches_last_candidate(self):
        service = _service()
        result = service.resolve_choice("o último", _candidates())
        assert result.kind == "match"
        assert result.candidate.id == "id-2"


class TestResolveChoiceLiteral:
    def test_literal_name__matches_that_candidate(self):
        service = _service()
        result = service.resolve_choice("carne de panela", _candidates())
        assert result.kind == "match"
        assert result.candidate.id == "id-1"


class TestResolveChoiceNone:
    def test_unrelated_message__returns_none(self):
        service = _service()
        result = service.resolve_choice("acende a luz da sala", _candidates())
        assert result.kind == "none"
        assert result.candidate is None


class TestResolveChoiceLengthGuards:
    """Backport of the §9.3 guards: a long command carrying a digit or a cancel
    word must not hijack a pending choice."""

    def test_digit_in_long_message__returns_none(self):
        service = _service()
        result = service.resolve_choice("coloca 3 leites na lista", _candidates())
        assert result.kind == "none"

    def test_para_inside_long_message__does_not_cancel(self):
        service = _service()
        result = service.resolve_choice("põe leite na lista para amanhã", _candidates())
        assert result.kind != "cancel"
