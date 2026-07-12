"""
Conversation digest unit tests — Phase A / F1 (TDD RED phase).

Drives a pure helper used by the compaction CAS (plan §3.4 step 2 / §3.5): before
the (slow) LLM call, `ContextCompactionAppService` snapshots the prefix it is
about to summarize as `len(prefix)` + a digest of it. When the summary comes back
(seconds later), `ConversationContextStore.apply_compaction` re-reads the history
under the per-user lock and only swaps the prefix for the summary when the count
AND the digest still match — otherwise a `reset_context` or a concurrent
compaction happened in between and the compaction is discarded.

Contract driven here:

    domain/services/conversation_digest.py

    def conversation_digest(messages: list[dict]) -> str

  - `messages` is the SERIALIZED form of the history, exactly as
    `RedisChatMessageHistory` stores it: [{"type": "human"|"ai", "content": str}].
  - Returns a non-empty hexdigest string.
  - Deterministic: the same messages always produce the same digest, across
    calls and across equal-but-distinct list/dict objects (the store re-reads
    from Redis, so it never gets the *same* objects back).
  - Sensitive to content, to the message type and to the order — any of those
    changing means the prefix is no longer the one that was summarized, and the
    swap MUST abort.
  - The empty list yields a stable digest and never raises (a history cleared
    between the snapshot and the swap must be a mismatch, not a crash).
  - Purely a function of the (type, content) pairs: the dict key insertion order
    is irrelevant, so a mismatch can never be a false alarm caused by JSON key
    ordering.

Written BEFORE the implementation, so these tests are expected to FAIL RED with
ImportError (the module does not exist yet).
"""

import pytest

from domain.services.conversation_digest import conversation_digest


# ===========================================================================
# Helpers
# ===========================================================================


def _human(content: str) -> dict:
    return {"type": "human", "content": content}


def _ai(content: str) -> dict:
    return {"type": "ai", "content": content}


def _sample_history() -> list[dict]:
    """A small serialized history: two complete human/ai turns."""
    return [
        _human("acenda a luz da sala"),
        _ai("Pronto, luz da sala acesa."),
        _human("obrigado"),
        _ai("De nada!"),
    ]


# ===========================================================================
# Determinism
# ===========================================================================


class TestConversationDigestDeterminism:
    def test_conversation_digest__same_messages__same_digest_across_calls(self):
        messages = _sample_history()
        assert conversation_digest(messages) == conversation_digest(messages)

    def test_conversation_digest__equal_but_distinct_objects__same_digest(self):
        # The store re-reads the history from Redis before the swap, so it never
        # sees the same objects that were snapshotted — only equal ones.
        assert conversation_digest(_sample_history()) == conversation_digest(
            _sample_history()
        )

    def test_conversation_digest__different_dict_key_order__same_digest(self):
        ordered = [{"type": "human", "content": "oi"}]
        reordered = [{"content": "oi", "type": "human"}]
        assert conversation_digest(ordered) == conversation_digest(reordered)

    def test_conversation_digest__does_not_mutate_input(self):
        messages = _sample_history()
        snapshot = [dict(message) for message in messages]
        conversation_digest(messages)
        assert messages == snapshot


# ===========================================================================
# Sensitivity (a changed prefix must abort the swap)
# ===========================================================================


class TestConversationDigestSensitivity:
    def test_conversation_digest__different_content__different_digest(self):
        original = [_human("acenda a luz da sala")]
        edited = [_human("acenda a luz do quarto")]
        assert conversation_digest(original) != conversation_digest(edited)

    def test_conversation_digest__same_content_different_type__different_digest(self):
        assert conversation_digest([_human("oi")]) != conversation_digest([_ai("oi")])

    def test_conversation_digest__swapped_types__different_digest(self):
        assert conversation_digest([_human("oi"), _ai("olá")]) != conversation_digest(
            [_ai("oi"), _human("olá")]
        )

    def test_conversation_digest__different_order__different_digest(self):
        messages = _sample_history()
        reversed_messages = list(reversed(messages))
        assert conversation_digest(messages) != conversation_digest(reversed_messages)

    def test_conversation_digest__appended_message__different_digest(self):
        messages = _sample_history()
        longer = messages + [_human("mais uma coisa")]
        assert conversation_digest(messages) != conversation_digest(longer)

    def test_conversation_digest__same_concatenated_text_split_differently__different_digest(
        self,
    ):
        # Guards against a naive implementation that just concatenates contents:
        # ["ab", ""] and ["a", "b"] must NOT collide.
        assert conversation_digest(
            [_human("ab"), _human("")]
        ) != conversation_digest([_human("a"), _human("b")])


# ===========================================================================
# Empty history and return type
# ===========================================================================


class TestConversationDigestEmptyHistory:
    def test_conversation_digest__empty_list__returns_non_empty_string(self):
        digest = conversation_digest([])
        assert isinstance(digest, str)
        assert digest != ""

    def test_conversation_digest__empty_list__is_stable(self):
        assert conversation_digest([]) == conversation_digest([])

    def test_conversation_digest__empty_list__differs_from_non_empty_history(self):
        assert conversation_digest([]) != conversation_digest(_sample_history())

    def test_conversation_digest__empty_content__does_not_collide_with_empty_list(self):
        assert conversation_digest([]) != conversation_digest([_human("")])


class TestConversationDigestReturnValue:
    @pytest.mark.parametrize(
        "messages",
        [
            [],
            [_human("oi")],
            _sample_history(),
        ],
    )
    def test_conversation_digest__any_history__returns_non_empty_hexdigest(
        self, messages
    ):
        digest = conversation_digest(messages)
        assert isinstance(digest, str)
        assert digest != ""
        # A hexdigest: lowercase hex characters only.
        assert all(char in "0123456789abcdef" for char in digest)

    def test_conversation_digest__any_history__has_stable_length(self):
        # Same hash function for every input, so the digest length is fixed.
        assert len(conversation_digest([])) == len(
            conversation_digest(_sample_history())
        )
