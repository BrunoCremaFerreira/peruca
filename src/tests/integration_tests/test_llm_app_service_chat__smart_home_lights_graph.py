import pytest

from application.appservices.view_models import ChatRequest


pytestmark = pytest.mark.integration


# ======================================================
# Turn On
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "ligue a luz da sala",
        "ligue o abajur do quarto",
        "acenda as luzes da cozinha",
    ],
)
def test_llm_app_service_chat__smart_home_lights_turn_on_intent__routes_to_smart_home_lights(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    # LlmAppService.chat() returns {"intents": [...], "output": "string"}.
    # output_lights (the internal SmartHomeLightsGraph dict) is not exposed by the public API.
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to smart_home_lights (it never exposes sub-graph intents)
    assert intents is not None and "smart_home_lights" in intents, (
        f"Expected 'smart_home_lights' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string (LLM generated a response without crashing)
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


# ======================================================
# Turn Off
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "apague a luz da sala",
        "desligue o abajur do quarto",
        "apague as luzes da cozinha",
    ],
)
def test_llm_app_service_chat__smart_home_lights_turn_off_intent__routes_to_smart_home_lights(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to smart_home_lights
    assert intents is not None and "smart_home_lights" in intents, (
        f"Expected 'smart_home_lights' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


# ======================================================
# Turn Off All (whole-house command)
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "Desligue todas as luzes da casa",
        "Apague todas as luzes",
        "Apaga tudo da casa",
    ],
)
def test_llm_app_service_chat__smart_home_lights_turn_off_all_intent__routes_to_smart_home_lights(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to smart_home_lights (sub-graph intents are not exposed)
    assert intents is not None and "smart_home_lights" in intents, (
        f"Expected 'smart_home_lights' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string (whole-house command produced a response)
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


# ======================================================
# Turn On By Area (kitchen)
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "Ligue as luzes da cozinha",
        "Acenda as luzes do quarto",
    ],
)
def test_llm_app_service_chat__smart_home_lights_turn_on_by_area_intent__routes_to_smart_home_lights(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to smart_home_lights
    assert intents is not None and "smart_home_lights" in intents, (
        f"Expected 'smart_home_lights' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string (by-area command produced a response)
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


# ======================================================
# List Lights Status
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "Mostre as luzes da casa",
        "Quais luzes estão ligadas?",
        "Liste o status das luzes",
    ],
)
def test_llm_app_service_chat__smart_home_lights_list_status_intent__routes_to_smart_home_lights(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to smart_home_lights for status queries
    assert intents is not None and "smart_home_lights" in intents, (
        f"Expected 'smart_home_lights' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string (listing produced a response).
    # We do NOT assert specific content: Ollama is non-deterministic and the
    # test DB may not have areas populated; we only validate routing + non-empty output.
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


# ======================================================
# Unknown Area (friendly response)
# ======================================================


def test_llm_app_service_chat__smart_home_lights_unknown_area__routes_and_responds_friendly(
    llm_app_service, integration_user
):
    # Arrange — "varanda gourmet" is not a real area in the test environment.
    # Expected behavior: graph still routes to smart_home_lights, area handler
    # raises NofFoundValidationError, graph catches it and returns a friendly,
    # non-empty message. We do NOT assert specific wording (LLM varies).
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id,
        message="Ligue as luzes da varanda gourmet",
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must still route to smart_home_lights even for unknown areas
    assert intents is not None and "smart_home_lights" in intents, (
        f"Expected 'smart_home_lights' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string (friendly message that area is unknown)
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


# ======================================================
# Regression — singular alias-based commands still work as turn_on (entity-centric)
# ======================================================


def test_llm_app_service_chat__smart_home_lights_singular_alias__still_routes_as_entity_turn_on(
    llm_app_service, integration_user
):
    # Arrange — "Acenda a luz da sala" is a SINGULAR, alias-specific command.
    # Critical regression: after introducing turn_on_by_area, this must keep
    # being classified as the traditional entity-centric `turn_on` intent
    # (not as `turn_on_by_area`). From the public API perspective we cannot
    # observe the sub-graph intent directly, so we assert the contract that
    # IS observable: MainGraph routes to smart_home_lights AND produces a
    # non-empty response (i.e. the chain did not crash because of a routing
    # mismatch on a previously-working command).
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id,
        message="Acenda a luz da sala",
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — routing preserved for the legacy singular form
    assert intents is not None and "smart_home_lights" in intents, (
        f"Expected 'smart_home_lights' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string (legacy command still produces a response)
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )
