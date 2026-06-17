import json
from typing import Optional

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from domain.interfaces.data_repository import ContextRepository
from infra import async_runner


def _serialize_messages(messages: list[BaseMessage]) -> list[dict]:
    result = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            result.append({"type": "human", "content": msg.content})
        elif isinstance(msg, AIMessage):
            result.append({"type": "ai", "content": msg.content})
        else:
            result.append({"type": msg.type, "content": msg.content})
    return result


def _deserialize_messages(data: list[dict]) -> list[BaseMessage]:
    result = []
    for item in data:
        msg_type = item.get("type", "")
        content = item.get("content", "")
        if msg_type == "human":
            result.append(HumanMessage(content=content))
        elif msg_type == "ai":
            result.append(AIMessage(content=content))
        else:
            result.append(HumanMessage(content=content))
    return result


class RedisChatMessageHistory(BaseChatMessageHistory):

    def __init__(
        self,
        session_id: str,
        context_repo: ContextRepository,
        ttl_seconds: Optional[int] = None,
    ):
        self._key = f"chat_history:{session_id}"
        self._repo = context_repo
        self._ttl = ttl_seconds

    @property
    def key(self) -> str:
        return self._key

    def _get_client(self):
        return self._repo._get_client()

    @property
    def messages(self) -> list[BaseMessage]:
        raw = async_runner.run(self._repo.get_key(self._key))
        if not raw or raw == "None":
            return []
        return _deserialize_messages(json.loads(raw))

    def add_messages(self, messages: list[BaseMessage]) -> None:
        current = self.messages
        all_messages = current + list(messages)
        serialized = json.dumps(_serialize_messages(all_messages))
        async_runner.run(self._repo.set_key(self._key, serialized))
        # A non-positive TTL is treated as "no expiry". Redis `EXPIRE key 0`
        # (or a negative value) deletes the key immediately, which would wipe
        # the conversation history on every write and make the bot forget the
        # previous message.
        if self._ttl is not None and self._ttl > 0:
            async_runner.run(self._get_client().expire(self._key, self._ttl))

    def clear(self) -> None:
        async_runner.run(self._repo.delete_key(self._key))
