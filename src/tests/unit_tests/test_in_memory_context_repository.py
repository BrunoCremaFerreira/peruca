"""
InMemoryContextRepository unit tests (TDD — written before implementation).

The in-memory ContextRepository is the fallback used when no Redis
(CACHE_DB_CONNECTION_STRING) is configured, so the disambiguation feature works
without Redis. It stores string values in a process-local dict and mirrors the
async ContextRepository contract.
"""

import asyncio

from domain.interfaces.data_repository import ContextRepository
from infra.data.cache.in_memory_context_repository import InMemoryContextRepository


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestInMemoryContextRepository:
    def test_is_a_context_repository(self):
        assert isinstance(InMemoryContextRepository(), ContextRepository)

    def test_set_then_get_returns_value(self):
        repo = InMemoryContextRepository()
        _run(repo.set_key("k", "v"))
        assert _run(repo.get_key("k")) == "v"

    def test_get_missing_key_returns_none(self):
        repo = InMemoryContextRepository()
        assert _run(repo.get_key("absent")) is None

    def test_delete_removes_key(self):
        repo = InMemoryContextRepository()
        _run(repo.set_key("k", "v"))
        _run(repo.delete_key("k"))
        assert _run(repo.get_key("k")) is None

    def test_delete_missing_key_does_not_raise(self):
        repo = InMemoryContextRepository()
        # Should not raise
        _run(repo.delete_key("absent"))

    def test_set_overwrites_existing_value(self):
        repo = InMemoryContextRepository()
        _run(repo.set_key("k", "v1"))
        _run(repo.set_key("k", "v2"))
        assert _run(repo.get_key("k")) == "v2"
