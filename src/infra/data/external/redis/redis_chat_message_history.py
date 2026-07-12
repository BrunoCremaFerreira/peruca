import json
from typing import Optional

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage

from domain.interfaces.data_repository import ContextRepository
from infra import async_runner
from infra.data.chat_message_serialization import (
    deserialize_messages,
    serialize_messages,
)
from infra.user_lock_registry import UserLockRegistry, get_user_lock_registry


class RedisChatMessageHistory(BaseChatMessageHistory):

    def __init__(
        self,
        session_id: str,
        context_repo: ContextRepository,
        ttl_seconds: Optional[int] = None,
        lock_registry: Optional[UserLockRegistry] = None,
    ):
        self._session_id = session_id
        self._key = f"chat_history:{session_id}"
        # The very key RedisConversationContextStore writes the compaction
        # summary to; kept in sync with `_summary_key` there.
        self._summary_key = f"chat_summary:{session_id}"
        self._repo = context_repo
        self._ttl = ttl_seconds
        self._lock_registry = lock_registry or get_user_lock_registry()

    @property
    def key(self) -> str:
        return self._key

    @property
    def summary_key(self) -> str:
        return self._summary_key

    def _get_client(self):
        return self._repo._get_client()

    @property
    def messages(self) -> list[BaseMessage]:
        # No lock here on purpose: `add_messages` reads through this property
        # while holding the (non-reentrant) per-user lock — locking it too would
        # deadlock every write against itself.
        raw = async_runner.run(self._repo.get_key(self._key))
        if not raw or raw == "None":
            return []
        return deserialize_messages(json.loads(raw))

    def add_messages(self, messages: list[BaseMessage]) -> None:
        # The whole read-modify-write runs under the per-user lock, which the
        # compaction CAS also takes: without it, a compaction rewriting the key
        # can clobber the turn appended here.
        with self._lock_registry.get(self._session_id):
            current = self.messages
            all_messages = current + list(messages)
            serialized = json.dumps(serialize_messages(all_messages))
            async_runner.run(self._repo.set_key(self._key, serialized))
            # A non-positive TTL is treated as "no expiry". Redis `EXPIRE key 0`
            # (or a negative value) deletes the key immediately, which would wipe
            # the conversation history on every write and make the bot forget the
            # previous message.
            #
            # The summary is renewed on the SAME write: it is only (re)written by
            # a compaction — roughly once every seven turns, and never again for a
            # user who stopped triggering one — so letting it expire before the
            # history would permanently lose the compacted (and already deleted)
            # prefix. EXPIRE on a missing key is a harmless no-op.
            if self._ttl is not None and self._ttl > 0:
                client = self._get_client()
                async_runner.run(client.expire(self._key, self._ttl))
                async_runner.run(client.expire(self._summary_key, self._ttl))

    def clear(self) -> None:
        with self._lock_registry.get(self._session_id):
            async_runner.run(self._repo.delete_key(self._key))
