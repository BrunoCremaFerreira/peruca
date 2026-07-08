"""
FlowStateStore — the generic, mechanical persistence behind a multi-turn flow.

It stores two JSON payloads per user in a ContextRepository, each with an embedded
TTL: a "pending" slot (the operation awaiting the user's next reply) and a "focus"
slot (the record a query last reported on, so a follow-up can target it). The store
is deliberately dumb about payload shape — the domain-specific serialization of
``operation``/``slots``/``candidates`` stays the caller's responsibility. The store
only injects/enforces the TTL and (de)serializes JSON, keyed by ``user_id``.
"""

import json
import time
from typing import Optional

from domain.interfaces.data_repository import ContextRepository


class FlowStateStore:
    def __init__(
        self,
        context_repository: ContextRepository,
        key_prefix: str,
        focus_prefix: str,
        ttl_seconds: int = 600,
    ):
        self.context_repository = context_repository
        self.key_prefix = key_prefix
        self.focus_prefix = focus_prefix
        self.ttl_seconds = ttl_seconds

    def _key(self, user_id: str) -> str:
        return f"{self.key_prefix}{user_id}"

    def _focus_key(self, user_id: str) -> str:
        return f"{self.focus_prefix}{user_id}"

    async def _get_with_ttl(self, key: str, clear) -> Optional[dict]:
        raw = await self.context_repository.get_key(key)
        if raw is None or raw == "None":
            return None
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return None
        expires_at = data.get("expires_at", 0.0)
        if expires_at and expires_at < time.time():
            await clear()
            return None
        return data

    # ------------------------------------------------------------------ #
    # Pending
    # ------------------------------------------------------------------ #
    async def set_pending(self, user_id: str, payload: dict) -> None:
        stored = dict(payload)
        stored["expires_at"] = time.time() + self.ttl_seconds
        await self.context_repository.set_key(self._key(user_id), json.dumps(stored))

    async def get_pending_raw(self, user_id: str) -> Optional[dict]:
        return await self._get_with_ttl(
            self._key(user_id), lambda: self.clear_pending(user_id)
        )

    async def clear_pending(self, user_id: str) -> None:
        await self.context_repository.delete_key(self._key(user_id))

    # ------------------------------------------------------------------ #
    # Focus
    # ------------------------------------------------------------------ #
    async def set_focus(self, user_id: str, focus: dict) -> None:
        stored = dict(focus)
        stored["expires_at"] = time.time() + self.ttl_seconds
        await self.context_repository.set_key(
            self._focus_key(user_id), json.dumps(stored)
        )

    async def get_focus(self, user_id: str) -> Optional[dict]:
        return await self._get_with_ttl(
            self._focus_key(user_id), lambda: self.clear_focus(user_id)
        )

    async def clear_focus(self, user_id: str) -> None:
        await self.context_repository.delete_key(self._focus_key(user_id))
