import os
from typing import List
from unittest.mock import patch

import pytest

from application.appservices.view_models import ChatRequest
from domain.commands import UserAdd
from domain.entities import ShoppingListItem
from infra.ioc import get_llm_app_service, get_shopping_list_repository, get_user_app_service


DB_PATH = "/home/brn/tests/data/tests.db"
@patch.dict(os.environ, {
    "CORS_ORIGIN": "http://localhost:3000",
    "LLM_PROVIDER_TYPE": "OLLAMA",
    "LLM_PROVIDER_URL": "http://10.10.1.10:11434",
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
    return get_shopping_list_repository(), get_llm_app_service(), get_user_app_service()

@pytest.mark.parametrize("message, expected_items", [
    ("Adicione ovos e ligue a luz da sala", ["ovos"]),
    ("Coloca leite, pão e manteiga na lista, por favor", ["leite", "pão", "manteiga"]),
    ("A gente precisa comprar arroz. Ah, e me lembra de ver a pressão da bomba", ["arroz"]),
    ("Adiciona 2 kg de batata e 1 de cebola", ["batata", "cebola"]),
    ("Preciso de farinha e fermento, vou tentar fazer pão hoje", ["farinha", "fermento"]),
    ("Bota na lista: tomate, alface e pepino. Amanhã tem churrasco", ["tomate", "alface", "pepino"]),
    ("Não esquece: papel higiênico e detergente. Tem mais algo importante?", ["papel higiênico", "detergente"]),
    ("Compra maçã, banana e laranja. E vê se o portão fechou direito", ["maçã", "banana", "laranja"]),
    ("Me adiciona leite condensado e creme de leite. Vai ter sobremesa!", ["leite condensado", "creme de leite"]),
    ("Pega também 1 pacote de café e 2 de açúcar", ["café", "açúcar"]),
    ("Vamos precisar de óleo, sal e vinagre. E deixa as luzes da varanda apagadas", ["óleo", "sal", "vinagre"]),
    ("Anota aí: frango, carne moída e salsicha", ["frango", "carne moída", "salsicha"]),
    ("Coloca sabão em pó e amaciante, acabou tudo", ["sabão em pó", "amaciante"]),
    ("Quero comprar queijo, presunto e pão de forma", ["queijo", "presunto", "pão de forma"]),
    ("Adiciona 3 litros de leite. Vou fazer aquele bolo da vó. Você tem a receita?", ["leite"]),
    ("Compra iogurte natural e granola", ["iogurte natural", "granola"]),
    ("Adiciona milho verde, ervilha e molho de tomate", ["milho verde", "ervilha", "molho de tomate"]),
    ("Preciso de pão integral e peito de peru. E como anda a previsão do tempo?", ["pão integral", "peito de peru"]),
    ("Bota na lista fraldas e lenços umedecidos", ["fraldas", "lenços umedecidos"]),
    ("Lembra de comprar cerveja e carvão pro fim de semana", ["cerveja", "carvão"]),
])
def test_chat_shopping_list_add(message, expected_items):
    # Arrange
    shopping_list_repository, llm_app_service, user_app_service = setup_app_service()
    user = UserAdd(name="Bruno", external_id="1000", summary="")
    user_app_service.add(user)
    chat_request = ChatRequest(external_user_id=user.external_id, message=message)

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")
    shopping_list_items: List[ShoppingListItem] = shopping_list_repository.get_all()

    # Assert
    assert "shopping_list" in intents
    assert output
    for expected_item in expected_items:
        assert any(expected_item in item.name.lower() for item in shopping_list_items), f'"{expected_item}" was found in {shopping_list_items}'
