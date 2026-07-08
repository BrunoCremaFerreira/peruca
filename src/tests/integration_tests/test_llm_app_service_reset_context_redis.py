"""
LlmAppService.reset_context() — Redis-backed integration test (TDD - RED phase).

Proves the endpoint deletes the *real* chat_history key from Redis — the unit
test only proves clear() is called on a mock, not that the correct key is
wiped. Uses the existing `redis_backed_env` / `llm_app_service_redis` fixtures,
which skip gracefully when no test Redis is reachable. No Ollama needed: the
history is populated directly (add_messages), not via a chat() LLM round-trip.

Expected to FAIL until LlmAppService gains reset_context.
"""

from langchain_core.messages import AIMessage, HumanMessage


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
