"""
RedisImageStore Integration Tests (Fase B) — exercises the real Redis client
and the project's async_runner facade (not a mock ContextRepository).

Skips gracefully when no test Redis is reachable, so the suite stays green in
environments without Redis.
"""

import os
import uuid

import pytest

from infra.data.external.redis.redis_image_store import RedisImageStore
from infra.data.sqlite.context_repository_redis import RedisContextRepository


pytestmark = pytest.mark.integration


TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")

URI_A = "data:image/png;base64,aGVsbG8="
URI_B = "data:image/jpeg;base64,d29ybGQ="
URI_C = "data:image/webp;base64,Zm9vYmFy"


def _cleanup(user_id: str) -> None:
    from redis import from_url

    client = from_url(TEST_REDIS_URL)
    try:
        for pattern in (
            f"image:{user_id}:*",
            f"image_ids:{user_id}",
            f"image_seq:{user_id}",
        ):
            for key in client.scan_iter(pattern):
                client.delete(key)
    finally:
        client.close()


@pytest.fixture
def image_store():
    from redis import from_url
    from redis.exceptions import RedisError

    client = from_url(TEST_REDIS_URL)
    try:
        client.ping()
    except (RedisError, OSError) as exc:
        pytest.skip(f"Test Redis not reachable at {TEST_REDIS_URL}: {exc}")
    finally:
        client.close()

    repo = RedisContextRepository(TEST_REDIS_URL)
    yield RedisImageStore(repo, ttl_seconds=3600, max_per_user=3)


class TestRedisImageStoreIntegration:
    def test_save_then_get_round_trip(self, image_store):
        user_id = str(uuid.uuid4())
        try:
            image_store.save(user_id, "1", URI_A)
            assert image_store.get(user_id, "1") == URI_A
        finally:
            _cleanup(user_id)

    def test_get_unknown_returns_none(self, image_store):
        user_id = str(uuid.uuid4())
        try:
            assert image_store.get(user_id, "999") is None
        finally:
            _cleanup(user_id)

    def test_cross_user_isolation(self, image_store):
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())
        try:
            image_store.save(user_a, "1", URI_A)
            assert image_store.get(user_b, "1") is None
        finally:
            _cleanup(user_a)
            _cleanup(user_b)

    def test_next_index_monotonic_then_latest_id(self, image_store):
        user_id = str(uuid.uuid4())
        try:
            n1 = image_store.next_index(user_id)
            n2 = image_store.next_index(user_id)
            assert (n1, n2) == (1, 2)
            image_store.save(user_id, str(n1), URI_A)
            image_store.save(user_id, str(n2), URI_B)
            assert image_store.latest_id(user_id) == str(n2)
        finally:
            _cleanup(user_id)

    def test_cap_evicts_oldest(self, image_store):
        user_id = str(uuid.uuid4())
        try:
            image_store.save(user_id, "1", URI_A)
            image_store.save(user_id, "2", URI_B)
            image_store.save(user_id, "3", URI_C)
            image_store.save(user_id, "4", URI_A)  # cap is 3 → id "1" evicted
            assert image_store.get(user_id, "1") is None
            assert image_store.get(user_id, "4") == URI_A
        finally:
            _cleanup(user_id)
