"""
get_image_store factory unit tests (TDD - RED phase, Fase B).

  - Redis configured  → returns a RedisImageStore.
  - No CACHE_DB_CONNECTION_STRING → returns None (re-vision disabled; NOT an
    in-memory store, which would balloon RAM with base64 and not survive across
    workers).

Expected to FAIL until get_image_store exists.
"""

import os
from unittest.mock import patch

from infra.ioc import get_image_store
from infra.data.external.redis.redis_image_store import RedisImageStore


class TestGetImageStore:
    def test_with_redis_configured__returns_redis_image_store(self):
        with patch.dict(
            os.environ, {"CACHE_DB_CONNECTION_STRING": "redis://localhost:6379/0"}
        ):
            store = get_image_store()
        assert isinstance(store, RedisImageStore)

    def test_without_redis__returns_none(self):
        with patch.dict(os.environ, {"CACHE_DB_CONNECTION_STRING": ""}):
            store = get_image_store()
        assert store is None
