"""
RedisConversationContextStore Integration Tests (Fase F) — real Redis.

The unit tests prove the CAS logic against a fake repository. What they cannot
prove is that the store and `RedisChatMessageHistory` actually agree on the wire:
same key, same JSON serialization, same lock registry. That agreement is the
whole feature — a mismatch means the compaction truncates an array nobody reads,
or reads an array nobody writes.

So every test here goes through the REAL history object to write and the REAL
store to read/compact, and verifies the resulting Redis keys with a plain Redis
client.

Skips gracefully (via `redis_backed_env`) when no test Redis is reachable.
No Ollama needed: the summary text is supplied directly, not generated.
"""

import json
import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from domain.services.conversation_digest import conversation_digest
from infra.data.external.redis.redis_chat_message_history import RedisChatMessageHistory
from infra.data.external.redis.redis_conversation_context_store import (
    RedisConversationContextStore,
)
from infra.data.sqlite.context_repository_redis import RedisContextRepository


pytestmark = pytest.mark.integration


SUMMARY = "### Assuntos em andamento\n- O usuário planeja uma viagem."


def _history_key(user_id: str) -> str:
    return f"chat_history:{user_id}"


def _summary_key(user_id: str) -> str:
    return f"chat_summary:{user_id}"


@pytest.fixture
def redis_client(redis_backed_env):
    from redis import from_url

    client = from_url(redis_backed_env, decode_responses=True)
    yield client
    client.close()


@pytest.fixture
def context_repo(redis_backed_env):
    return RedisContextRepository(redis_backed_env)


@pytest.fixture
def store(context_repo):
    return RedisConversationContextStore(context_repo, ttl_seconds=None)


@pytest.fixture
def history_for(context_repo):
    """Builds the REAL RedisChatMessageHistory the app writes turns through."""

    def _factory(user_id: str) -> RedisChatMessageHistory:
        return RedisChatMessageHistory(user_id, context_repo, None)

    return _factory


@pytest.fixture
def user_id():
    return str(uuid.uuid4())


def _seed(history, n_turns: int, tag: str = "") -> None:
    for i in range(n_turns):
        history.add_messages(
            [
                HumanMessage(content=f"pergunta {tag}{i}"),
                AIMessage(content=f"resposta {tag}{i}"),
            ]
        )


class TestRedisRoundTrip:
    def test_read_history__written_by_chat_message_history__reads_same_turns(
        self, store, history_for, user_id
    ):
        # Arrange — write through the real history object (what LlmAppService uses).
        history = history_for(user_id)
        history.add_messages(
            [HumanMessage(content="oi"), AIMessage(content="olá!")]
        )

        # Act — read through the store (what the compaction uses).
        read = store.read_history(user_id)

        # Assert — same key, same serialization: the two sides agree on the wire.
        assert read == [
            {"type": "human", "content": "oi"},
            {"type": "ai", "content": "olá!"},
        ]

    def test_read_history__no_key__returns_empty_list(self, store, user_id):
        assert store.read_history(user_id) == []

    def test_get_summary__nothing_compacted__returns_none(self, store, user_id):
        assert store.get_summary(user_id) is None


class TestRedisApplyCompaction:
    def test_apply_compaction__turn_appended_during_llm_call__keeps_appended_turn(
        self, store, history_for, redis_client, user_id
    ):
        # Arrange — 6 messages, snapshot the 4-message prefix (as the app service
        # does BEFORE the slow LLM call, with no lock held).
        history = history_for(user_id)
        _seed(history, n_turns=3)
        snapshot = store.read_history(user_id)
        assert len(snapshot) == 6
        prefix = snapshot[:4]
        digest = conversation_digest(prefix)

        # ...and now the user sends another turn WHILE the LLM is summarizing.
        history.add_messages(
            [
                HumanMessage(content="chegou durante o LLM"),
                AIMessage(content="respondi durante o LLM"),
            ]
        )

        # Act — CAS against the snapshot taken before the append.
        applied = store.apply_compaction(user_id, len(prefix), digest, SUMMARY)

        # Assert — the append does NOT invalidate the CAS: it only touched the
        # tail, and the prefix being summarized is immutable (append-only
        # history). Aborting here would starve compaction on a chatty user.
        assert applied is True

        remaining = store.read_history(user_id)
        assert len(remaining) == 4, (
            f"Expected the 2 untouched tail messages + the 2 appended, got: {remaining}"
        )
        contents = [m["content"] for m in remaining]
        assert "chegou durante o LLM" in contents, (
            "The turn appended during the LLM call was clobbered by the compaction"
        )
        assert "respondi durante o LLM" in contents
        # The prefix really went away.
        assert "pergunta 0" not in contents

        # Summary landed in its own key, in the same transaction.
        assert store.get_summary(user_id)["summary"] == SUMMARY
        assert redis_client.exists(_summary_key(user_id)) == 1

    def test_apply_compaction__prefix_changed_between_snapshot_and_cas__aborts(
        self, store, history_for, redis_client, user_id
    ):
        # Arrange — snapshot a prefix, then wipe and rewrite the history with
        # DIFFERENT content (a reset_context landing mid-compaction).
        history = history_for(user_id)
        _seed(history, n_turns=3, tag="old-")
        snapshot = store.read_history(user_id)
        prefix = snapshot[:4]
        digest = conversation_digest(prefix)

        history.clear()
        _seed(history, n_turns=3, tag="new-")
        before_cas = store.read_history(user_id)

        # Act — the digest of the current prefix no longer matches the snapshot.
        applied = store.apply_compaction(user_id, len(prefix), digest, SUMMARY)

        # Assert — abort, and NOTHING was touched: not the history...
        assert applied is False
        assert store.read_history(user_id) == before_cas, (
            "An aborted CAS must leave the history byte-for-byte untouched"
        )
        # ...and not the summary key (a summary covering messages that are still
        # in the array would be duplicated into every future prompt).
        assert store.get_summary(user_id) is None
        assert redis_client.exists(_summary_key(user_id)) == 0

    def test_apply_compaction__history_cleared_between_snapshot_and_cas__aborts(
        self, store, history_for, redis_client, user_id
    ):
        # Arrange — snapshot, then the history is gone entirely.
        history = history_for(user_id)
        _seed(history, n_turns=3)
        prefix = store.read_history(user_id)[:4]
        digest = conversation_digest(prefix)

        history.clear()

        # Act — current history (0 messages) is shorter than the expected prefix.
        applied = store.apply_compaction(user_id, len(prefix), digest, SUMMARY)

        # Assert — abort; the reset the user asked for is not resurrected.
        assert applied is False
        assert store.read_history(user_id) == []
        assert redis_client.exists(_history_key(user_id)) == 0
        assert redis_client.exists(_summary_key(user_id)) == 0

    def test_apply_compaction__written_tail__is_readable_by_chat_message_history(
        self, store, history_for, user_id
    ):
        # Arrange
        history = history_for(user_id)
        _seed(history, n_turns=3)
        prefix = store.read_history(user_id)[:4]

        # Act
        applied = store.apply_compaction(
            user_id, len(prefix), conversation_digest(prefix), SUMMARY
        )

        # Assert — the tail the store wrote round-trips back through the history
        # object (the OnlyTalkGraph reader). A serialization drift here would
        # turn every AI turn into a HumanMessage.
        assert applied is True
        messages = history_for(user_id).messages
        assert len(messages) == 2
        assert isinstance(messages[0], HumanMessage)
        assert isinstance(messages[1], AIMessage)
        assert messages[0].content == "pergunta 2"
        assert messages[1].content == "resposta 2"


class TestRedisClear:
    def test_clear__removes_both_history_and_summary_keys(
        self, store, history_for, redis_client, user_id
    ):
        # Arrange — a compacted conversation: both keys exist in Redis.
        history = history_for(user_id)
        _seed(history, n_turns=3)
        prefix = store.read_history(user_id)[:4]
        assert store.apply_compaction(
            user_id, len(prefix), conversation_digest(prefix), SUMMARY
        )
        assert redis_client.exists(_history_key(user_id)) == 1
        assert redis_client.exists(_summary_key(user_id)) == 1

        # Act
        store.clear(user_id)

        # Assert — verified with a plain Redis client, not through the store:
        # a reset that left the summary behind would have Peruca "remembering" a
        # conversation the user asked to erase.
        assert redis_client.exists(_history_key(user_id)) == 0
        assert redis_client.exists(_summary_key(user_id)) == 0
        assert store.read_history(user_id) == []
        assert store.get_summary(user_id) is None

    def test_clear__cross_user_isolation(
        self, store, history_for, redis_client, user_id
    ):
        # Arrange — two users, both with a history.
        other_id = str(uuid.uuid4())
        _seed(history_for(user_id), n_turns=1)
        _seed(history_for(other_id), n_turns=1)

        # Act
        store.clear(user_id)

        # Assert — only the target user's keys are gone.
        assert redis_client.exists(_history_key(user_id)) == 0
        assert redis_client.exists(_history_key(other_id)) == 1
        assert len(store.read_history(other_id)) == 2


class TestRedisSummaryEnvelope:
    def test_apply_compaction__envelope_shape_on_the_wire(
        self, store, history_for, redis_client, user_id
    ):
        # Arrange
        history = history_for(user_id)
        _seed(history, n_turns=3)
        prefix = store.read_history(user_id)[:4]

        # Act
        store.apply_compaction(
            user_id, len(prefix), conversation_digest(prefix), SUMMARY
        )

        # Assert — the raw value is the JSON envelope the ABC documents.
        envelope = json.loads(redis_client.get(_summary_key(user_id)))
        assert envelope["summary"] == SUMMARY
        assert envelope["covers"] == 4
        assert envelope["updated_at"]
