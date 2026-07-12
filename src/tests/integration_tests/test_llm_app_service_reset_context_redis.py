"""
LlmAppService.reset_context() — Redis-backed integration test.

Proves the endpoint deletes the *real* keys from Redis — the unit test only
proves clear() is called on a mock, not that the correct keys are wiped. Uses
the existing `redis_backed_env` / `llm_app_service_redis` fixtures, which skip
gracefully when no test Redis is reachable. No Ollama needed: the history is
populated directly (add_messages) and the summary is written through the store,
not via a chat() LLM round-trip.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from domain.services.conversation_digest import conversation_digest
from infra.ioc import get_conversation_context_store


pytestmark = pytest.mark.integration


SUMMARY = "### Assuntos em andamento\n- O usuário planeja uma viagem."


class TestResetContextRedis:
    def test_reset_context__redis_backed__clears_history_key(
        self, llm_app_service_redis, integration_user, user_app_service
    ):
        # Arrange — resolve the persisted user id (the history session key).
        service = llm_app_service_redis
        user = user_app_service.get_by_external_id(integration_user.external_id)

        history = service.get_session_history(user.id)
        history.add_messages(
            [HumanMessage(content="oi"), AIMessage(content="olá!")]
        )
        # Sanity — history really got populated in Redis.
        assert service.get_session_history(user.id).messages != []

        # Act
        service.reset_context(user_id=user.id)

        # Assert — the chat_history key is gone; a fresh lookup is empty.
        assert service.get_session_history(user.id).messages == []

    def test_reset_context__redis_backed__clears_summary_key_too(
        self, llm_app_service_redis, integration_user, user_app_service,
        redis_backed_env,
    ):
        from redis import from_url

        # Arrange — a COMPACTED conversation: history key + summary key.
        service = llm_app_service_redis
        user = user_app_service.get_by_external_id(integration_user.external_id)
        store = get_conversation_context_store()

        history = service.get_session_history(user.id)
        history.add_messages(
            [
                HumanMessage(content="pergunta 0"),
                AIMessage(content="resposta 0"),
                HumanMessage(content="pergunta 1"),
                AIMessage(content="resposta 1"),
            ]
        )
        prefix = store.read_history(user.id)[:2]
        assert store.apply_compaction(
            user.id, len(prefix), conversation_digest(prefix), SUMMARY
        )

        client = from_url(redis_backed_env)
        try:
            assert client.exists(f"chat_history:{user.id}") == 1
            assert client.exists(f"chat_summary:{user.id}") == 1

            # Act
            service.reset_context(user_id=user.id)

            # Assert — BOTH keys are gone. A reset that wiped only the history
            # would leave Peruca reciting a summary of the conversation the user
            # just asked it to forget.
            assert client.exists(f"chat_history:{user.id}") == 0
            assert client.exists(f"chat_summary:{user.id}") == 0
        finally:
            client.close()

        assert store.get_summary(user.id) is None
        assert service.get_session_history(user.id).messages == []
