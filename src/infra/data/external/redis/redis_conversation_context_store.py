import json
import logging
from datetime import datetime
from typing import Optional

from domain.interfaces.data_repository import (
    ContextRepository,
    ConversationContextStore,
)
from domain.services.conversation_digest import conversation_digest
from infra import async_runner
from infra.user_lock_registry import UserLockRegistry, get_user_lock_registry

logger = logging.getLogger(__name__)


class RedisConversationContextStore(ConversationContextStore):
    """
    Redis-backed conversation context: the history array written by
    `RedisChatMessageHistory` (`chat_history:{user_id}`) plus the compaction
    summary (`chat_summary:{user_id}`), both sharing the same TTL.

    Reads are fail-safe (corrupt value -> "nothing compacted yet") because the
    caller is a background task whose only acceptable failure mode is "did not
    compact", never "lost the history".
    """

    def __init__(
        self,
        context_repo: ContextRepository,
        ttl_seconds: Optional[int] = None,
        lock_registry: Optional[UserLockRegistry] = None,
    ):
        self._repo = context_repo
        self._ttl = ttl_seconds
        self._lock_registry = lock_registry or get_user_lock_registry()

    def get_summary(self, user_id: str) -> Optional[dict]:
        # No lock: only `apply_compaction` and `clear` mutate, and they re-read
        # under the lock themselves (which a non-reentrant Lock taken here would
        # deadlock).
        return self._read_summary(user_id)

    def read_history(self, user_id: str) -> list[dict]:
        return self._read_history(user_id)

    def apply_compaction(
        self,
        user_id: str,
        expected_count: int,
        expected_digest: str,
        summary: str,
    ) -> bool:
        with self._lock_registry.get(user_id):
            # Re-read INSIDE the lock: the snapshot the caller verified against
            # was taken before the (slow) LLM call, with no lock held.
            current = self._read_history(user_id)
            if len(current) < expected_count:
                return False
            if conversation_digest(current[: expected_count]) != expected_digest:
                return False

            envelope = self._build_envelope(user_id, expected_count, summary)
            tail = current[expected_count:]

            # Summary and tail go out in ONE transaction: the intermediate state
            # "history truncated, summary not written" is unrecoverable loss.
            pipeline = self._repo._get_client().pipeline()
            pipeline.set(self._history_key(user_id), json.dumps(tail))
            pipeline.set(self._summary_key(user_id), json.dumps(envelope))
            if self._ttl is not None and self._ttl > 0:
                pipeline.expire(self._history_key(user_id), self._ttl)
                pipeline.expire(self._summary_key(user_id), self._ttl)
            async_runner.run(pipeline.execute())
            return True

    def clear(self, user_id: str) -> None:
        # Under the lock, so a concurrent CAS cannot land between the two deletes
        # and rewrite the history the user just reset.
        with self._lock_registry.get(user_id):
            async_runner.run(self._repo.delete_key(self._history_key(user_id)))
            async_runner.run(self._repo.delete_key(self._summary_key(user_id)))

    def _history_key(self, user_id: str) -> str:
        return f"chat_history:{user_id}"

    def _summary_key(self, user_id: str) -> str:
        return f"chat_summary:{user_id}"

    def _read_history(self, user_id: str) -> list[dict]:
        raw = async_runner.run(self._repo.get_key(self._history_key(user_id)))
        if not raw or raw == "None":
            return []
        try:
            history = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning("Corrupt chat history for user %s; ignoring it.", user_id)
            return []
        if not isinstance(history, list):
            return []
        return history

    def _read_summary(self, user_id: str) -> Optional[dict]:
        raw = async_runner.run(self._repo.get_key(self._summary_key(user_id)))
        if not raw or raw == "None":
            return None
        try:
            envelope = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning("Corrupt chat summary for user %s; ignoring it.", user_id)
            return None
        if not isinstance(envelope, dict) or not envelope.get("summary"):
            return None
        return envelope

    def _build_envelope(self, user_id: str, expected_count: int, summary: str) -> dict:
        # `covers` is cumulative: the new summary also stands for everything the
        # previous one covered (the raw prefix is physically dropped).
        previous = self._read_summary(user_id)
        previous_covers = previous.get("covers") if previous else None
        if not isinstance(previous_covers, int) or previous_covers < 0:
            previous_covers = 0
        return {
            "summary": summary,
            "covers": previous_covers + expected_count,
            "updated_at": datetime.now().isoformat(),
        }
