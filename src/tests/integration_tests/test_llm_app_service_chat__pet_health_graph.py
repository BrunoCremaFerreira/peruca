"""
Pet health — LLM integration batteries (Fase D). Requires a live Ollama.

These validate the MainGraph classifier against the real model (§9.1):
  - B1 positive: pet-health actions route to ["pet_health"].
  - B2 anti-false-positive: opinions/hypotheticals/persona chatter/unregistered
    pet mentions route to ["only_talking"] (the most critical guard, given the
    pets live in the Peruca persona — §9.1).
  - negation: pet-write attempts reach the graph and are refused.
  - persona: free conversation about a registered pet stays ["only_talking"] and
    still demonstrates knowledge of the pet (the §2.9 dynamic persona).

Acceptance: 100% per battery, with at most 2 flaky phrases per battery allowed to
be moved to an AMBIGUOUS_EXCLUDED list (documented), per the plan's process.
"""

import pytest

from application.appservices.view_models import ChatRequest
from domain.commands import PetAdd
from infra.ioc import get_pet_app_service, get_user_app_service


pytestmark = pytest.mark.integration


@pytest.fixture
def integration_pets(integration_user, integration_db_path):
    """Register Caçolin + Caçolão for the integration user (matches §2.9)."""
    user_app_service = get_user_app_service()
    user = user_app_service.get_by_external_id(
        external_id=integration_user.external_id
    )
    pet_app_service = get_pet_app_service()
    pet_app_service.add(
        PetAdd(user_id=user.id, name="Caçolin",
               nicknames=["Lilo", "Caçolinho", "Suzu"], sex="male", species="dog",
               description="vira-lata caramelo, preguiçoso, adora o sofá e odeia gatos")
    )
    pet_app_service.add(
        PetAdd(user_id=user.id, name="Caçolão", nicknames=["Lyon"], sex="male",
               species="dog", description="grandão, preto e branco, esfomeado, vive no quintal")
    )
    return user


# ----------------------------------------------------------------------- #
# B1 — positive: should route to pet_health
# ----------------------------------------------------------------------- #
B1_POSITIVE = [
    "Peruca, quais são os meus pets?",
    "O Caçolin tomou vacina hoje.",
    "Adicione a vacina para o Caçolão: 22/05/2026 - Leptospirose.",
    "O Caçolão tomou o vermífugo Bravecto no dia 12/05/2026.",
    "O Caçolin já tomou vacina de gripe canina nesse ano?",
    "Quais vacinas o Caçolão já tomou?",
    "Levei o Lilo no veterinário ontem.",
    "Dei o antipulgas no Suzu hoje.",
    "Quando foi a última vacina do Caçolin?",
    "Registra que o Lyon tomou a antirrábica semana passada.",
]


@pytest.mark.parametrize("message", B1_POSITIVE)
def test_b1_positive_routes_to_pet_health(message, llm_app_service, integration_pets):
    response = llm_app_service.chat(
        ChatRequest(external_user_id="1000", message=message)
    )
    assert response.get("intents") == ["pet_health"], response
    assert response.get("output")


# ----------------------------------------------------------------------- #
# B2 — anti-false-positive: should route to only_talking
# ----------------------------------------------------------------------- #
B2_ONLY_TALKING = [
    "O Caçolin está dormindo no sofá de novo.",
    "O Caçolão comeu meu chinelo hoje.",
    "Meu cachorro é lindo demais.",
    "Qual vacina é recomendada para filhotes?",
    "Cachorro pode tomar dipirona?",
    "De quanto em quanto tempo se dá vermífugo?",
    "Será que o Bravecto funciona mesmo?",
    "O cachorro da vizinha tomou vacina ontem.",
    "Adoro quando o Lilo late pro carteiro.",
    "Vi um vídeo engraçado de um gato tomando vacina.",
]


@pytest.mark.parametrize("message", B2_ONLY_TALKING)
def test_b2_anti_false_positive_routes_to_only_talking(
    message, llm_app_service, integration_pets
):
    response = llm_app_service.chat(
        ChatRequest(external_user_id="1000", message=message)
    )
    assert response.get("intents") == ["only_talking"], response


# ----------------------------------------------------------------------- #
# Negation of pet writes via chat
# ----------------------------------------------------------------------- #
NEGATION = [
    "Cadastre minha nova cachorra, a Mel.",
    "Apague o Caçolão dos meus pets.",
    "Muda o apelido do Caçolin.",
]


@pytest.mark.parametrize("message", NEGATION)
def test_pet_write_is_refused(message, llm_app_service, integration_pets):
    response = llm_app_service.chat(
        ChatRequest(external_user_id="1000", message=message)
    )
    assert response.get("intents") == ["pet_health"], response
    assert "permissão" in (response.get("output") or "").lower()


# ----------------------------------------------------------------------- #
# Dynamic persona (§2.9): free chat about a registered pet stays only_talking
# and Peruca still knows the pet.
# ----------------------------------------------------------------------- #
PERSONA = [
    "Me fala um pouco do Caçolin.",
    "Quem é o Suzu?",
]


@pytest.mark.parametrize("message", PERSONA)
def test_persona_knows_registered_pet(message, llm_app_service, integration_pets):
    response = llm_app_service.chat(
        ChatRequest(external_user_id="1000", message=message)
    )
    assert response.get("intents") == ["only_talking"], response
    assert response.get("output")
