"""
LlmAppService Integration Tests - Smart Home Cameras Graph Classification Tests

Physical cameras (Home Assistant) are NOT required to be connected.
These tests only validate that MainGraph correctly classifies messages as
"smart_home_security_cams" intent and that the system produces a non-empty string
response without crashing.

If no camera entity aliases are registered in the test database, the cameras graph
will find no matching entities and still produce a response via the final_response
node (which formats whatever camera data is available, even if empty).
"""

import pytest

from application.appservices.view_models import ChatRequest


pytestmark = pytest.mark.integration


# ======================================================
# Show Snapshot
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "Mostre a câmera da cozinha",
        "Quero ver a câmera da entrada",
        "Mostra o que está aparecendo na câmera da garagem",
    ],
)
def test_chat__show_snapshot__routes_to_smart_home_cameras_graph(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    # Camera hardware is not connected — only routing and non-empty output are validated.
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to smart_home_security_cams
    assert intents is not None and "smart_home_security_cams" in intents, (
        f"Expected 'smart_home_security_cams' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string (LLM generated a response without crashing)
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


@pytest.mark.parametrize(
    "message",
    [
        "Mostre a câmera da sala",
        "Preciso ver a imagem da câmera do quarto",
        "Exibe a câmera do corredor para mim",
    ],
)
def test_chat__show_snapshot__returns_non_empty_response(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    output = response.get("output")

    # Assert — output is a non-empty string regardless of camera availability
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


# ======================================================
# Check Status
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "A câmera da sala está ativa?",
        "A câmera da cozinha está funcionando?",
        "Qual é o status da câmera da garagem?",
    ],
)
def test_chat__check_status__routes_to_smart_home_cameras_graph(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    # Camera hardware is not connected — only routing and non-empty output are validated.
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to smart_home_security_cams
    assert intents is not None and "smart_home_security_cams" in intents, (
        f"Expected 'smart_home_security_cams' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


@pytest.mark.parametrize(
    "message",
    [
        "A câmera da entrada está online?",
        "Verifique se a câmera do jardim está ativa",
        "A câmera de segurança do escritório está ligada?",
    ],
)
def test_chat__check_status__returns_non_empty_response(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    output = response.get("output")

    # Assert — output is a non-empty string regardless of camera availability
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


# ======================================================
# Boundary / Regression — Non-Camera Messages
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "ligue a luz da sala",
        "adicione leite na lista",
        "como você está",
        "qual a temperatura do quarto",
    ],
)
def test_chat__non_camera_messages__do_not_route_to_cameras_graph(
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

    # Assert — MainGraph must NOT route to smart_home_security_cams for unrelated messages
    assert intents is not None and "smart_home_security_cams" not in intents, (
        f"Expected 'smart_home_security_cams' NOT in intents, got: {intents}"
    )

    # Assert — output is a non-empty string regardless of the intent
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )
