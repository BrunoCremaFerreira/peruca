"""
MainGraph._handle_final_response camera data URI bypass Unit Tests (TDD RED).

F2 (cameras review plan §3.1): a camera snapshot data URI in ``output_cams``
must NEVER be handed to the merge LLM — a 12B model cannot reproduce megabytes
of base64, so the URI would be truncated/corrupted. The fix splits
``output_cams`` BY LINE: lines starting with ``IMAGE_DATA_URI_PREFIX``
("data:image/", new constant in application/graphs/markers.py) are bypassed
verbatim (same shape as the SHOPPING_LIST_HEADER bypass:
``bypass + "\\n\\n" + merged``); the remaining lines (camera status) keep
flowing through the normal merge.

Detection is by LINE PREFIX, not substring — a sentence merely mentioning
"data:image/" mid-string must NOT be bypassed.

This file mirrors the pattern of TestFinalResponseProtectsListingVerbatim in
test_main_graph_final_response.py.

RED: today ``IMAGE_DATA_URI_PREFIX`` does not exist in markers.py (this module
fails at import) and ``output_cams`` enters the merge ``outputs`` list whole.
"""

import base64
import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.graphs.main_graph import MainGraph
from application.graphs.markers import IMAGE_DATA_URI_PREFIX
from domain.entities import GraphInvokeRequest, User


# ===========================================================================
# Helpers
# ===========================================================================


def _request(message: str = "mostra a câmera e acende a luz") -> GraphInvokeRequest:
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


def _png_data_uri() -> str:
    """A realistic (small) PNG snapshot data URI, as produced by the cameras graph."""
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDRfake_png_payload"
    encoded = base64.b64encode(png_bytes).decode()
    return f"{IMAGE_DATA_URI_PREFIX}png;base64,{encoded}"


# ===========================================================================
# TestFinalResponseCameraSnapshotBypass
# ===========================================================================


class TestFinalResponseCameraSnapshotBypass:
    def test_final_response__data_uri_in_output_cams_and_second_output__merge_llm_not_called_with_uri(
        self,
    ):
        """
        With a data URI in output_cams plus two mergeable outputs, the merge
        LLM runs — but its rendered input must NOT contain the URI (nor any
        'data:image/' fragment).
        """
        graph = _make_main_graph(merge_content="Liguei a luz. Tudo certo!")
        uri = _png_data_uri()
        data = {
            "input": _request(),
            "intent": ["smart_home_security_cams", "smart_home_lights", "only_talking"],
            "output_cams": uri,
            "output_lights": "Ligado: sala",
            "output_only_talking": "Tudo certo!",
        }

        graph._handle_final_response(data)

        graph.llm_chat.assert_called_once()
        rendered = str(graph.llm_chat.call_args.args[0])
        assert IMAGE_DATA_URI_PREFIX not in rendered, (
            f"Camera data URI leaked into the merge LLM input: {rendered[:200]!r}"
        )

    def test_final_response__data_uri_and_conversational_output__uri_byte_identical_in_final_output(
        self,
    ):
        """
        The URI must survive BYTE-IDENTICAL as a whole line of the final
        output (exact line equality, not just a prefix `in` check).
        """
        graph = _make_main_graph(merge_content="Liguei a luz. Que legal!")
        uri = _png_data_uri()
        data = {
            "input": _request(),
            "intent": ["smart_home_security_cams", "smart_home_lights", "only_talking"],
            "output_cams": uri,
            "output_lights": "Ligado: sala",
            "output_only_talking": "Que legal!",
        }

        result = graph._handle_final_response(data)

        assert uri in result["output"].splitlines(), (
            f"Expected the data URI byte-identical as a full line of the final "
            f"output, got lines: "
            f"{[line[:60] for line in result['output'].splitlines()]!r}"
        )

    def test_final_response__data_uri_and_conversational_output__merged_text_preserved(
        self,
    ):
        """
        The bypass must not drop the legitimate merged conversational content —
        the user still hears about the light and the chit-chat.
        """
        graph = _make_main_graph(merge_content="Liguei a luz da sala. Que fome, hein!")
        uri = _png_data_uri()
        data = {
            "input": _request(),
            "intent": ["smart_home_security_cams", "smart_home_lights", "only_talking"],
            "output_cams": uri,
            "output_lights": "Ligado: sala",
            "output_only_talking": "Que fome!",
        }

        result = graph._handle_final_response(data)

        assert "Liguei a luz da sala. Que fome, hein!" in result["output"], (
            f"Merged conversational content was dropped when a camera URI was "
            f"present: {result['output'][:200]!r}"
        )
        assert uri in result["output"], (
            "The camera URI must also be present alongside the merged text"
        )

    def test_final_response__data_uri_single_intent__no_merge_llm_call_and_output_is_uri(
        self,
    ):
        """
        Regression of the len(outputs) <= 1 path: a lone camera URI must be
        returned verbatim without any merge LLM call.
        """
        graph = _make_main_graph(merge_content="MERGED (should not appear)")
        uri = _png_data_uri()
        data = {
            "input": _request("mostra a câmera da sala"),
            "intent": ["smart_home_security_cams"],
            "output_cams": uri,
        }

        result = graph._handle_final_response(data)

        graph.llm_chat.assert_not_called()
        graph.llm_chat.invoke.assert_not_called()
        assert result["output"] == uri, (
            f"A lone camera URI must be returned verbatim, got: "
            f"{result['output'][:80]!r}"
        )

    def test_final_response__camera_status_text_in_output_cams__goes_through_normal_merge(
        self,
    ):
        """
        A status-only output_cams (no URI line) must keep flowing through the
        normal merge — the bypass applies only to data URI lines.
        """
        graph = _make_main_graph(merge_content="A câmera está gravando e a luz acesa.")
        data = {
            "input": _request("a câmera está gravando? e acende a luz"),
            "intent": ["smart_home_security_cams", "smart_home_lights"],
            "output_cams": "Camera Sala: gravando",
            "output_lights": "Ligado: sala",
        }

        result = graph._handle_final_response(data)

        graph.llm_chat.assert_called_once()
        rendered = str(graph.llm_chat.call_args.args[0])
        assert "Camera Sala: gravando" in rendered, (
            f"Camera status text must be merged normally, rendered: "
            f"{rendered[:200]!r}"
        )
        assert result["output"] == "A câmera está gravando e a luz acesa.", (
            "With no URI line there is nothing to bypass — the output must be "
            f"the plain merge result, got: {result['output']!r}"
        )

    def test_final_response__output_cams_with_uri_and_status_lines__status_merged_uri_bypassed(
        self,
    ):
        """
        Pins the §3.1 decision: output_cams is split BY LINE. The URI line is
        bypassed; the status line joins the merge with the other outputs.
        """
        graph = _make_main_graph(merge_content="Garagem gravando e luz acesa.")
        uri = _png_data_uri()
        data = {
            "input": _request("mostra a sala, a garagem tá gravando? e acende a luz"),
            "intent": ["smart_home_security_cams", "smart_home_lights"],
            "output_cams": f"{uri}\nCamera Garagem: gravando",
            "output_lights": "Ligado: sala",
        }

        result = graph._handle_final_response(data)

        graph.llm_chat.assert_called_once()
        rendered = str(graph.llm_chat.call_args.args[0])
        assert "Camera Garagem: gravando" in rendered, (
            f"The status line must go through the merge, rendered: "
            f"{rendered[:200]!r}"
        )
        assert IMAGE_DATA_URI_PREFIX not in rendered, (
            f"The URI line leaked into the merge LLM input: {rendered[:200]!r}"
        )
        assert uri in result["output"].splitlines(), (
            "The bypassed URI must still be a full line of the final output"
        )
        assert "Garagem gravando e luz acesa." in result["output"], (
            f"The merged text must be preserved, got: {result['output'][:200]!r}"
        )

    def test_final_response__merge_llm_returns_empty__uri_still_present(self):
        """
        Even when the merge LLM returns an empty string (fallback to the raw
        outputs), the bypassed URI must still be present in the final output.
        """
        graph = _make_main_graph(merge_content="")
        uri = _png_data_uri()
        data = {
            "input": _request(),
            "intent": ["smart_home_security_cams", "smart_home_lights", "only_talking"],
            "output_cams": uri,
            "output_lights": "Ligado: sala",
            "output_only_talking": "Tudo certo!",
        }

        result = graph._handle_final_response(data)

        assert uri in result["output"], (
            f"URI lost when the merge LLM returned empty: "
            f"{result['output'][:200]!r}"
        )
        assert "Ligado: sala" in result["output"], (
            "The raw fallback outputs must also survive an empty merge"
        )

    def test_final_response__text_mentioning_data_image_mid_string__not_bypassed(self):
        """
        Bypass detection is by LINE PREFIX, not substring: a sentence that
        merely mentions 'data:image/' mid-string must flow through the merge.
        """
        graph = _make_main_graph(merge_content="Explicado e luz acesa.")
        sentence = "O formato retornado costuma ser data:image/png em base64."
        data = {
            "input": _request("como funciona o snapshot? e acende a luz"),
            "intent": ["smart_home_security_cams", "smart_home_lights"],
            "output_cams": sentence,
            "output_lights": "Ligado: sala",
        }

        result = graph._handle_final_response(data)

        graph.llm_chat.assert_called_once()
        rendered = str(graph.llm_chat.call_args.args[0])
        assert sentence in rendered, (
            f"A mid-string 'data:image/' mention must NOT be bypassed — the "
            f"whole sentence belongs in the merge input: {rendered[:200]!r}"
        )
        assert result["output"] == "Explicado e luz acesa.", (
            "Nothing was bypassed, so the output must be the plain merge "
            f"result, got: {result['output']!r}"
        )
