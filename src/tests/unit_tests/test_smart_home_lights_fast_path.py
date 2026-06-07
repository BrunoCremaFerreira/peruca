"""
SmartHomeLightsGraph deterministic fast-path unit tests — Change #5 (TDD RED).

The lights graph resolves aliases to entity ids in `_find_entity_ids`. Today it
goes STRAIGHT to the LLM (`asyncio.run(self.llm_chat.ainvoke(...))`). The climate
graph already does the right thing: it first asks the domain service
(`smart_home_service.find_entity_ids_by_alias`) and only falls back to the LLM
when the deterministic lookup returns an empty list.

Desired contract for the lights graph (mirroring climate):
  - When `smart_home_service.find_entity_ids_by_alias(...)` returns a NON-empty
    list, `_find_entity_ids` returns that list and DOES NOT call the LLM.
  - When it returns `[]`, the existing LLM parser path runs and its parsed output
    is returned.
  - `find_entity_ids_by_alias` is invoked with `available_entities or {}` (so a
    `None` argument becomes `{}`).

These tests are written BEFORE the implementation and are expected to FAIL today,
because the fast-path does not exist yet (the LLM is always called).

External IO is avoided: `llm_chat` and `smart_home_service` are mocks, the
repositories are mocks, and `Graph.load_prompt` is patched so no prompt file is
read.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.graphs.smart_home_lights_graph import SmartHomeLightsGraph


# ===========================================================================
# Helpers
# ===========================================================================


def _make_graph(find_entity_ids_return):
    """
    Build a SmartHomeLightsGraph with fully mocked dependencies.

    `smart_home_service.find_entity_ids_by_alias` is configured to return
    `find_entity_ids_return`. `llm_chat.ainvoke` is an AsyncMock that, when
    awaited, yields an object whose `.content` is "light.from_llm" — used only to
    assert the LLM fallback path.
    """
    llm_chat = MagicMock()
    llm_response = MagicMock()
    llm_response.content = "light.from_llm"
    llm_chat.ainvoke = AsyncMock(return_value=llm_response)

    smart_home_service = MagicMock()
    smart_home_service.find_entity_ids_by_alias = MagicMock(
        return_value=find_entity_ids_return
    )

    entity_alias_repository = MagicMock()
    area_repository = MagicMock()

    # Patch load_prompt so the constructor (and the LLM fallback) never touches
    # the filesystem and the ChatPromptTemplate gets a benign template.
    with patch.object(
        SmartHomeLightsGraph, "load_prompt", return_value="{input} {available_entities}"
    ):
        graph = SmartHomeLightsGraph(
            llm_chat=llm_chat,
            smart_home_service=smart_home_service,
            smart_home_entity_alias_repository=entity_alias_repository,
            smart_home_area_repository=area_repository,
        )

    return graph, llm_chat, smart_home_service


# ===========================================================================
# Fast-path (deterministic) — no LLM
# ===========================================================================


class TestSmartHomeLightsFastPath:
    def test_find_entity_ids__deterministic_hit__returns_list_without_calling_llm(
        self,
    ):
        """
        When the domain service resolves the alias deterministically (non-empty
        list), `_find_entity_ids` must return that list and the LLM must NOT be
        called.
        """
        graph, llm_chat, smart_home_service = _make_graph(
            find_entity_ids_return=["light.sala"]
        )

        with patch.object(
            SmartHomeLightsGraph,
            "load_prompt",
            return_value="{input} {available_entities}",
        ):
            result = graph._find_entity_ids("sala", {"sala": "light.sala"})

        assert result == ["light.sala"]
        llm_chat.ainvoke.assert_not_called()

    def test_find_entity_ids__deterministic_hit__queries_service_with_available_entities(
        self,
    ):
        """
        The deterministic lookup must be called with the alias and the provided
        available_entities mapping.
        """
        graph, _llm_chat, smart_home_service = _make_graph(
            find_entity_ids_return=["light.sala"]
        )

        with patch.object(
            SmartHomeLightsGraph,
            "load_prompt",
            return_value="{input} {available_entities}",
        ):
            graph._find_entity_ids("sala", {"sala": "light.sala"})

        smart_home_service.find_entity_ids_by_alias.assert_called_once_with(
            query_alias="sala",
            available_entities={"sala": "light.sala"},
        )

    def test_find_entity_ids__none_available_entities__passes_empty_dict_to_service(
        self,
    ):
        """
        When available_entities is None, the service must be queried with `{}`
        (the `available_entities or {}` contract).
        """
        graph, _llm_chat, smart_home_service = _make_graph(
            find_entity_ids_return=["light.sala"]
        )

        with patch.object(
            SmartHomeLightsGraph,
            "load_prompt",
            return_value="{input} {available_entities}",
        ):
            graph._find_entity_ids("sala", None)

        smart_home_service.find_entity_ids_by_alias.assert_called_once_with(
            query_alias="sala",
            available_entities={},
        )


# ===========================================================================
# Fallback (LLM) path — deterministic miss
# ===========================================================================


class TestSmartHomeLightsLlmFallback:
    def test_find_entity_ids__deterministic_miss__falls_back_to_llm(self):
        """
        When the deterministic lookup returns `[]`, the LLM parser path must run
        and its parsed output must be returned.
        """
        graph, llm_chat, _smart_home_service = _make_graph(find_entity_ids_return=[])

        with patch.object(
            SmartHomeLightsGraph,
            "load_prompt",
            return_value="{input} {available_entities}",
        ):
            result = graph._find_entity_ids("sala", {"sala": "light.sala"})

        llm_chat.ainvoke.assert_called_once()
        assert result == ["light.from_llm"]
