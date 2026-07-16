import uuid
from typing import List

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from application.appservices.view_models import ChatRequest
from domain.entities import ShoppingListItem


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# recent_history seeding helper
#
# The recent_history context hint is built by LlmAppService from the same
# session history that _persist_turn writes (session_id = user.id). Seeding
# human/ai messages directly into that history reproduces a previous
# conversation turn (e.g. Peruca answering a recipe) without paying extra LLM
# calls — mirroring the pattern used by the context-compaction battery.
# ---------------------------------------------------------------------------
RECIPE_QUESTION = "Peruca, como se faz um bolo de laranja?"
RECIPE_ANSWER = (
    "Claro! Para um bolo de laranja simples você vai precisar de: 3 ovos, "
    "1 xícara de açúcar, 1 xícara de leite, 2 xícaras de farinha de trigo, "
    "1 colher de fermento em pó e o suco de 2 laranjas. É só bater tudo no "
    "liquidificador, misturar com a farinha e o fermento e assar por uns 40 "
    "minutos. Fica uma delícia!"
)


def _seed_history(llm_app_service, user_app_service, external_id, turns):
    """Append (human, ai) turns to the user's session history."""
    user_id = user_app_service.get_by_external_id(external_id=external_id).id
    messages = []
    for human, ai in turns:
        messages.append(HumanMessage(content=human))
        messages.append(AIMessage(content=ai))
    llm_app_service.get_session_history(user_id).add_messages(messages)


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


# ======================================================
# Add Items from Conversation Context (recent_history)
# ======================================================


class TestChatShoppingListAddFromRecentHistory:
    def test_chat_add_items__recipe_in_history_and_anaphoric_add__adds_main_ingredients(
        self,
        shopping_list_repo_for_integration,
        llm_app_service,
        user_app_service,
        integration_user,
    ):
        # Arrange — seed a previous turn where Peruca listed the recipe
        _seed_history(
            llm_app_service,
            user_app_service,
            integration_user.external_id,
            [(RECIPE_QUESTION, RECIPE_ANSWER)],
        )
        chat_request = ChatRequest(
            external_user_id=integration_user.external_id,
            message="Adicione esses ingredientes na lista de compras",
        )

        # Act
        response = llm_app_service.chat(chat_request=chat_request)
        intents = response.get("intents")
        output = response.get("output")
        stored_names = [
            item.name.lower()
            for item in shopping_list_repo_for_integration.get_all()
        ]

        # Assert — the anaphoric reference was resolved against the history
        assert "shopping_list" in intents
        assert output
        assert "adicionado" in output.lower(), (
            f'Expected the "Adicionado" section in the output, got: {output}'
        )
        for expected_ingredient in ["ovo", "açúcar", "leite", "farinha"]:
            assert any(expected_ingredient in name for name in stored_names), (
                f'"{expected_ingredient}" was NOT found in stored items: '
                f"{stored_names}"
            )

    def test_chat_add_items__ingredient_already_on_list__reports_both_sections_without_duplicate(
        self,
        shopping_list_repo_for_integration,
        llm_app_service,
        user_app_service,
        integration_user,
    ):
        # Arrange — "farinha de trigo" is already on the list before the add
        existing = ShoppingListItem(
            id=str(uuid.uuid4()), name="farinha de trigo", quantity=1
        )
        shopping_list_repo_for_integration.add(existing)
        _seed_history(
            llm_app_service,
            user_app_service,
            integration_user.external_id,
            [(RECIPE_QUESTION, RECIPE_ANSWER)],
        )
        chat_request = ChatRequest(
            external_user_id=integration_user.external_id,
            message="Adicione esses ingredientes na lista de compras",
        )

        # Act
        response = llm_app_service.chat(chat_request=chat_request)
        intents = response.get("intents")
        output = response.get("output")
        stored_items = shopping_list_repo_for_integration.get_all()
        flour_items = [
            item for item in stored_items if "farinha" in item.name.lower()
        ]

        # Assert — both sections rendered, no duplicate persisted
        assert "shopping_list" in intents
        assert output
        assert "adicionado" in output.lower(), (
            f'Expected the "Adicionado" section in the output, got: {output}'
        )
        assert "já estava" in output.lower(), (
            f'Expected the "Já estava na lista" section in the output, got: {output}'
        )
        assert len(flour_items) == 1, (
            f'Expected a single "farinha" entry (no duplicate), got: '
            f"{[item.name for item in stored_items]}"
        )

    @pytest.mark.parametrize(
        "history_turns",
        [
            pytest.param(None, id="no_history"),
            pytest.param(
                [
                    (
                        "Será que vai chover hoje à tarde?",
                        "Pelo jeito o céu está fechado, é bom levar um "
                        "guarda-chuva se for sair.",
                    ),
                    (
                        "E o jogo de ontem, quem ganhou?",
                        "O time da casa venceu por 2 a 1, com um golaço nos "
                        "acréscimos!",
                    ),
                ],
                id="irrelevant_history",
            ),
        ],
    )
    def test_chat_add_items__explicit_item_with_no_or_irrelevant_history__adds_only_named_item(
        self,
        history_turns,
        shopping_list_repo_for_integration,
        llm_app_service,
        user_app_service,
        integration_user,
    ):
        # Arrange — prompt regression: the history block must never leak items
        if history_turns:
            _seed_history(
                llm_app_service,
                user_app_service,
                integration_user.external_id,
                history_turns,
            )
        chat_request = ChatRequest(
            external_user_id=integration_user.external_id,
            message="Adicione leite na lista de compras",
        )

        # Act
        response = llm_app_service.chat(chat_request=chat_request)
        intents = response.get("intents")
        output = response.get("output")
        stored_items = shopping_list_repo_for_integration.get_all()
        stored_names = [item.name.lower() for item in stored_items]

        # Assert — only the named item was added, nothing from the history
        assert "shopping_list" in intents
        assert output
        assert any("leite" in name for name in stored_names), (
            f'"leite" was NOT found in stored items: {stored_names}'
        )
        assert len(stored_items) == 1, (
            f"Expected only the named item on the list, got: {stored_names}"
        )

    def test_chat_add_items__recipe_in_history_but_message_names_item__ignores_history(
        self,
        shopping_list_repo_for_integration,
        llm_app_service,
        user_app_service,
        integration_user,
    ):
        # Arrange — recipe in history, but the message has no anaphora
        _seed_history(
            llm_app_service,
            user_app_service,
            integration_user.external_id,
            [(RECIPE_QUESTION, RECIPE_ANSWER)],
        )
        chat_request = ChatRequest(
            external_user_id=integration_user.external_id,
            message="Adicione pilhas na lista de compras",
        )

        # Act
        response = llm_app_service.chat(chat_request=chat_request)
        intents = response.get("intents")
        output = response.get("output")
        stored_names = [
            item.name.lower()
            for item in shopping_list_repo_for_integration.get_all()
        ]

        # Assert — only "pilhas"; no recipe ingredient leaked into the list
        assert "shopping_list" in intents
        assert output
        assert any("pilha" in name for name in stored_names), (
            f'"pilhas" was NOT found in stored items: {stored_names}'
        )
        for recipe_ingredient in ["ovo", "açúcar", "leite", "farinha", "laranja", "fermento"]:
            assert all(recipe_ingredient not in name for name in stored_names), (
                f'Recipe ingredient "{recipe_ingredient}" leaked into the list: '
                f"{stored_names}"
            )
