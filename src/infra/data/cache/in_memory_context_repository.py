from typing import Dict, Optional

from domain.interfaces.data_repository import ContextRepository


class InMemoryContextRepository(ContextRepository):
    """
    Process-local, in-memory ContextRepository used as the fallback when no
    Redis (CACHE_DB_CONNECTION_STRING) is configured. Mirrors the async
    contract so features depending on ContextRepository (e.g. disambiguation)
    work without an external cache. State lives for the lifetime of the process.
    """

    def __init__(self):
        self._store: Dict[str, str] = {}

    def connect(self) -> None:
        # Nothing to connect to; kept for interface parity with Redis.
        pass

    async def set_key(self, key: str, value: str) -> None:
        self._store[key] = value

    async def get_key(self, key: str) -> Optional[str]:
        return self._store.get(key)

    async def delete_key(self, key: str) -> bool:
        return self._store.pop(key, None) is not None
