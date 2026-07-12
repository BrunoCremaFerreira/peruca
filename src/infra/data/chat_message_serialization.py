"""Mapping between langchain messages and the serialized history form.

The serialized form — [{"type": "human"|"ai", "content": str}] — is what the
history is stored as and what `ConversationContextStore` (domain) speaks, so both
the Redis and the in-memory backends map through here.
"""

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


def serialize_messages(messages: list[BaseMessage]) -> list[dict]:
    result = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            result.append({"type": "human", "content": msg.content})
        elif isinstance(msg, AIMessage):
            result.append({"type": "ai", "content": msg.content})
        else:
            result.append({"type": msg.type, "content": msg.content})
    return result


def deserialize_messages(data: list[dict]) -> list[BaseMessage]:
    result = []
    for item in data:
        msg_type = item.get("type", "")
        content = item.get("content", "")
        if msg_type == "ai":
            result.append(AIMessage(content=content))
        else:
            result.append(HumanMessage(content=content))
    return result
