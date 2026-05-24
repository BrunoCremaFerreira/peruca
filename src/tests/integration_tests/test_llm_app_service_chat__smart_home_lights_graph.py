import pytest

from application.appservices.view_models import ChatRequest


pytestmark = pytest.mark.integration


@pytest.mark.parametrize("message, expected_items", [
    ("ligue a luz da sala", ["luz da sala"]),
    ("ligue o abajur do quarto", ["abajur do quarto"])
])
def test_chat_smart_home_lights__turn_on(message, expected_items, llm_app_service, integration_user):
    # Arrange
    chat_request = ChatRequest(external_user_id=integration_user.external_id, message=message)

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert
    assert "turn_on" in intents
    for item in expected_items:
        assert item in output
