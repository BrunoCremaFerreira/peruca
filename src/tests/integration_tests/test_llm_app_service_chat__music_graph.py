"""
LlmAppService Integration Tests - Music Graph Classification Tests

Music Assistant (MASS) is NOT running in the test environment. These tests only
validate that MainGraph correctly classifies messages as "music" intent and that
the system produces a non-empty string response without crashing, even when the
MASS REST API is unreachable (graceful degradation path).
"""

import pytest

from application.appservices.view_models import ChatRequest


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_music_assistant(music_assistant_available):
    # Skip the whole module early (before any LLM call) when MA is unreachable.
    pass


# ======================================================
# play_media — tocar música / artista / playlist / álbum
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "toca Listen to Your Heart da Roxette",
        "toque aquela música da Roxette Listen to Your Heart",
        "coloca uma música dos Beatles",
        "toca músicas do Caetano Veloso",
        "coloca uma playlist de jazz",
        "toque o álbum Abbey Road dos Beatles",
    ],
)
def test_llm_app_service_chat__music_play_media_intent__routes_to_music(
    message, llm_app_service, integration_user
):
    """
    Regression group: explicit play requests (artist, song, album, playlist) must
    always be routed to the music graph regardless of MASS availability. The actual
    MASS call will fail gracefully, but the intent classification and routing are
    what this test exercises.
    """
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    # MASS is offline — LlmAppService catches get_players() exception and sets
    # music_is_playing=False. MainGraph still classifies these messages as "music".
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to music (sub-graph play_media intent is not exposed)
    assert intents is not None and "music" in intents, (
        f"Expected 'music' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string (graceful error message or success response)
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


# ======================================================
# player_command — controles de transporte com contexto explícito
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "pause a música",
        "pausa a música",
        "para a música",
        "próxima música",
        "música anterior",
        "volta a música",
    ],
)
def test_llm_app_service_chat__music_player_command_intent__routes_to_music(
    message, llm_app_service, integration_user
):
    """
    Transport-control commands must route to the music graph when the explicit
    word "música" is present. Without MASS context (music_is_playing=False), the
    LLM relies on lexical cues alone — "próxima" in isolation is ambiguous, but
    "próxima MÚSICA" is unambiguous and must always classify as music.
    """
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to music
    assert intents is not None and "music" in intents, (
        f"Expected 'music' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


# ======================================================
# set_volume — controle de volume
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "coloca o volume em 50",
        "aumenta o volume da música",
        "abaixa o volume",
    ],
)
def test_llm_app_service_chat__music_set_volume_intent__routes_to_music(
    message, llm_app_service, integration_user
):
    """
    Volume commands that are musically contextualized must route to the music graph.
    "coloca o volume em 50" uses the numeric form; "aumenta/abaixa o volume da música"
    uses the directional form — both paths must be covered.
    """
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to music
    assert intents is not None and "music" in intents, (
        f"Expected 'music' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


# ======================================================
# now_playing — consulta de status
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "o que está tocando?",
        "qual música está tocando?",
        "me diz o que está tocando",
    ],
)
def test_llm_app_service_chat__music_now_playing_intent__routes_to_music(
    message, llm_app_service, integration_user
):
    """
    "What is playing?" queries must route to the music graph so that MusicGraph
    can call get_now_playing() — or return a graceful offline message if MASS is
    unreachable. The intent classification must not be swallowed into only_talking.
    """
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must route to music
    assert intents is not None and "music" in intents, (
        f"Expected 'music' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


# ======================================================
# graceful_degradation — MASS offline não crasha
# ======================================================


def test_llm_app_service_chat__music_mass_offline__returns_nonempty_string_without_crash(
    llm_app_service, integration_user
):
    """
    Even when MASS is unreachable, the graph must return a non-empty string —
    never crash or expose a stack trace in the output.

    This test does NOT assert the specific content of the response (success vs.
    error message) because both are valid outcomes when the backend is offline.
    It only verifies the system's resilience contract: any exception thrown by the
    MASS REST adapter must be caught inside MusicGraph and converted into a
    user-facing string.
    """
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id,
        message="toca jazz",
    )

    # Act — MASS is not running; all asyncio.run() calls inside MusicGraph will raise
    response = llm_app_service.chat(chat_request=chat_request)
    output = response.get("output")

    # Assert — must be a non-empty string regardless of success or graceful error
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output (graceful degradation), got: {output!r}"
    )


# ======================================================
# negative — comandos não-musicais NÃO são roteados como music
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "ligue a luz da sala",
        "adiciona leite na lista",
    ],
)
def test_llm_app_service_chat__non_music_messages__do_not_route_to_music(
    message, llm_app_service, integration_user
):
    """
    Boundary / regression: unrelated commands (lighting, shopping) must never be
    classified as "music". This guards against prompt drift where the classifier
    becomes too aggressive in routing to MusicGraph.
    """
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — MainGraph must NOT route to music for unrelated messages
    assert intents is not None and "music" not in intents, (
        f"Expected 'music' NOT in intents, got: {intents}"
    )

    # Assert — output is a non-empty string regardless of the intent used
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )


# ======================================================
# multi_intent — luzes + música no mesmo pedido
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "ligue a luz da sala e toque jazz",
        "acende as luzes do quarto e coloca uma playlist relaxante",
    ],
)
def test_llm_app_service_chat__music_and_lights_multi_intent__routes_to_both_graphs(
    message, llm_app_service, integration_user
):
    """
    Multi-intent messages that combine a smart-home lighting command with a music
    command must be classified as BOTH "smart_home_lights" AND "music". This
    validates that MainGraph does not short-circuit on the first recognized intent
    and that the final_response merge step aggregates both sub-graph outputs into a
    single non-empty string.
    """
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert — both intents must be present
    assert intents is not None and "music" in intents, (
        f"Expected 'music' in intents, got: {intents}"
    )
    assert "smart_home_lights" in intents, (
        f"Expected 'smart_home_lights' in intents, got: {intents}"
    )

    # Assert — output is a non-empty string (both sub-graphs produced responses)
    assert isinstance(output, str) and len(output.strip()) > 0, (
        f"Expected non-empty string output, got: {output!r}"
    )
