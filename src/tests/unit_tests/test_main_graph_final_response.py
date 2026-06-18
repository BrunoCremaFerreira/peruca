"""
MainGraph._handle_final_response robustness unit tests.

The final-response node runs an LLM merge to compose the user-facing reply.
Qwen3 occasionally returns an empty string for this merge (observed with the
sparse numbered shopping-list payload), which produced an empty ``output`` and
failed integration tests asserting a non-empty response. The node must fall back
to the raw sub-graph outputs whenever the merge yields nothing.
"""

from unittest.mock import MagicMock, patch
import uuid

import pytest

from application.graphs.main_graph import MainGraph
from application.graphs.markers import SHOPPING_LIST_HEADER
from domain.entities import GraphInvokeRequest, User


def _request(message: str = "adiciona leite na lista") -> GraphInvokeRequest:
    uid = str(uuid.uuid4())
    return GraphInvokeRequest(
        message=message,
        user=User(id=uid, external_id=uid, name="Alice", summary=""),
        memories=[],
        context_hints={},
    )


def _make_main_graph(merge_content: str) -> MainGraph:
    llm_chat = MagicMock()
    llm_response = MagicMock()
    llm_response.content = merge_content
    # `prompt | llm_chat` coerces the mock into a RunnableLambda, so the chain
    # calls it via __call__ — configure the call return value, not .invoke.
    llm_chat.return_value = llm_response
    llm_chat.invoke.return_value = llm_response

    sub = MagicMock()
    sub.invoke.return_value = {"output": "ok"}

    with patch.object(MainGraph, "load_prompt", return_value="{input} {responses}"):
        return MainGraph(
            llm_chat=llm_chat,
            only_talk_graph=sub,
            shopping_list_graph=sub,
            smart_home_lights_graph=sub,
            smart_home_climate_graph=sub,
            smart_home_sensors_graph=sub,
        )


class TestFinalResponseEmptyMergeFallback:
    def test_empty_merge__falls_back_to_raw_output(self):
        graph = _make_main_graph(merge_content="")
        data = {
            "input": _request(),
            "intent": ["shopping_list"],
            "output_shopping": "1. Adicionado: leite",
        }

        result = graph._handle_final_response(data)

        assert result["output"].strip(), result
        assert "leite" in result["output"]

    def test_whitespace_only_merge__falls_back_to_raw_output(self):
        graph = _make_main_graph(merge_content="   \n  ")
        data = {
            "input": _request(),
            "intent": ["smart_home_lights", "shopping_list"],
            "output_lights": "Luz acesa.",
            "output_shopping": "1. Adicionado: leite",
        }

        result = graph._handle_final_response(data)

        assert result["output"].strip(), result
        assert "leite" in result["output"] and "Luz acesa." in result["output"]

    def test_valid_merge__is_used_unchanged(self):
        # The merge LLM only runs with 2+ non-empty outputs, so provide two so
        # the merge is actually invoked; its valid output must be used verbatim.
        graph = _make_main_graph(merge_content="Pronto, adicionei o leite.")
        data = {
            "input": _request(),
            "intent": ["smart_home_lights", "shopping_list"],
            "output_lights": "Luz acesa.",
            "output_shopping": "1. Adicionado: leite",
        }

        result = graph._handle_final_response(data)

        assert result["output"] == "Pronto, adicionei o leite."


class TestFinalResponseEmptySubGraphOutputFiltering:
    """
    Hardening of the output filter in _handle_final_response.

    Today the filter keeps every value where ``e is not None``. A sub-graph that
    returns an empty/whitespace string (e.g. ``output_climate == ""``) therefore
    leaks into the numbered ``responses`` payload handed to the merge LLM,
    polluting the prompt with empty bullet points. The filter must also drop
    empty/whitespace strings (``e is not None and e.strip()``).
    """

    def test_empty_string_subgraph_output__is_not_passed_to_merge(self):
        graph = _make_main_graph(merge_content="Luz da sala acesa.")
        data = {
            "input": _request("acende a luz da sala"),
            "intent": [
                "smart_home_lights",
                "shopping_list",
                "smart_home_climate",
            ],
            "output_lights": "Ligado: luz da sala",
            "output_shopping": "Adicionado: leite",
            "output_climate": "",  # empty sub-graph output must be filtered
        }

        graph._handle_final_response(data)

        # The merge prompt template renders {responses}; the chain feeds the
        # resulting ChatPromptValue to llm_chat.__call__. The merge runs because
        # there are two non-empty outputs ("1." and "2."); the filtered empty
        # output must never produce a third "3." bullet.
        graph.llm_chat.assert_called_once()
        rendered = str(graph.llm_chat.call_args.args[0])
        assert "luz da sala" in rendered
        assert "leite" in rendered
        assert "3." not in rendered, (
            f"Empty sub-graph output leaked into merge payload: {rendered!r}"
        )

    def test_whitespace_string_subgraph_output__is_not_passed_to_merge(self):
        graph = _make_main_graph(merge_content="Luz da sala acesa.")
        data = {
            "input": _request("acende a luz da sala"),
            "intent": [
                "smart_home_lights",
                "shopping_list",
                "smart_home_climate",
            ],
            "output_lights": "Ligado: luz da sala",
            "output_shopping": "Adicionado: leite",
            "output_climate": "   \n  ",  # whitespace-only must be filtered
        }

        graph._handle_final_response(data)

        graph.llm_chat.assert_called_once()
        rendered = str(graph.llm_chat.call_args.args[0])
        assert "luz da sala" in rendered
        assert "leite" in rendered
        assert "3." not in rendered, (
            f"Whitespace-only sub-graph output leaked into merge payload: "
            f"{rendered!r}"
        )


class TestFinalResponseSkipMergeForSingleOutput:
    """
    Phase 1 / Change #3 (TDD RED phase).

    The merge LLM call is only meaningful when there are 2+ sub-graph outputs to
    blend. When there is at most one non-empty output, _handle_final_response
    must return that single output directly (or "" if there are none) WITHOUT
    invoking `final_response_prompt | llm_chat`.

    This generalises the existing shortcut that only triggered for the
    `only_talking`-alone case.

    RED: today the single-output shortcut only fires when
    intent == ["only_talking"]. For a lone `smart_home_lights` output the code
    still calls the merge LLM, and the zero-output case risks an IndexError on
    `outputs[0]`.
    """

    def test_single_non_empty_output__llm_not_invoked_and_returns_that_output(self):
        graph = _make_main_graph(merge_content="MERGED (should not appear)")
        data = {
            "input": _request("acende a luz da sala"),
            "intent": ["smart_home_lights"],
            "output_lights": "Ligado: sala",
        }

        result = graph._handle_final_response(data)

        graph.llm_chat.assert_not_called()
        graph.llm_chat.invoke.assert_not_called()
        assert result["output"] == "Ligado: sala", (
            "A single non-empty sub-graph output must be returned verbatim "
            "without calling the merge LLM."
        )

    def test_only_talking_alone__still_returns_direct_output_without_llm(self):
        """Existing behaviour for `only_talking` alone must be preserved."""
        graph = _make_main_graph(merge_content="MERGED (should not appear)")
        data = {
            "input": _request("como você está?"),
            "intent": ["only_talking"],
            "output_only_talking": "Estou bem, obrigado!",
        }

        result = graph._handle_final_response(data)

        graph.llm_chat.assert_not_called()
        graph.llm_chat.invoke.assert_not_called()
        assert result["output"] == "Estou bem, obrigado!"

    def test_two_non_empty_outputs__merge_llm_is_invoked(self):
        graph = _make_main_graph(merge_content="Luz acesa e leite adicionado.")
        data = {
            "input": _request("acende a luz e adiciona leite"),
            "intent": ["smart_home_lights", "shopping_list"],
            "output_lights": "Ligado: sala",
            "output_shopping": "1. Adicionado: leite",
        }

        result = graph._handle_final_response(data)

        # With 2+ outputs the merge chain must run (llm_chat called via __call__).
        assert graph.llm_chat.called or graph.llm_chat.invoke.called, (
            "With two non-empty outputs the merge LLM must be invoked."
        )
        assert result["output"] == "Luz acesa e leite adicionado.", (
            "The output must be the merge LLM result when 2+ outputs are present."
        )

    def test_zero_outputs__returns_empty_string_without_llm_and_no_exception(self):
        graph = _make_main_graph(merge_content="MERGED (should not appear)")
        data = {
            "input": _request("..."),
            "intent": ["smart_home_lights"],
            # No output_* keys -> zero non-empty outputs.
        }

        result = graph._handle_final_response(data)

        graph.llm_chat.assert_not_called()
        graph.llm_chat.invoke.assert_not_called()
        assert result["output"] == "", (
            "With zero sub-graph outputs the node must return an empty string "
            "without calling the merge LLM and without raising IndexError."
        )


# ---------------------------------------------------------------------------
# Phase 2 (TDD RED) — a shopping-list LISTING (output_shopping that starts with
# SHOPPING_LIST_HEADER) must be preserved verbatim in the final response and
# must NEVER be sent to the merge LLM. Short confirmations (which do not carry
# the header, e.g. "Adicionado: leite") keep flowing through the merge as today.
# ---------------------------------------------------------------------------


def _listing() -> str:
    """A realistic listing as produced by ShoppingListGraph._format_items."""
    return f"{SHOPPING_LIST_HEADER}\n- leite\n- arroz (2)"


class TestFinalResponseProtectsListingVerbatim:
    def test_listing_with_other_outputs__listing_verbatim_plus_merged_conversation(self):
        """
        Test A: a listing combined with other (mergeable) outputs.

        The listing must appear VERBATIM in result["output"] (it is bypassed from
        the LLM, so the model can never rewrite its bytes), AND the legitimate
        merged conversational content (lights confirmation + free talk) must
        survive alongside it. SHOPPING_LIST_HEADER must NOT appear in the rendered
        input handed to the merge LLM (i.e. the listing was bypassed).
        """
        graph = _make_main_graph(merge_content="Liguei a luz da sala. E que fome, hein!")
        listing = _listing()
        data = {
            "input": _request("o que tem na lista e acende a luz"),
            "intent": ["shopping_list", "smart_home_lights", "only_talking"],
            "output_shopping": listing,
            "output_lights": "Ligado: sala",
            "output_only_talking": "Que fome!",
        }

        result = graph._handle_final_response(data)

        # The listing survives verbatim (exact substring, with newlines/hyphens).
        assert listing in result["output"], (
            f"Listing must be preserved verbatim. output={result['output']!r}"
        )
        # The legitimate merged conversational content must NOT be discarded —
        # the user still hears about the light and the chit-chat.
        assert "Liguei a luz da sala. E que fome, hein!" in result["output"], (
            "Merged conversational content was dropped when a listing was "
            f"present: {result['output']!r}"
        )
        # The listing must have been bypassed from the LLM merge input.
        graph.llm_chat.assert_called_once()
        rendered = str(graph.llm_chat.call_args.args[0])
        assert SHOPPING_LIST_HEADER not in rendered, (
            f"Listing leaked into the merge LLM input: {rendered!r}"
        )

    def test_listing_alone__llm_not_invoked_and_output_is_listing_verbatim(self):
        """
        Test B: a listing as the only output. The merge LLM must NOT be called
        and result["output"] must equal the listing verbatim.
        """
        graph = _make_main_graph(merge_content="MERGED (should not appear)")
        listing = _listing()
        data = {
            "input": _request("o que tem na lista de compras?"),
            "intent": ["shopping_list"],
            "output_shopping": listing,
        }

        result = graph._handle_final_response(data)

        graph.llm_chat.assert_not_called()
        graph.llm_chat.invoke.assert_not_called()
        assert result["output"] == listing, (
            f"A lone listing must be returned verbatim, got: {result['output']!r}"
        )

    def test_multi_output_with_listing__no_numbered_prefix_lines(self):
        """
        Test C (anti-numbering regression): with a listing plus other outputs,
        no line in the final output may start with a numbered prefix "1. "/"2. ".
        """
        graph = _make_main_graph(merge_content="Luz acesa.")
        data = {
            "input": _request("o que tem na lista e acende a luz"),
            "intent": ["shopping_list", "smart_home_lights"],
            "output_shopping": _listing(),
            "output_lights": "Ligado: sala",
        }

        result = graph._handle_final_response(data)

        for line in result["output"].splitlines():
            assert not line.startswith("1. "), (
                f"Numbered prefix leaked into final response: {line!r}"
            )
            assert not line.startswith("2. "), (
                f"Numbered prefix leaked into final response: {line!r}"
            )
