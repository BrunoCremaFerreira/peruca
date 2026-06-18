"""End-to-end integration tests for the shopping list, driven through the real
LLM (MainGraph -> ShoppingListGraph), focused on the QUALITY of the final
human-facing reply (``response["output"]``).

These tests lock the recent fix for the shopping list replies, which previously
leaked English text, broken numbered lists with empty items, ugly floats like
"(1.0)" and raw entity/JSON repr. They complement (do not duplicate) the
scenarios in ``test_llm_app_service_chat__shopping_list_graph.py`` (basic add,
remove-with-noise, show, clear and stub intents), adding lifecycle coverage and
output-quality assertions instead.
"""

import uuid

import pytest

from application.appservices.view_models import ChatRequest
from domain.entities import ShoppingListItem


pytestmark = pytest.mark.integration


# Substrings that betray English leaking through into a reply that must be in
# Portuguese. Kept lowercase; callers compare against output.lower().
_ENGLISH_MARKERS = ("shopping list", "the list", "empty")


def _assert_clean_human_output(output):
    """Assert ``output`` is a clean, human-facing Portuguese string.

    Locks the core regressions: no entity repr, no classifier JSON and no raw
    internal node/intent token leaking into the user reply.
    """
    assert isinstance(output, str), f"output must be a str, got {type(output)}"
    assert output.strip(), f"output must not be empty/blank: {output!r}"
    # Entity repr leaking (e.g. "ShoppingListItem(id=..., name=...)").
    assert "ShoppingListItem(" not in output, f"entity repr leaked: {output!r}"
    # Classifier / graph JSON leaking into the reply.
    assert '"intents"' not in output, f"intents JSON leaked: {output!r}"
    assert "{'intents'" not in output, f"intents dict leaked: {output!r}"
    # Internal node name leaking instead of a real answer.
    assert "output_add_item" not in output, f"node token leaked: {output!r}"


def _assert_no_english(output):
    """Assert no English marker substrings appear (case-insensitive)."""
    lowered = output.lower()
    for marker in _ENGLISH_MARKERS:
        assert marker not in lowered, f'English marker "{marker}" found in: {output!r}'


def _assert_empty_in_portuguese(output):
    """Assert the reply signals an empty list in Portuguese (not English)."""
    lowered = output.lower()
    assert ("vazia" in lowered) or ("vazio" in lowered) or ("nada" in lowered), (
        f"reply does not signal an empty list in Portuguese: {output!r}"
    )
    _assert_no_english(output)


class TestShoppingListAddOutputQuality:
    """Quality of the reply when adding items through chat."""

    @pytest.mark.parametrize(
        "message",
        [
            "Adiciona arroz na lista de compras",
            "Coloca leite, pão e manteiga na lista, por favor",
        ],
    )
    def test_add_item__reply_is_clean_human_text(
        self, message, llm_app_service, integration_user
    ):
        """ADD reply must be clean Portuguese, never leaking entity/JSON/node."""
        chat_request = ChatRequest(
            external_user_id=integration_user.external_id, message=message
        )

        response = llm_app_service.chat(chat_request=chat_request)
        intents = response.get("intents")
        output = response.get("output")

        assert "shopping_list" in intents
        _assert_clean_human_output(output)
        _assert_no_english(output)


class TestShoppingListListingOutputQuality:
    """The central bug: quality of the listing reply.

    Locks the regressions of ugly floats ("(1.0)"), broken legacy numbering
    ("1. ", "2. "), entity repr and English text in the listing reply.
    """

    def test_list__after_adding_three_items__reply_is_clean_and_formatted(
        self, llm_app_service, integration_user
    ):
        expected_items = ["arroz", "feijão", "açúcar"]

        # Arrange — add three items through chat.
        add_request = ChatRequest(
            external_user_id=integration_user.external_id,
            message="Adiciona arroz, feijão e açúcar na lista",
        )
        llm_app_service.chat(chat_request=add_request)

        # Act — ask for the listing through chat.
        list_request = ChatRequest(
            external_user_id=integration_user.external_id,
            message="O que tem na minha lista de compras?",
        )
        response = llm_app_service.chat(chat_request=list_request)
        intents = response.get("intents")
        output = response.get("output")

        # Assert
        assert "shopping_list" in intents
        _assert_clean_human_output(output)

        lowered = output.lower()
        # Item names must be present (tolerant lowercase substring match).
        for expected_item in expected_items:
            assert expected_item.lower() in lowered, (
                f'"{expected_item}" missing from listing: {output!r}'
            )

        # Regression: ugly float quantities like "(1.0)"/"(2.0)".
        assert ".0" not in output, f'ugly float ".0" leaked into listing: {output!r}'

        # Regression: broken legacy numbering with empty items.
        for line in output.splitlines():
            assert not line.startswith("1. "), f'legacy numbering "1. ": {output!r}'
            assert not line.startswith("2. "), f'legacy numbering "2. ": {output!r}'

        # Regression: entity repr and English text leaking.
        assert "ShoppingListItem(" not in output, f"entity repr leaked: {output!r}"
        _assert_no_english(output)


class TestShoppingListDeleteWithConfirmation:
    """Deleting an item through chat removes it from the DB and replies cleanly."""

    def test_delete__one_of_two_items__removed_from_db_and_clean_reply(
        self, shopping_list_repo_for_integration, llm_app_service, integration_user
    ):
        # Arrange — pre-populate two items directly in the repository.
        for name in ["arroz", "feijão"]:
            shopping_list_repo_for_integration.add(
                ShoppingListItem(id=str(uuid.uuid4()), name=name, quantity=1)
            )

        chat_request = ChatRequest(
            external_user_id=integration_user.external_id,
            message="Remove o arroz da lista de compras",
        )

        # Act
        response = llm_app_service.chat(chat_request=chat_request)
        intents = response.get("intents")
        output = response.get("output")
        remaining = shopping_list_repo_for_integration.get_all()

        # Assert — item gone from DB.
        assert "shopping_list" in intents
        assert all("arroz" not in i.name.lower() for i in remaining), (
            f'"arroz" still present: {remaining}'
        )
        # Reply quality.
        _assert_clean_human_output(output)
        _assert_no_english(output)


class TestShoppingListFullLifecycle:
    """Sequential add -> list -> delete -> list -> clear -> list on one session."""

    def test_full_lifecycle_add_list_delete_clear(
        self, shopping_list_repo_for_integration, llm_app_service, integration_user
    ):
        external_id = integration_user.external_id

        def chat(message):
            return llm_app_service.chat(
                chat_request=ChatRequest(external_user_id=external_id, message=message)
            )

        # (a) Add milk and rice.
        add_response = chat("Adiciona leite e arroz na lista de compras")
        assert "shopping_list" in add_response.get("intents")
        _assert_clean_human_output(add_response.get("output"))

        # (b) List and validate both present with clean format.
        list_response = chat("O que tem na minha lista de compras?")
        assert "shopping_list" in list_response.get("intents")
        list_output = list_response.get("output")
        _assert_clean_human_output(list_output)
        _assert_no_english(list_output)
        assert "leite" in list_output.lower(), f"milk missing: {list_output!r}"
        assert "arroz" in list_output.lower(), f"rice missing: {list_output!r}"
        assert ".0" not in list_output, f'ugly float leaked: {list_output!r}'

        # (c) Remove rice.
        delete_response = chat("Remove o arroz da lista de compras")
        assert "shopping_list" in delete_response.get("intents")
        _assert_clean_human_output(delete_response.get("output"))
        remaining = shopping_list_repo_for_integration.get_all()
        assert all("arroz" not in i.name.lower() for i in remaining), (
            f'"arroz" should be gone: {remaining}'
        )

        # (d) List again: rice gone, milk stays, clean format.
        list_response_2 = chat("O que ainda tem na lista de compras?")
        assert "shopping_list" in list_response_2.get("intents")
        list_output_2 = list_response_2.get("output")
        _assert_clean_human_output(list_output_2)
        _assert_no_english(list_output_2)
        assert "leite" in list_output_2.lower(), f"milk should remain: {list_output_2!r}"
        assert "arroz" not in list_output_2.lower(), (
            f"rice should be gone from listing: {list_output_2!r}"
        )

        # (e) Clear everything.
        clear_response = chat("Limpa a minha lista de compras")
        assert "shopping_list" in clear_response.get("intents")
        _assert_clean_human_output(clear_response.get("output"))

        # (f) List again: reply signals empty list in Portuguese.
        empty_response = chat("O que tem na minha lista de compras?")
        assert "shopping_list" in empty_response.get("intents")
        empty_output = empty_response.get("output")
        _assert_clean_human_output(empty_output)
        _assert_empty_in_portuguese(empty_output)


class TestShoppingListEmptyListing:
    """Listing an empty list replies 'empty' in Portuguese, never English."""

    def test_list__empty_list__reply_signals_empty_in_portuguese(
        self, llm_app_service, integration_user
    ):
        chat_request = ChatRequest(
            external_user_id=integration_user.external_id,
            message="O que tem na minha lista de compras?",
        )

        response = llm_app_service.chat(chat_request=chat_request)
        intents = response.get("intents")
        output = response.get("output")

        assert "shopping_list" in intents
        _assert_clean_human_output(output)
        _assert_empty_in_portuguese(output)
