from typing import Optional

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage

from infra.user_lock_registry import UserLockRegistry, get_user_lock_registry


class LockedInMemoryChatMessageHistory(BaseChatMessageHistory):
    """
    In-memory chat history whose writes take the per-user lock.

    LangChain's `InMemoryChatMessageHistory` takes no lock, while
    `InMemoryConversationContextStore.apply_compaction` rewrites that same object
    (read prefix -> truncate -> restore tail) while holding the user's lock. A
    request thread appending a turn in the middle of that window would have it
    erased. Drawing both writers' lock from the SAME registry closes the gap — the
    Redis backend is already symmetric (`RedisChatMessageHistory`).

    Two invariants that look like details and are not:

      - `messages` does NOT take the lock (`threading.Lock` is not reentrant and
        the compaction re-reads the history while holding it) and returns a
        SNAPSHOT, so a caller holding the returned list never watches a background
        compaction mutate it mid-turn;
      - `replace_all_unlocked` / `clear_unlocked` exist for the compaction store,
        which ALREADY holds the lock when it truncates: calling the public
        (locking) methods from there would deadlock it against itself.

    The message list is composed, not inherited, precisely because
    `InMemoryChatMessageHistory.messages` is the live pydantic field — returning
    it would break the snapshot invariant.
    """

    def __init__(
        self,
        session_id: str,
        lock_registry: Optional[UserLockRegistry] = None,
    ):
        self._session_id = session_id
        self._messages: list[BaseMessage] = []
        self._lock_registry = lock_registry or get_user_lock_registry()

    @property
    def messages(self) -> list[BaseMessage]:
        return list(self._messages)

    def add_messages(self, messages: list[BaseMessage]) -> None:
        with self._lock_registry.get(self._session_id):
            self._messages.extend(messages)

    def clear(self) -> None:
        with self._lock_registry.get(self._session_id):
            self._messages = []

    def replace_all_unlocked(self, messages: list[BaseMessage]) -> None:
        """Replace the whole array. The caller MUST already hold the user's lock."""
        self._messages = list(messages)

    def clear_unlocked(self) -> None:
        """Empty the history. The caller MUST already hold the user's lock."""
        self._messages = []
