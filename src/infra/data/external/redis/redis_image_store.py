import json
from typing import Optional

from domain.interfaces.data_repository import ContextRepository, ImageStore
from infra import async_runner


class RedisImageStore(ImageStore):
    """
    Redis-backed ImageStore. Synchronous facade over async_runner (mirrors
    RedisChatMessageHistory), built on a ContextRepository.

    Keys (all namespaced per user so an id never resolves cross-user):
      - blob:  ``image:{user_id}:{image_id}``  → the full data URI
      - index: ``image_ids:{user_id}``         → JSON list of live ids (oldest
               first) used to enforce the per-user cap
      - seq:   ``image_seq:{user_id}``         → monotonic counter behind
               ``next_index`` (the stable ``#N`` handle)
    """

    def __init__(
        self,
        context_repo: ContextRepository,
        ttl_seconds: Optional[int] = None,
        max_per_user: int = 10,
    ):
        self._repo = context_repo
        self._ttl = ttl_seconds
        self._max_per_user = max_per_user

    # ===============================================
    # Public (ImageStore)
    # ===============================================

    def save(self, user_id: str, image_id: str, data_uri: str) -> None:
        blob_key = self._blob_key(user_id, image_id)
        async_runner.run(self._repo.set_key(blob_key, data_uri))
        self._expire(blob_key)

        index = self._load_index(user_id)
        if image_id in index:
            index.remove(image_id)
        index.append(image_id)
        while len(index) > self._max_per_user:
            oldest = index.pop(0)
            async_runner.run(self._repo.delete_key(self._blob_key(user_id, oldest)))
        index_key = self._index_key(user_id)
        async_runner.run(self._repo.set_key(index_key, json.dumps(index)))
        self._expire(index_key)

    def get(self, user_id: str, image_id: str) -> Optional[str]:
        raw = async_runner.run(self._repo.get_key(self._blob_key(user_id, image_id)))
        if not raw or raw == "None":
            return None
        return raw

    def next_index(self, user_id: str) -> int:
        seq_key = self._seq_key(user_id)
        value = async_runner.run(self._repo._get_client().incr(seq_key))
        self._expire(seq_key)
        return int(value)

    def latest_id(self, user_id: str) -> Optional[str]:
        index = self._load_index(user_id)
        return index[-1] if index else None

    # ===============================================
    # Private
    # ===============================================

    def _blob_key(self, user_id: str, image_id: str) -> str:
        return f"image:{user_id}:{image_id}"

    def _index_key(self, user_id: str) -> str:
        return f"image_ids:{user_id}"

    def _seq_key(self, user_id: str) -> str:
        return f"image_seq:{user_id}"

    def _load_index(self, user_id: str) -> list[str]:
        raw = async_runner.run(self._repo.get_key(self._index_key(user_id)))
        if not raw or raw == "None":
            return []
        try:
            value = json.loads(raw)
            return value if isinstance(value, list) else []
        except (ValueError, TypeError):
            return []

    def _expire(self, key: str) -> None:
        # A non-positive TTL means "no expiry" (see RedisChatMessageHistory).
        if self._ttl is not None and self._ttl > 0:
            async_runner.run(self._repo._get_client().expire(key, self._ttl))
