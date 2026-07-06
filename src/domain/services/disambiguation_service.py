import json
import time
from dataclasses import dataclass
from typing import List, Optional

from domain.entities import DisambiguationCandidate, PendingDisambiguation
from domain.interfaces.data_repository import ContextRepository
from domain.services.shopping_list_service import ShoppingListService
from domain.services.text_matching import is_cancel, resolve_ordinal


@dataclass
class ChoiceResult:
    """Outcome of resolving a follow-up reply against a pending disambiguation."""

    kind: str  # "match" | "cancel" | "none"
    candidate: Optional[DisambiguationCandidate] = None


class DisambiguationService:
    """
    Persists and resolves a pending disambiguation question for a user.

    The pending state is stored as a JSON payload under
    ``disambiguation:{user_id}`` in a ContextRepository, with the TTL embedded
    in the payload (``expires_at``) — the ABC has no native TTL parameter, so
    embedding keeps behaviour identical for Redis and the in-memory fallback.
    """

    _KEY_PREFIX = "disambiguation:"

    def __init__(
        self,
        context_repository: ContextRepository,
        shopping_list_service: ShoppingListService,
        ttl_seconds: int = 120,
    ):
        self.context_repository = context_repository
        self.shopping_list_service = shopping_list_service
        self.ttl_seconds = ttl_seconds

    def _key(self, user_id: str) -> str:
        return f"{self._KEY_PREFIX}{user_id}"

    async def set_pending(
        self, user_id: str, pending: PendingDisambiguation
    ) -> None:
        """Store a pending disambiguation, stamping its expiry from the TTL."""
        pending.expires_at = time.time() + self.ttl_seconds
        payload = json.dumps(
            {
                "operation": pending.operation,
                "query": pending.query,
                "candidates": [
                    {"id": c.id, "name": c.name} for c in pending.candidates
                ],
                "expires_at": pending.expires_at,
            }
        )
        await self.context_repository.set_key(self._key(user_id), payload)

    async def get_pending(self, user_id: str) -> Optional[PendingDisambiguation]:
        """
        Load the pending disambiguation, or None when absent, malformed or
        expired. Expired entries are purged as a side effect.
        """
        raw = await self.context_repository.get_key(self._key(user_id))
        # RedisContextRepository returns the literal string "None" for a miss;
        # the in-memory repository returns Python None.
        if raw is None or raw == "None":
            return None
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return None

        pending = PendingDisambiguation(
            operation=data.get("operation", ""),
            query=data.get("query", ""),
            candidates=[
                DisambiguationCandidate(id=c.get("id", ""), name=c.get("name", ""))
                for c in data.get("candidates", [])
            ],
            expires_at=data.get("expires_at", 0.0),
        )

        if pending.expires_at and pending.expires_at < time.time():
            await self.clear_pending(user_id)
            return None

        return pending

    async def clear_pending(self, user_id: str) -> None:
        """Remove any pending disambiguation for the user."""
        await self.context_repository.delete_key(self._key(user_id))

    def resolve_choice(
        self, message: str, candidates: List[DisambiguationCandidate]
    ) -> ChoiceResult:
        """
        Resolve a follow-up reply against the candidates. Pure and synchronous.
        Precedence: cancel > ordinal > literal name; otherwise "none".

        Cancel words and ordinals are only honored in short, content-poor
        replies (the length guards in text_matching), so a long legitimate
        command that merely contains a digit or a cancel word no longer hijacks
        the choice.
        """
        if not candidates:
            return ChoiceResult(kind="none")

        if is_cancel(message):
            return ChoiceResult(kind="cancel")

        index = resolve_ordinal(message, len(candidates))
        if index is not None:
            return ChoiceResult(kind="match", candidate=candidates[index])

        matched = self.shopping_list_service.find_items_by_name(message, candidates)
        if len(matched) == 1:
            return ChoiceResult(kind="match", candidate=matched[0])

        return ChoiceResult(kind="none")
