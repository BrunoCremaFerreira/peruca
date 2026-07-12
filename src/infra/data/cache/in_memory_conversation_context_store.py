import logging
from datetime import datetime
from typing import Optional

from langchain_core.chat_history import InMemoryChatMessageHistory

from domain.interfaces.data_repository import ConversationContextStore
from domain.services.conversation_digest import conversation_digest
from infra.data.chat_message_serialization import serialize_messages
from infra.user_lock_registry import UserLockRegistry, get_user_lock_registry

logger = logging.getLogger(__name__)


class InMemoryConversationContextStore(ConversationContextStore):
    """
    Fallback store used when no Redis is configured.

    `history_store` is INJECTED and is the very dict `ioc._get_session_history_factory()`
    closes over ({session_id: InMemoryChatMessageHistory}). A dict of its own would
    make the compaction truncate a history nobody reads, while `OnlyTalkGraph` kept
    seeing the full array.

    Summaries live in a plain dict — a per-user value object with no TTL, matching
    the (also unbounded) in-memory history.
    """

    def __init__(
        self,
        history_store: dict[str, InMemoryChatMessageHistory],
        lock_registry: Optional[UserLockRegistry] = None,
    ):
        self._history_store = history_store
        self._summaries: dict[str, dict] = {}
        self._lock_registry = lock_registry or get_user_lock_registry()

    def get_summary(self, user_id: str) -> Optional[dict]:
        # No lock: `apply_compaction` re-reads the history while holding the
        # (non-reentrant) per-user lock, so any read that took it would deadlock
        # the CAS against itself.
        return self._summaries.get(user_id)

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
            # Re-read INSIDE the lock: the caller snapshotted the prefix before
            # the (slow) LLM call, with no lock held.
            history = self._history_store.get(user_id)
            if history is None:
                return False
            current = self._read_history(user_id)
            if len(current) < expected_count:
                return False
            if conversation_digest(current[: expected_count]) != expected_digest:
                return False

            # Truncate the SAME history object — OnlyTalkGraph may already hold a
            # reference to it — keeping the tail as it is NOW (turns appended
            # while the LLM was summarizing must survive).
            tail = list(history.messages[expected_count:])
            self._replace_all(history, tail)
            self._summaries[user_id] = self._build_envelope(
                user_id, expected_count, summary
            )
            return True

    def clear(self, user_id: str) -> None:
        # Under the lock, so a concurrent CAS cannot rewrite the history this
        # reset just wiped.
        with self._lock_registry.get(user_id):
            history = self._history_store.get(user_id)
            if history is not None:
                self._clear_history(history)
            self._summaries.pop(user_id, None)

    def _replace_all(self, history, messages: list) -> None:
        # `LockedInMemoryChatMessageHistory` takes the per-user lock in its public
        # writers — the very lock this store is already holding — so it must be
        # mutated through the lock-free primitives (threading.Lock is not
        # reentrant: going through clear()/add_messages() would deadlock the
        # compaction against itself). A raw InMemoryChatMessageHistory locks
        # nothing, so its public methods stay safe to call.
        replace_all_unlocked = getattr(history, "replace_all_unlocked", None)
        if replace_all_unlocked is not None:
            replace_all_unlocked(messages)
            return
        history.clear()
        history.add_messages(messages)

    def _clear_history(self, history) -> None:
        clear_unlocked = getattr(history, "clear_unlocked", None)
        if clear_unlocked is not None:
            clear_unlocked()
            return
        history.clear()

    def _read_history(self, user_id: str) -> list[dict]:
        history = self._history_store.get(user_id)
        if history is None:
            return []
        return serialize_messages(history.messages)

    def _build_envelope(self, user_id: str, expected_count: int, summary: str) -> dict:
        # `covers` is cumulative: the new summary also stands for everything the
        # previous one covered (the raw prefix is physically dropped).
        previous = self._summaries.get(user_id)
        previous_covers = previous.get("covers") if previous else None
        if not isinstance(previous_covers, int) or previous_covers < 0:
            previous_covers = 0
        return {
            "summary": summary,
            "covers": previous_covers + expected_count,
            "updated_at": datetime.now().isoformat(),
        }
