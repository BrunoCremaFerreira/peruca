"""
LlmAppService Integration Tests - Smart Home Sensors Graph Classification Tests

Sensors and physical devices (Home Assistant) are NOT required to be connected.
These tests only validate that MainGraph correctly classifies messages as
"smart_home_sensors" intent and that the system produces a non-empty string
response without crashing.

If no entity aliases are registered in the test database, the sensors graph will
find no matching entities and still produce a response via the final_response node
(which formats whatever sensor data is available, even if empty).
"""

import pytest

from application.appservices.view_models import ChatRequest


pytestmark = pytest.mark.integration


# ======================================================
# Query Current State
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "Há alguma porta aberta na casa?",
        "Tem alguma janela aberta agora?",
        "Qual a temperatura do quarto?",
    ],
)
def test_llm_app_service_chat__sensors_query_current_state_intent__routes_to_smart_home_sensors(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    # Sensors are not physically connected — only routing and non-empty output are validated.
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to smart_home_sensors
    assert intents is not None and "smart_home_sensors" in intents, (
        f"Expected 'smart_home_sensors' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string (LLM generated a response without crashing)
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


@pytest.mark.parametrize(
    "message",
    [
        "Tem alguém no escritório?",
        "Detectou algum movimento na sala?",
        "A porta da frente está fechada?",
    ],
)
def test_llm_app_service_chat__sensors_presence_and_door_query__routes_to_smart_home_sensors(
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

    # Assert — MainGraph must route to smart_home_sensors
    assert intents is not None and "smart_home_sensors" in intents, (
        f"Expected 'smart_home_sensors' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


# ======================================================
# Query History
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "Houve movimento na lavanderia nas últimas 3 horas?",
        "A porta ficou aberta hoje?",
        "Quando foi a última vez que detectaram presença no corredor?",
    ],
)
def test_llm_app_service_chat__sensors_query_history_intent__routes_to_smart_home_sensors(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    # History queries — HA not connected, graph falls back gracefully
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to smart_home_sensors
    assert intents is not None and "smart_home_sensors" in intents, (
        f"Expected 'smart_home_sensors' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


# ======================================================
# Multi-intent: Sensors + Lights
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "Acende a luz da sala e me diz se tem alguma porta aberta.",
        "Ligue as luzes do corredor e verifique se há movimento lá.",
        "Desligue a luz da cozinha e me fala qual a temperatura do ambiente.",
    ],
)
def test_llm_app_service_chat__sensors_and_lights_combined__routes_to_both_graphs(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    # Multi-intent: MainGraph should classify both smart_home_lights and smart_home_sensors
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — both intents must be present; only_talking must not be the sole intent
    assert intents is not None, f"intents must not be None, got: {intents}"
    assert "smart_home_sensors" in intents, (
        f"Expected 'smart_home_sensors' in intents, got: {intents}"
    )
    assert "smart_home_lights" in intents, (
        f"Expected 'smart_home_lights' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


# ======================================================
# Boundary / Regression — Non-Sensor Messages
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "ligue a luz da sala",
        "adicione leite na lista",
        "como você está",
        "ligue o ar condicionado do quarto",
    ],
)
def test_llm_app_service_chat__non_sensor_messages__do_not_route_to_sensors(
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

    # Assert — MainGraph must NOT route to smart_home_sensors for unrelated messages
    assert intents is not None and "smart_home_sensors" not in intents, (
        f"Expected 'smart_home_sensors' NOT in intents, got: {intents}"
    )

    # Assert — output is a non-empty string regardless of the intent
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )
