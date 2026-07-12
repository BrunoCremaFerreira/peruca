import hashlib
import json


def conversation_digest(messages: list[dict]) -> str:
    """
    Fingerprint a serialized chat history so the compaction can swap a prefix
    for its summary safely (verify-before-swap / logical CAS).

    The compaction snapshots the prefix it is about to summarize, then calls the
    LLM outside of any lock. Seconds later, the store re-reads the history under
    the per-user lock and compares this digest against the one taken at snapshot
    time: it only rewrites the history when they still match. A mismatch means a
    `reset_context` or a concurrent compaction changed the prefix in between, and
    the compaction is discarded instead of destroying turns.

    The digest is a pure function of the ordered (type, content) pairs, so it is
    sensitive to content, message type and order, while remaining insensitive to
    dict key insertion order (the store re-reads from Redis and never gets the
    same objects back). Contents are serialized as JSON rather than concatenated,
    so histories like ["ab", ""] and ["a", "b"] cannot collide.
    """
    payload = [
        {"type": message.get("type"), "content": message.get("content")}
        for message in messages
    ]
    serialized = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
