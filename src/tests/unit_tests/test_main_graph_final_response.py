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
        graph = _make_main_graph(merge_content="Pronto, adicionei o leite.")
        data = {
            "input": _request(),
            "intent": ["shopping_list"],
            "output_shopping": "1. Adicionado: leite",
        }

        result = graph._handle_final_response(data)

        assert result["output"] == "Pronto, adicionei o leite."
