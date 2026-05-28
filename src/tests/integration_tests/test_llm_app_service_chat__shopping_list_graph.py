import uuid
from typing import List

import pytest

from application.appservices.view_models import ChatRequest
from domain.entities import ShoppingListItem


pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "message, expected_items",
    [
        ("Adicione ovos e ligue a luz da sala", ["ovos"]),
        (
            "Coloca leite, pão e manteiga na lista, por favor",
            ["leite", "pão", "manteiga"],
        ),
        (
            "A gente precisa comprar arroz. Ah, e me lembra de ver a pressão da bomba",
            ["arroz"],
        ),
        ("Adiciona 2 kg de batata e 1 de cebola", ["batata", "cebola"]),
        (
            "Preciso de farinha e fermento, vou tentar fazer pão hoje",
            ["farinha", "fermento"],
        ),
        (
            "Bota na lista: tomate, alface e pepino. Amanhã tem churrasco",
            ["tomate", "alface", "pepino"],
        ),
        (
            "Não esquece: papel higiênico e detergente. Tem mais algo importante?",
            ["papel higiênico", "detergente"],
        ),
        (
            "Compra maçã, banana e laranja. E vê se o portão fechou direito",
            ["maçã", "banana", "laranja"],
        ),
        (
            "Me adiciona leite condensado e creme de leite. Vai ter sobremesa!",
            ["leite condensado", "creme de leite"],
        ),
        ("Pega também 1 pacote de café e 2 de açúcar", ["café", "açúcar"]),
        (
            "Vamos precisar de óleo, sal e vinagre. E deixa as luzes da varanda apagadas",
            ["óleo", "sal", "vinagre"],
        ),
        (
            "Anota aí: frango, carne moída e salsicha",
            ["frango", "carne moída", "salsicha"],
        ),
        ("Coloca sabão em pó e amaciante, acabou tudo", ["sabão em pó", "amaciante"]),
        (
            "Quero comprar queijo, presunto e pão de forma",
            ["queijo", "presunto", "pão de forma"],
        ),
        (
            "Adiciona 3 litros de leite. Vou fazer aquele bolo da vó. Você tem a receita?",
            ["leite"],
        ),
        ("Compra iogurte natural e granola", ["iogurte natural", "granola"]),
        (
            "Adiciona milho verde, ervilha e molho de tomate",
            ["milho verde", "ervilha", "molho de tomate"],
        ),
        (
            "Preciso de pão integral e peito de peru. E como anda a previsão do tempo?",
            ["pão integral", "peito de peru"],
        ),
        ("Bota na lista fraldas e lenços umedecidos", ["fraldas", "lenços umedecidos"]),
        ("Lembra de comprar cerveja e carvão pro fim de semana", ["cerveja", "carvão"]),
    ],
)
def test_chat_shopping_list_add(
    message,
    expected_items,
    shopping_list_repo_for_integration,
    llm_app_service,
    integration_user,
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")
    shopping_list_items: List[ShoppingListItem] = (
        shopping_list_repo_for_integration.get_all()
    )

    # Assert
    assert "shopping_list" in intents
    assert output
    for expected_item in expected_items:
        assert any(
            expected_item in item.name.lower() for item in shopping_list_items
        ), f'"{expected_item}" was NOT found in {shopping_list_items}'


@pytest.mark.parametrize(
    "initial_items, message, expected_removed",
    [
        (
            ["ovos", "leite"],
            "Ah, tira os ovos da lista e vê se apagou a luz da cozinha",
            ["ovos"],
        ),
        (
            ["pão", "manteiga", "café"],
            "Por favor, remove manteiga e café da lista. Ah, e como tá o tempo?",
            ["manteiga", "café"],
        ),
        (
            ["arroz", "feijão", "açúcar"],
            "Acho que não precisa mais de arroz nem feijão. Deixa só o açúcar",
            ["arroz", "feijão"],
        ),
        (
            ["tomate", "pepino", "alface"],
            "Pode apagar tomate, alface e pepino da lista? E lembra de verificar o portão",
            ["tomate", "alface", "pepino"],
        ),
        (
            ["sabão em pó", "amaciante"],
            "O sabão em pó, pode tirar da lista. E a máquina de lavar já terminou o ciclo?",
            ["sabão em pó"],
        ),
        (
            ["banana", "laranja", "maçã"],
            "Não esquece de tirar maçã e banana. A laranja ainda deixa por enquanto",
            ["maçã", "banana"],
        ),
        (
            ["óleo", "sal", "vinagre"],
            "Tira o sal e o vinagre, e por favor vê se o alarme tá ativado",
            ["sal", "vinagre"],
        ),
        (
            ["queijo", "presunto", "pão de forma"],
            "Pode remover o presunto e o pão de forma. Deixa o queijo!",
            ["presunto", "pão de forma"],
        ),
        (
            ["iogurte natural", "granola"],
            "Só tira o iogurte natural, mas mantém a granola que ainda tem pouca",
            ["iogurte natural"],
        ),
        (
            ["cerveja", "carvão"],
            "Cerveja e carvão já comprei, pode apagar da lista. A churrasqueira tá ok?",
            ["cerveja", "carvão"],
        ),
    ],
)
def test_chat_shopping_list_remove_with_noise(
    initial_items,
    message,
    expected_removed,
    shopping_list_repo_for_integration,
    llm_app_service,
    integration_user,
):
    # Arrange
    for item_name in initial_items:
        item = ShoppingListItem(id=str(uuid.uuid4()), name=item_name, quantity=1)
        shopping_list_repo_for_integration.add(item)

    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")
    shopping_list_items = shopping_list_repo_for_integration.get_all()

    # Assert
    assert "shopping_list" in intents
    assert output
    for removed_item in expected_removed:
        assert all(
            removed_item.lower() not in s.name.lower() for s in shopping_list_items
        ), f'"{removed_item}" still available on {shopping_list_items}'


@pytest.mark.parametrize(
    "add_messages, expected_items",
    [
        (["Adiciona ovos na lista", "Adiciona leite na lista"], ["ovos", "leite"]),
        (["Coloca pão, manteiga e café na lista"], ["pão", "manteiga", "café"]),
        (["Adiciona arroz, feijão e açúcar na lista"], ["arroz", "feijão", "açúcar"]),
    ],
)
def test_chat_shopping_list_show__items_added_via_chat__items_persisted_in_db(
    add_messages,
    expected_items,
    shopping_list_repo_for_integration,
    llm_app_service,
    integration_user,
):
    # Arrange — add items through the LLM service
    for msg in add_messages:
        add_request = ChatRequest(
            external_user_id=integration_user.external_id, message=msg
        )
        llm_app_service.chat(chat_request=add_request)

    # Act — request listing through the LLM service
    list_request = ChatRequest(
        external_user_id=integration_user.external_id,
        message="O que tem na minha lista de compras?",
    )
    response = llm_app_service.chat(chat_request=list_request)
    intents = response.get("intents")
    output = response.get("output")

    # Verify items are persisted in the database
    stored_items: List[ShoppingListItem] = shopping_list_repo_for_integration.get_all()
    stored_names = [item.name.lower() for item in stored_items]

    # Assert
    assert "shopping_list" in intents
    assert output
    for expected_item in expected_items:
        assert any(expected_item.lower() in name for name in stored_names), (
            f'"{expected_item}" was NOT found in stored items: {stored_names}'
        )


# ======================================================
# Clear Items
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "Limpa a minha lista de compras",
        "Apaga tudo da lista",
        "Remove todos os itens da lista de compras",
    ],
)
def test_chat_shopping_list_clear__clear_intent__list_is_empty_after(
    message, shopping_list_repo_for_integration, llm_app_service, integration_user
):
    # Arrange — add items to the list before clearing
    for item_name in ["ovos", "leite", "pão"]:
        item = ShoppingListItem(id=str(uuid.uuid4()), name=item_name, quantity=1)
        shopping_list_repo_for_integration.add(item)

    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")
    remaining_items: List[ShoppingListItem] = (
        shopping_list_repo_for_integration.get_all()
    )

    # Assert
    assert "shopping_list" in intents
    assert output
    assert remaining_items == [], (
        f"List should be empty but contains: {remaining_items}"
    )


# ======================================================
# Stub Intents — Smoke Tests (no exception is the goal)
# ======================================================


@pytest.mark.parametrize(
    "message",
    [
        "Marca os ovos como comprados",
        "Marca o leite como verificado na lista",
    ],
)
def test_chat_shopping_list_check_item__stub_intent__returns_response_without_exception(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act — should not raise any exception even though check_item is a stub
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert
    assert "shopping_list" in intents
    assert output is not None


@pytest.mark.parametrize(
    "message",
    [
        "Desmarca o leite da lista",
        "Tira o check do arroz",
    ],
)
def test_chat_shopping_list_uncheck_item__stub_intent__returns_response_without_exception(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act — should not raise any exception even though uncheck_item is a stub
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert
    assert "shopping_list" in intents
    assert output is not None


@pytest.mark.parametrize(
    "message",
    [
        "Muda o nome do leite para leite integral",
        "Edita o item arroz para arroz parboilizado",
    ],
)
def test_chat_shopping_list_edit_item__stub_intent__returns_response_without_exception(
    message, llm_app_service, integration_user
):
    # Arrange
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id, message=message
    )

    # Act — should not raise any exception even though edit_item is a stub
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert
    assert "shopping_list" in intents
    assert output is not None
