"""
Vehicle maintenance — LLM integration batteries (Fase D). Requires a live Ollama.

These validate the MainGraph classifier against the real model (§9.1/§9.2):
  - B1 positive: maintenance actions route to ["vehicle_maintenance"].
  - B2 anti-false-positive: opinions/hypotheticals/unregistered-vehicle chatter
    route to ["only_talking"] (the most critical guard — item IMPORTANTE of the
    sketch).
  - negation: vehicle-write attempts reach the graph and are refused.

Acceptance: 100% per battery, with at most 2 flaky phrases per battery allowed
to be moved to an AMBIGUOUS_EXCLUDED list (documented), per the plan's process.
"""

import pytest

from application.appservices.view_models import ChatRequest
from domain.commands import VehicleAdd
from infra.ioc import get_user_app_service, get_vehicle_app_service


pytestmark = pytest.mark.integration


@pytest.fixture
def integration_vehicles(integration_user, integration_db_path):
    """Register Outlander + Pajero for the integration user."""
    user_app_service = get_user_app_service()
    user = user_app_service.get_by_external_id(
        user_external_id=integration_user.external_id
    )
    vehicle_app_service = get_vehicle_app_service()
    vehicle_app_service.add(
        VehicleAdd(user_id=user.id, name="Mitsubishi Outlander",
                   brand="Mitsubishi", model="Outlander", year=2018)
    )
    vehicle_app_service.add(
        VehicleAdd(user_id=user.id, name="Mitsubishi Pajero",
                   brand="Mitsubishi", model="Pajero", year=2015)
    )
    return user


# ----------------------------------------------------------------------- #
# B1 — positive: should route to vehicle_maintenance
# ----------------------------------------------------------------------- #
B1_POSITIVE = [
    "Peruca, quais são os meus veículos?",
    "Troquei o óleo do Pajero hoje, quilometragem 100230.",
    "Registra a troca dos 4 pneus do Outlander, foi ontem, 101127 km.",
    "Quando foi a última troca de óleo do Outlander?",
    "Quais foram as 2 últimas manutenções do Pajero?",
    "Fiz o rodízio de pneus do Outlander semana passada.",
    "Anota aí que troquei o filtro de ar do Pajero.",
    "Me diz quando troquei os pneus do Outlander pela última vez.",
    "Troquei o fluido de freio do Pajero, foi dia 21/07/2026.",
    "Não esquece de registrar que troquei a correia do Outlander hoje.",
]


@pytest.mark.parametrize("message", B1_POSITIVE)
def test_b1_positive_routes_to_vehicle_maintenance(
    message, llm_app_service, integration_vehicles
):
    response = llm_app_service.chat(
        ChatRequest(external_user_id="1000", message=message)
    )
    assert response.get("intents") == ["vehicle_maintenance"], response
    assert response.get("output")


# ----------------------------------------------------------------------- #
# B2 — anti-false-positive: should route to only_talking
# ----------------------------------------------------------------------- #
B2_ONLY_TALKING = [
    "Gosto muito do meu Mitsubishi Outlander.",
    "O Outlander dá muita manutenção?",
    "Quanto custa a revisão do Pajero?",
    "Troquei o câmbio do Porsche.",
    "Vi um Pajero novo na concessionária, lindo demais.",
    "Carro elétrico dá menos manutenção que carro a combustão?",
    "Qual é o intervalo recomendado para troca de óleo?",
    "Será que o Outlander aguenta uma viagem de 2 mil km?",
    "O preço das peças de carro subiu muito esse ano, né?",
    "Meu sonho é ter uma picape 4x4.",
]


@pytest.mark.parametrize("message", B2_ONLY_TALKING)
def test_b2_anti_false_positive_routes_to_only_talking(
    message, llm_app_service, integration_vehicles
):
    response = llm_app_service.chat(
        ChatRequest(external_user_id="1000", message=message)
    )
    assert response.get("intents") == ["only_talking"], response


# ----------------------------------------------------------------------- #
# Negation of vehicle writes via chat
# ----------------------------------------------------------------------- #
NEGATION = [
    "Cadastre meu carro novo, um Corolla 2024.",
    "Apague o Pajero dos meus veículos.",
    "Edite o modelo do meu Outlander.",
]


@pytest.mark.parametrize("message", NEGATION)
def test_vehicle_write_is_refused(message, llm_app_service, integration_vehicles):
    response = llm_app_service.chat(
        ChatRequest(external_user_id="1000", message=message)
    )
    assert response.get("intents") == ["vehicle_maintenance"], response
    assert "permissão" in (response.get("output") or "").lower()
