"""
User Memory Integration Tests

Exercises the end-to-end memory feature against a real LLM (Ollama):
  - Level A: durable facts said in chat are extracted (BackgroundTasks) and
    persisted; commands are NOT turned into memories.
  - Level B: existing memories enrich the conversation context.

The chat route schedules memory extraction via FastAPI BackgroundTasks.
Starlette's TestClient runs background tasks at the end of each request, so a
request through the TestClient validates response + extraction + persistence
end-to-end.
"""

import pytest
from fastapi.testclient import TestClient

from app import app
from application.appservices.view_models import ChatRequest
from domain.commands import UserMemoryAdd
from infra.ioc import get_user_memory_service


pytestmark = pytest.mark.integration


@pytest.fixture
def client(integration_user, integration_db_path):
    """
    TestClient created under the integration env + temporary DB fixtures.

    The IoC factories read Settings() (and therefore os.environ) at call time,
    so the env patches kept active by `integration_env` / `integration_db_path`
    apply to every request made through this client. The integration user
    (external_id="1000") is created by the `integration_user` fixture.
    """
    with TestClient(app) as test_client:
        yield test_client


def _internal_user_id(user_app_service) -> str:
    user = user_app_service.get_by_external_id(external_id="1000")
    return user.id


# ======================================================
# Level A — extraction + persistence via TestClient
# ======================================================


def test_chat_durable_fact__is_persisted_as_memory(client, user_app_service):
    # Arrange
    user_id = _internal_user_id(user_app_service)

    # Act — durable fact stated in conversation
    chat_resp = client.post(
        "/llm/chat",
        json={
            "message": "Meu nome é Bruno e eu adoro café sem açúcar.",
            "external_user_id": "1000",
            "chat_id": "x",
        },
    )
    assert chat_resp.status_code == 200, chat_resp.text

    # Background task (memory extraction) has already run by now.
    memory_resp = client.get(f"/user/{user_id}/memory")
    assert memory_resp.status_code == 200, memory_resp.text
    memories = memory_resp.json()

    # Assert — at least one memory was extracted from the durable fact.
    assert len(memories) >= 1, (
        f"Expected at least one memory to be extracted, got: {memories}"
    )

    # Tolerant content check: the LLM is non-deterministic, so we accept any
    # memory mentioning the coffee preference ("café" or "açúcar").
    contents = " ".join(m["content"].lower() for m in memories)
    assert ("café" in contents) or ("açúcar" in contents), (
        f"Expected a memory mentioning the coffee preference, got: {memories}"
    )


def test_chat_command__does_not_create_memory(client, user_app_service):
    # Arrange — DB is recreated per test by the fixture, so memory starts empty.
    user_id = _internal_user_id(user_app_service)

    # Act — a pure command should not produce a durable memory.
    chat_resp = client.post(
        "/llm/chat",
        json={
            "message": "Liga a luz da sala.",
            "external_user_id": "1000",
            "chat_id": "x",
        },
    )
    assert chat_resp.status_code == 200, chat_resp.text

    memory_resp = client.get(f"/user/{user_id}/memory")
    assert memory_resp.status_code == 200, memory_resp.text
    memories = memory_resp.json()

    # Assert — commands must not become memories.
    assert len(memories) == 0, (
        f"Expected no memory to be created for a command, got: {memories}"
    )


# ======================================================
# Level B — context enrichment with existing memory
# ======================================================


def test_chat_enriches_context_with_existing_memory(
    llm_app_service, user_app_service
):
    # Arrange — pre-populate a memory directly through the service (no LLM).
    user_id = _internal_user_id(user_app_service)
    memory_service = get_user_memory_service()
    memory_service.add(
        UserMemoryAdd(
            user_id=user_id,
            content="O nome do cachorro do usuário é Rex.",
        )
    )

    # Act — ask something that requires the stored memory to answer.
    chat_request = ChatRequest(
        external_user_id="1000",
        message="Qual é o nome do meu cachorro?",
        chat_id="x",
    )
    response = llm_app_service.chat(chat_request=chat_request)

    intents = response.get("intents")
    output = response.get("output")

    # Assert — structural guarantee: this is small talk, routed to only_talking.
    assert output, "Response output must not be empty"
    assert "only_talking" in intents, (
        f"Expected only_talking intent for a personal question, got: {intents}"
    )

    # Tolerant content check: the enriched context should let Peruca recall "Rex".
    assert "rex" in output.lower(), (
        f"Expected response to recall the dog's name 'Rex' from memory, got: {output}"
    )
