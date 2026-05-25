import pytest

from application.appservices.view_models import ChatRequest


pytestmark = pytest.mark.integration


#======================================================
# Turn On
#======================================================

@pytest.mark.parametrize("message", [
    "ligue a luz da sala",
    "ligue o abajur do quarto",
    "acenda as luzes da cozinha",
])
def test_llm_app_service_chat__smart_home_lights_turn_on_intent__routes_to_smart_home_lights(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(external_user_id=integration_user.external_id, message=message)

    # Act
    # LlmAppService.chat() returns {"intents": [...], "output": "string"}.
    # output_lights (the internal SmartHomeLightsGraph dict) is not exposed by the public API.
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to smart_home_lights (it never exposes sub-graph intents)
    assert intents is not None and "smart_home_lights" in intents, \
        f"Expected 'smart_home_lights' in intents, got: {intents}"

    # Assert — output is a non-empty string (LLM generated a response without crashing)
    assert isinstance(output, str) and len(output.strip()) > 0, \
        f"Expected non-empty string output, got: {output!r}"


#======================================================
# Turn Off
#======================================================

@pytest.mark.parametrize("message", [
    "apague a luz da sala",
    "desligue o abajur do quarto",
    "apague as luzes da cozinha",
])
def test_llm_app_service_chat__smart_home_lights_turn_off_intent__routes_to_smart_home_lights(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(external_user_id=integration_user.external_id, message=message)

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to smart_home_lights
    assert intents is not None and "smart_home_lights" in intents, \
        f"Expected 'smart_home_lights' in intents, got: {intents}"

    # Assert — output is a non-empty string
    assert isinstance(output, str) and len(output.strip()) > 0, \
        f"Expected non-empty string output, got: {output!r}"
