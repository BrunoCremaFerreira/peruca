"""
RedisImageStore unit tests (TDD - RED phase, Fase B).

The store keeps inbound base64 images (full data URIs) OUT of the conversation
history but available for on-demand re-vision (Fase C). It is a synchronous
facade over async_runner (mirrors RedisChatMessageHistory), built on a
ContextRepository.

Contract (domain ABC ImageStore):
    save(user_id, image_id, data_uri) -> None
    get(user_id, image_id) -> Optional[str]
    next_index(user_id) -> int          # stable per-user handle N (#N)

Security/robustness:
  - key is namespaced per user: image:{user_id}:{image_id}
  - get NEVER resolves another user's id (cross-user isolation)
  - TTL applied on write; cap per user evicts the oldest blob

Expected to FAIL until RedisImageStore exists.
"""

import json

import pytest

from infra.data.external.redis.redis_image_store import RedisImageStore


class _FakeClient:
    def __init__(self):
        self.counters = {}
        self.expires = {}

    async def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key, ttl):
        self.expires[key] = ttl
        return True


class _FakeContextRepo:
    """In-memory ContextRepository stand-in for the store facade."""

    def __init__(self):
        self.store = {}
        self._client = _FakeClient()

    async def set_key(self, key, value):
        self.store[key] = value

    async def get_key(self, key):
        return self.store.get(key, "None")

    async def delete_key(self, key):
        self.store.pop(key, None)
        return True

    def _get_client(self):
        return self._client


def _make_store(ttl=86400, max_per_user=3):
    repo = _FakeContextRepo()
    store = RedisImageStore(repo, ttl_seconds=ttl, max_per_user=max_per_user)
    return store, repo


URI_A = "data:image/png;base64,aGVsbG8="
URI_B = "data:image/jpeg;base64,d29ybGQ="


class TestRedisImageStoreRoundTrip:
    def test_save_then_get_returns_data_uri(self):
        store, _ = _make_store()
        store.save("user-1", "1", URI_A)
        assert store.get("user-1", "1") == URI_A

    def test_get_unknown_id_returns_none(self):
        store, _ = _make_store()
        assert store.get("user-1", "999") is None

    def test_key_is_namespaced_per_user(self):
        store, repo = _make_store()
        store.save("user-1", "7", URI_A)
        assert "image:user-1:7" in repo.store
        assert repo.store["image:user-1:7"] == URI_A


class TestRedisImageStoreCrossUserIsolation:
    def test_get_does_not_resolve_other_users_id(self):
        store, _ = _make_store()
        store.save("user-A", "1", URI_A)
        # Same image_id, different user → must not leak.
        assert store.get("user-B", "1") is None


class TestRedisImageStoreTTL:
    def test_ttl_applied_on_write(self):
        store, repo = _make_store(ttl=3600)
        store.save("user-1", "1", URI_A)
        assert repo._client.expires.get("image:user-1:1") == 3600

    def test_non_positive_ttl_not_applied(self):
        store, repo = _make_store(ttl=0)
        store.save("user-1", "1", URI_A)
        assert "image:user-1:1" not in repo._client.expires


class TestRedisImageStoreCap:
    def test_cap_evicts_oldest_blob(self):
        store, _ = _make_store(max_per_user=2)
        store.save("user-1", "1", URI_A)
        store.save("user-1", "2", URI_B)
        store.save("user-1", "3", URI_A)
        # Oldest (id "1") evicted; newest two remain.
        assert store.get("user-1", "1") is None
        assert store.get("user-1", "2") == URI_B
        assert store.get("user-1", "3") == URI_A


class TestRedisImageStoreNextIndex:
    def test_next_index_is_monotonic_per_user(self):
        store, _ = _make_store()
        assert store.next_index("user-1") == 1
        assert store.next_index("user-1") == 2
        assert store.next_index("user-1") == 3

    def test_next_index_is_independent_per_user(self):
        store, _ = _make_store()
        assert store.next_index("user-1") == 1
        assert store.next_index("user-2") == 1


class TestRedisImageStoreLatestId:
    def test_latest_id_returns_most_recently_saved(self):
        store, _ = _make_store()
        store.save("user-1", "1", URI_A)
        store.save("user-1", "2", URI_B)
        assert store.latest_id("user-1") == "2"

    def test_latest_id_none_when_empty(self):
        store, _ = _make_store()
        assert store.latest_id("user-1") is None

    def test_latest_id_is_per_user(self):
        store, _ = _make_store()
        store.save("user-1", "1", URI_A)
        assert store.latest_id("user-2") is None
