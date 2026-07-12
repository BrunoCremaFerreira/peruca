"""
Chat Context Compaction — end-to-end integration test (Fase F).

The only test that runs the WHOLE cycle with nothing faked: a real Redis
history, the real trigger/turn-boundary gate, a real Ollama summarization, the
real CAS, and then a real chat() turn that has to answer from a fact which no
longer exists in the raw history — it survives only inside the summary.

Compaction is invoked DIRECTLY on the app service rather than through the HTTP
route: the scheduling of the BackgroundTask is FastAPI's job (covered by the
route unit test), and driving it through TestClient would re-test the framework
(plan §7, "Não testar").

Thresholds are lowered via the environment (trigger=6, keep_tail=4) so the cycle
fires on a short seeded conversation instead of a 30-message one.

Requires BOTH a live Ollama and a live test Redis; skips gracefully otherwise.
"""

import os
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

import infra.ioc as ioc
from application.appservices.view_models import ChatRequest
from infra.ioc import (
    get_context_compaction_app_service,
    get_conversation_context_store,
    get_llm_app_service,
)


pytestmark = pytest.mark.integration


COMPACTION_ENV = {
    "CHAT_COMPACTION_ENABLED": "True",
    "CHAT_COMPACTION_TRIGGER_MESSAGES": "6",
    "CHAT_COMPACTION_KEEP_TAIL_MESSAGES": "4",
    # High enough that only the message-count trigger can fire — the char
    # trigger firing too would make it ambiguous which gate we are exercising.
    "CHAT_COMPACTION_TRIGGER_CHARS": "100000",
}

EXTERNAL_USER_ID = "1000"


def _turn(human: str, ai: str) -> list:
    return [HumanMessage(content=human), AIMessage(content=ai)]


def _seeded_conversation() -> list:
    """
    10 messages. The distinctive fact ("Pousada Marmelada") sits in the first 6 —
    exactly the prefix the compaction will drop — so a later answer that recalls
    it can only have come from the summary.

    Alternating human/ai starting with a human keeps index 6 (the cut) on a turn
    boundary, so the boundary adjustment leaves the cut where it is.
    """
    messages = []
    messages += _turn(
        "Oi Peruca! Estou planejando uma viagem para Campos do Jordão.",
        "Que legal! Quando você vai?",
    )
    messages += _turn(
        "Vou no dia 20 de agosto e já reservei a Pousada Marmelada.",
        "Anotado: Pousada Marmelada, dia 20 de agosto.",
    )
    messages += _turn(
        "Vou de carro, são umas três horas de estrada.",
        "Boa, a estrada é tranquila nessa época.",
    )
    messages += _turn(
        "Quero levar a Marina junto.",
        "Vai ser uma ótima companhia.",
    )
    messages += _turn(
        "Depois eu te conto mais detalhes.",
        "Fico no aguardo!",
    )
    return messages


@pytest.fixture
def compaction_env(redis_backed_env):
    with patch.dict(os.environ, COMPACTION_ENV):
        # The app service captures the thresholds at construction time, so the
        # IoC cache must be rebuilt under the lowered thresholds.
        ioc._repo_cache.clear()
        yield redis_backed_env
        ioc._repo_cache.clear()


@pytest.fixture
def user_id(compaction_env, integration_user, user_app_service):
    return user_app_service.get_by_external_id(
        external_id=integration_user.external_id
    ).id


@pytest.fixture
def seeded_history(compaction_env, user_id):
    service = get_llm_app_service()
    history = service.get_session_history(user_id)
    history.add_messages(_seeded_conversation())
    assert len(service.get_session_history(user_id).messages) == 10
    return history


class TestChatContextCompactionCycle:
    def test_compact_if_needed__history_over_trigger__truncates_and_stores_summary(
        self, compaction_env, seeded_history, user_id, redis_backed_env
    ):
        from redis import from_url

        store = get_conversation_context_store()
        compaction = get_context_compaction_app_service()

        # Act — the real background job: gate → prefix → Ollama → CAS.
        compaction.compact_if_needed(external_user_id=EXTERNAL_USER_ID)

        # Assert — the history shrank to the configured tail (10 - 6 = 4 kept).
        remaining = store.read_history(user_id)
        assert len(remaining) == 4, (
            f"Expected the 4-message tail to survive, got {len(remaining)}: {remaining}"
        )
        contents = [m["content"] for m in remaining]
        assert "Quero levar a Marina junto." in contents
        assert "Vou no dia 20 de agosto e já reservei a Pousada Marmelada." not in (
            contents
        ), "The compacted prefix must be gone from the raw history"

        # Assert — the summary key really exists in Redis...
        client = from_url(redis_backed_env)
        try:
            assert client.exists(f"chat_summary:{user_id}") == 1, (
                "The compaction truncated the history but wrote no summary — "
                "that is unrecoverable context loss"
            )
        finally:
            client.close()

        # ...and holds a structurally valid summary (tolerant: structure only).
        record = store.get_summary(user_id)
        assert record is not None
        assert record["summary"].startswith("###")
        assert record["covers"] == 6

    def test_chat_after_compaction__fact_only_in_summary__is_recalled(
        self, compaction_env, seeded_history, user_id
    ):
        service = get_llm_app_service()
        store = get_conversation_context_store()
        compaction = get_context_compaction_app_service()

        # Arrange — compact, then prove the fact is NOT in the raw history anymore.
        compaction.compact_if_needed(external_user_id=EXTERNAL_USER_ID)
        raw_history = " ".join(m["content"] for m in store.read_history(user_id))
        assert "Marmelada" not in raw_history, (
            "Precondition failed: the fact is still in the raw history, so this "
            "test would pass without the summary being used at all"
        )

        # Act — ask about a fact that now lives only inside the summary.
        response = service.chat(
            chat_request=ChatRequest(
                message="Como se chama a pousada que eu reservei?",
                external_user_id=EXTERNAL_USER_ID,
                chat_id="x",
            )
        )
        output = response.get("output")

        # Assert — structural guarantee first: the turn completed.
        assert output, "Response output must not be empty"

        # Tolerant content check: the answer should recall the pousada's name,
        # which is reachable ONLY through the injected summary. Kept as a real
        # assertion (not a vacuous one) because recalling the compacted context
        # is the entire point of the feature.
        assert "marmelada" in output.lower(), (
            "Expected the answer to recall 'Pousada Marmelada' from the compaction "
            f"summary (it is no longer in the raw history), got: {output}"
        )


class TestChatContextCompactionGate:
    def test_compact_if_needed__history_below_trigger__does_nothing(
        self, compaction_env, user_id
    ):
        service = get_llm_app_service()
        store = get_conversation_context_store()
        compaction = get_context_compaction_app_service()

        # Arrange — 4 messages, below the trigger of 6. No Ollama call is made.
        service.get_session_history(user_id).add_messages(
            _turn("oi", "olá!") + _turn("tudo bem?", "tudo ótimo!")
        )

        # Act
        compaction.compact_if_needed(external_user_id=EXTERNAL_USER_ID)

        # Assert — untouched history, no summary.
        assert len(store.read_history(user_id)) == 4
        assert store.get_summary(user_id) is None
