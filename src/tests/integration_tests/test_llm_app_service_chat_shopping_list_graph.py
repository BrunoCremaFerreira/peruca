import os
from typing import List
from unittest.mock import patch
import uuid

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
    "NLP_SPACY_MODEL": "pt_core_news_sm",
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


@pytest.mark.parametrize("initial_items, message, expected_removed", [
    (["ovos", "leite"], "Ah, tira os ovos da lista e vê se apagou a luz da cozinha", ["ovos"]),
    (["pão", "manteiga", "café"], "Por favor, remove manteiga e café da lista. Ah, e como tá o tempo?", ["manteiga", "café"]),
    (["arroz", "feijão", "açúcar"], "Acho que não precisa mais de arroz nem feijão. Deixa só o açúcar", ["arroz", "feijão"]),
    (["tomate", "pepino", "alface"], "Pode apagar tomate, alface e pepino da lista? E lembra de verificar o portão", ["tomate", "alface", "pepino"]),
    (["sabão em pó", "amaciante"], "O sabão em pó, pode tirar da lista. E a máquina de lavar já terminou o ciclo?", ["sabão em pó"]),
    (["banana", "laranja", "maçã"], "Não esquece de tirar maçã e banana. A laranja ainda deixa por enquanto", ["maçã", "banana"]),
    (["óleo", "sal", "vinagre"], "Tira o sal e o vinagre, e por favor vê se o alarme tá ativado", ["sal", "vinagre"]),
    (["queijo", "presunto", "pão de forma"], "Pode remover o presunto e o pão de forma. Deixa o queijo!", ["presunto", "pão de forma"]),
    (["iogurte natural", "granola"], "Só tira o iogurte natural, mas mantém a granola que ainda tem pouca", ["iogurte natural"]),
    (["cerveja", "carvão"], "Cerveja e carvão já comprei, pode apagar da lista. A churrasqueira tá ok?", ["cerveja", "carvão"]),
])
def test_chat_shopping_list_remove_with_noise(initial_items, message, expected_removed):
    # Arrange
    shopping_list_repository, llm_app_service, user_app_service = setup_app_service()
    user = UserAdd(name="Bruno", external_id="1000", summary="")
    user_app_service.add(user)

    for item_name in initial_items:
        item = ShoppingListItem(id=str(uuid.uuid4()), name=item_name, quantity=1)
        shopping_list_repository.add(item)

    chat_request = ChatRequest(external_user_id=user.external_id, message=message)

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")
    shopping_list_items = shopping_list_repository.get_all()

    # Assert
    assert "shopping_list" in intents
    assert output
    for removed_item in expected_removed:
        assert all(removed_item.lower() not in s.name.lower() for s in shopping_list_items), \
            f'"{removed_item}" still available on {shopping_list_items}'

@pytest.mark.parametrize("initial_items, message, expected_listed", [
    (["ovos", "leite"], "O que tem na lista mesmo? Ah, e liga o ventilador", ["ovos", "leite"]),
    (["pão", "manteiga", "café"], "Me mostra a lista de compras, por favor. E me lembre de dar ração pro cachorro mais tarde", ["pão", "manteiga", "café"]),
    (["arroz", "feijão", "açúcar"], "Quais itens já estão na lista? Preciso planejar o mercado", ["arroz", "feijão", "açúcar"]),
    (["tomate", "alface"], "Vê aí o que a gente já colocou na lista. Ah, e a campainha tá funcionando?", ["tomate", "alface"]),
    (["banana", "laranja", "maçã"], "Lista de compras? Tô indo pro mercado. E depois me lembra de checar o gás", ["banana", "laranja", "maçã"]),
    (["sabão em pó", "amaciante"], "O que falta comprar? Ou melhor, o que já tem na lista? E como tá a previsão?", ["sabão em pó", "amaciante"]),
])
def test_chat_shopping_list_show(initial_items, message, expected_listed):
    # Arrange
    shopping_list_repository, llm_app_service, user_app_service = setup_app_service()
    user = UserAdd(name="Bruno", external_id="1000", summary="")
    user_app_service.add(user)

    for item_name in initial_items:
        item = ShoppingListItem(id=str(uuid.uuid4()), name=item_name, quantity=1)
        shopping_list_repository.add(item)

    chat_request = ChatRequest(external_user_id=user.external_id, message=message)

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert
    assert "shopping_list" in intents
    assert output
    for item in expected_listed:
        assert item.lower() in output.lower(), f'"{item}" not found on response: {output}'