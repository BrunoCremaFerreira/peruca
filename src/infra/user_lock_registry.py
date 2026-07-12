"""Per-user in-process locks shared by every writer of a user's chat context.

`RedisChatMessageHistory.add_messages` and `ConversationContextStore.apply_compaction`
are both read-modify-write cycles over the same `chat_history:{user_id}` value.
Interleaved, the compaction's rewrite can clobber a turn that was just appended
(permanent data loss), so both take THE SAME lock for a given user — which is only
possible when they draw it from a shared registry.

Locks are per user_id: one user's compaction never blocks another user's turn.

Single-process assumption (plan §3.5): these are `threading.Lock`s, so they
serialise nothing across workers. A multi-worker deployment must move the CAS to
a Redis-side script.
"""

import threading


class UserLockRegistry:
    """Hands out one lock per user_id, creating it on first use."""

    def __init__(self):
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def get(self, user_id: str) -> threading.Lock:
        lock = self._locks.get(user_id)
        if lock is not None:
            return lock
        with self._guard:
            if user_id not in self._locks:
                self._locks[user_id] = threading.Lock()
            return self._locks[user_id]


_default_registry = UserLockRegistry()


def get_user_lock_registry() -> UserLockRegistry:
    """The process-wide registry used when no registry is injected."""
    return _default_registry
