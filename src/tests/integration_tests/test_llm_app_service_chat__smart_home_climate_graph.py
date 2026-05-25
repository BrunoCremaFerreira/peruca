"""
LlmAppService Integration Tests - Smart Home Climate Graph Classification Tests

The air conditioning units are NOT physically connected. These tests only validate
that MainGraph correctly classifies messages as "smart_home_climate" intent and that
the system produces a non-empty string response without crashing.
"""

import pytest

from application.appservices.view_models import ChatRequest


pytestmark = pytest.mark.integration


#======================================================
# Turn On
#======================================================

@pytest.mark.parametrize("message", [
    "ligue o ar condicionado da sala",
    "liga o ar da cozinha",
    "pode ligar o ar do quarto",
])
def test_llm_app_service_chat__climate_turn_on_intent__routes_to_smart_home_climate(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(external_user_id=integration_user.external_id, message=message)

    # Act
    # AC units are not connected — only routing and non-empty output are validated.
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to smart_home_climate
    assert intents is not None and "smart_home_climate" in intents, \
        f"Expected 'smart_home_climate' in intents, got: {intents}"

    # Assert — output is a non-empty string (LLM generated a response without crashing)
    assert isinstance(output, str) and len(output.strip()) > 0, \
        f"Expected non-empty string output, got: {output!r}"


#======================================================
# Turn Off
#======================================================

@pytest.mark.parametrize("message", [
    "desligue o ar condicionado da sala",
    "apaga o ar do quarto",
    "desliga o climatizador",
])
def test_llm_app_service_chat__climate_turn_off_intent__routes_to_smart_home_climate(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(external_user_id=integration_user.external_id, message=message)

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to smart_home_climate
    assert intents is not None and "smart_home_climate" in intents, \
        f"Expected 'smart_home_climate' in intents, got: {intents}"

    # Assert — output is a non-empty string
    assert isinstance(output, str) and len(output.strip()) > 0, \
        f"Expected non-empty string output, got: {output!r}"


#======================================================
# Set Temperature
#======================================================

@pytest.mark.parametrize("message", [
    "coloque o ar da sala em 21 graus",
    "muda a temperatura do ar do quarto para 23",
    "quero 20 graus no ar da sala",
])
def test_llm_app_service_chat__climate_set_temperature_intent__routes_to_smart_home_climate(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(external_user_id=integration_user.external_id, message=message)

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to smart_home_climate
    assert intents is not None and "smart_home_climate" in intents, \
        f"Expected 'smart_home_climate' in intents, got: {intents}"

    # Assert — output is a non-empty string
    assert isinstance(output, str) and len(output.strip()) > 0, \
        f"Expected non-empty string output, got: {output!r}"


#======================================================
# Set HVAC Mode
#======================================================

@pytest.mark.parametrize("message", [
    "coloque o ar da sala em modo frio",
    "muda o ar para modo calor",
    "ativa o modo ventilacao no ar do quarto",
])
def test_llm_app_service_chat__climate_set_hvac_mode_intent__routes_to_smart_home_climate(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(external_user_id=integration_user.external_id, message=message)

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to smart_home_climate
    assert intents is not None and "smart_home_climate" in intents, \
        f"Expected 'smart_home_climate' in intents, got: {intents}"

    # Assert — output is a non-empty string
    assert isinstance(output, str) and len(output.strip()) > 0, \
        f"Expected non-empty string output, got: {output!r}"


#======================================================
# Query State
#======================================================

@pytest.mark.parametrize("message", [
    "qual a temperatura do ar da sala agora",
    "o ar condicionado da cozinha esta ligado?",
    "em que modo esta o ar do quarto",
])
def test_llm_app_service_chat__climate_query_state_intent__routes_to_smart_home_climate(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(external_user_id=integration_user.external_id, message=message)

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to smart_home_climate
    assert intents is not None and "smart_home_climate" in intents, \
        f"Expected 'smart_home_climate' in intents, got: {intents}"

    # Assert — output is a non-empty string
    assert isinstance(output, str) and len(output.strip()) > 0, \
        f"Expected non-empty string output, got: {output!r}"


#======================================================
# Boundary / Regression — Non-Climate Messages
#======================================================

@pytest.mark.parametrize("message", [
    "ligue a luz da sala",
    "adicione leite na lista",
    "como voce esta",
])
def test_llm_app_service_chat__non_climate_messages__do_not_route_to_climate(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(external_user_id=integration_user.external_id, message=message)

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must NOT route to smart_home_climate for unrelated messages
    assert intents is not None and "smart_home_climate" not in intents, \
        f"Expected 'smart_home_climate' NOT in intents, got: {intents}"

    # Assert — output is a non-empty string regardless of the intent
    assert isinstance(output, str) and len(output.strip()) > 0, \
        f"Expected non-empty string output, got: {output!r}"
