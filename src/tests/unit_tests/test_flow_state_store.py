"""
FlowStateStore unit tests (TDD — written before implementation).

FlowStateStore is the generic, mechanical persistence extracted from
MaintenanceFlowService: a JSON payload keyed by user_id with an embedded TTL, for
both the "pending" slot and the "focus" slot. It knows nothing about the shape of
the payload — that stays the caller's responsibility. It only injects/enforces the
TTL and (de)serializes.

API under test:
    FlowStateStore(context_repository, key_prefix, focus_prefix, ttl_seconds=600)
    async set_pending(user_id, payload_dict) -> None
    async get_pending_raw(user_id) -> Optional[dict]
    async clear_pending(user_id) -> None
    async set_focus(user_id, focus_dict) -> None
    async get_focus(user_id) -> Optional[dict]
    async clear_focus(user_id) -> None
"""

import asyncio
import uuid

from domain.services.flow_state_store import FlowStateStore


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class FakeContextRepository:
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


def _store(ttl_seconds=600, repo=None):
    return FlowStateStore(
        context_repository=repo or FakeContextRepository(),
        key_prefix="maintenance_flow:",
        focus_prefix="maintenance_focus:",
        ttl_seconds=ttl_seconds,
    )


class TestPending:
    def test_set_then_get_roundtrip(self):
        store = _store()
        user_id = str(uuid.uuid4())

        _run(store.set_pending(user_id, {"operation": "register", "slots": {"a": 1}}))
        loaded = _run(store.get_pending_raw(user_id))

        assert loaded is not None
        assert loaded["operation"] == "register"
        assert loaded["slots"] == {"a": 1}
        assert "expires_at" in loaded

    def test_get_without_set_returns_none(self):
        store = _store()
        assert _run(store.get_pending_raw(str(uuid.uuid4()))) is None

    def test_expired_ttl_clears_store_and_returns_none(self):
        repo = FakeContextRepository()
        store = _store(ttl_seconds=-10, repo=repo)
        user_id = str(uuid.uuid4())

        _run(store.set_pending(user_id, {"operation": "register"}))
        assert _run(store.get_pending_raw(user_id)) is None
        # The expired key is proactively cleared.
        assert repo.store == {}

    def test_raw_literal_none_string_returns_none(self):
        repo = FakeContextRepository()
        store = _store(repo=repo)
        user_id = str(uuid.uuid4())
        repo.store["maintenance_flow:" + user_id] = "None"
        assert _run(store.get_pending_raw(user_id)) is None

    def test_raw_none_value_returns_none(self):
        repo = FakeContextRepository()
        store = _store(repo=repo)
        user_id = str(uuid.uuid4())
        repo.store["maintenance_flow:" + user_id] = None
        assert _run(store.get_pending_raw(user_id)) is None

    def test_invalid_json_returns_none(self):
        repo = FakeContextRepository()
        store = _store(repo=repo)
        user_id = str(uuid.uuid4())
        repo.store["maintenance_flow:" + user_id] = "{not valid json"
        assert _run(store.get_pending_raw(user_id)) is None

    def test_clear_pending_removes_key(self):
        store = _store()
        user_id = str(uuid.uuid4())
        _run(store.set_pending(user_id, {"operation": "register"}))
        _run(store.clear_pending(user_id))
        assert _run(store.get_pending_raw(user_id)) is None


class TestFocus:
    def test_set_then_get_roundtrip(self):
        store = _store()
        user_id = str(uuid.uuid4())
        _run(store.set_focus(user_id, {"record_id": "abc", "pet_name": "Caçolin"}))
        loaded = _run(store.get_focus(user_id))

        assert loaded is not None
        assert loaded["record_id"] == "abc"
        assert loaded["pet_name"] == "Caçolin"

    def test_expired_focus_clears_and_returns_none(self):
        repo = FakeContextRepository()
        store = _store(ttl_seconds=-10, repo=repo)
        user_id = str(uuid.uuid4())
        _run(store.set_focus(user_id, {"record_id": "abc"}))
        assert _run(store.get_focus(user_id)) is None
        assert repo.store == {}

    def test_focus_without_set_returns_none(self):
        store = _store()
        assert _run(store.get_focus(str(uuid.uuid4()))) is None

    def test_clear_focus_removes_key(self):
        store = _store()
        user_id = str(uuid.uuid4())
        _run(store.set_focus(user_id, {"record_id": "abc"}))
        _run(store.clear_focus(user_id))
        assert _run(store.get_focus(user_id)) is None
