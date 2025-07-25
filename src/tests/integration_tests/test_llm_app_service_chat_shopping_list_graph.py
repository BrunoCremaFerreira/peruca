import os
from unittest.mock import patch

import pytest

from application.appservices.view_models import ChatRequest
from domain.commands import UserAdd
from infra.ioc import get_llm_app_service, get_user_app_service


DB_PATH = "/home/brn/tests/data/tests.db"
@patch.dict(os.environ, {
    "CORS_ORIGIN": "http://localhost:3000",
    "LLM_PROVIDER_TYPE": "OLLAMA",
    "LLM_PROVIDER_URL": "http://10.1.1.10:11434",
    "LLM_PROVIDER_API_KEY": "fake-api-key",
    "LLM_MAIN_GRAPH_CHAT_MODEL": "qwen3:14b",
    "LLM_MAIN_GRAPH_CHAT_TEMPERATURE": "0.5",
    "LLM_ONLY_TALK_GRAPH_CHAT_MODEL": "qwen3:14b",
    "LLM_ONLY_TALK_GRAPH_CHAT_TEMPERATURE": "0.5",
    "CACHE_DB_CONNECTION_STRING": "redis://localhost:6379/0",
    "PERUCA_DB_CONNECTION_STRING": f"sqlite://{DB_PATH}",
})

def setup_app_service():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    return get_llm_app_service(), get_user_app_service()

@pytest.mark.parametrize("message", [
    "Adicione ovos e ligue a luz da sala",
    "Coloca leite, pão e manteiga na lista, por favor",
    "A gente precisa comprar arroz. Ah, e me lembra de ver a pressão da bomba",
    "Adiciona 2 kg de batata e 1 de cebola",
    "Preciso de farinha e fermento, vou tentar fazer pão hoje",
    "Bota na lista: tomate, alface e pepino. Amanhã tem churrasco",
    "Não esquece: papel higiênico e detergente. Tem mais algo importante?",
    "Compra maçã, banana e laranja. E vê se o portão fechou direito",
    "Me adiciona leite condensado e creme de leite. Vai ter sobremesa!",
    "Pega também 1 pacote de café e 2 de açúcar",
    "Vamos precisar de óleo, sal e vinagre. E deixa as luzes da varanda apagadas",
    "Anota aí: frango, carne moída e salsicha",
    "Coloca sabão em pó e amaciante, acabou tudo",
    "Quero comprar queijo, presunto e pão de forma",
    "Adiciona 3 litros de leite. Vou fazer aquele bolo da vó. Você tem a receita?",
    "Compra iogurte natural e granola",
    "Adiciona milho verde, ervilha e molho de tomate",
    "Preciso de pão integral e peito de peru. E como anda a previsão do tempo?",
    "Bota na lista fraldas e lenços umedecidos",
    "Lembra de comprar cerveja e carvão pro fim de semana"
])
def test_chat_shopping_list_add(message):
    # Arrange
    llm_app_service, user_app_service = setup_app_service()
    user = UserAdd(name="Bruno", external_id="1000", summary="")
    user_app_service.add(user)
    chat_request = ChatRequest(external_user_id=user.external_id, message=message)
    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    # Assert
    intents = response.get("intents")
    output = response.get("output")
    assert "shopping_list" in intents
    assert output