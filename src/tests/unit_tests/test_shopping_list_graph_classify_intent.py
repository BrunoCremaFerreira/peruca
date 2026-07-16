"""
ShoppingListGraph._classify_intent Unit Tests

Covers two categories of behaviour:

  1. Happy path — clean, well-formed LLM output is parsed correctly and the
     resulting state dict contains the expected intent and output fields.

  2. Markdown code-fence stripping (Bug 1) — when the LLM wraps its JSON
     response in markdown fences (```json ... ``` or ``` ... ```), the current
     _remove_thinking_tag implementation does NOT strip them, so eval() receives
     a string beginning with "```" and raises SyntaxError.  The fallback path
     then sets intents=["not_recognized"] and the correct action node never runs.

     These tests exercise the FULL pipeline:
       - llm_chat.invoke() returns a MagicMock whose .content is set to the raw
         LLM string (including fences).
       - _remove_thinking_tag is NOT mocked — we want the real (broken) tag
         stripper so that the markdown-fence tests fail today and pass after the
         fix is applied.

  3. Fallback robustness — completely unparseable LLM output must produce
     intent=["not_recognized"] without raising.

NOTE ON HELPER STRATEGY:
  _configure_llm_output sets only llm_chat.invoke().content.  It deliberately
  does NOT mock _remove_thinking_tag so that the markdown-fence test class
  exercises the real cleaning pipeline end-to-end.
"""

import pytest
from unittest.mock import MagicMock, patch

from application.graphs.shopping_list_graph import ShoppingListGraph


# ===========================================================================
# Helpers
# ===========================================================================


def _make_graph() -> ShoppingListGraph:
    """
    Build a ShoppingListGraph with all external dependencies mocked.
    load_prompt is patched to avoid filesystem access.
    """
    llm_chat = MagicMock()
    shopping_list_service = MagicMock()

    with patch.object(ShoppingListGraph, "load_prompt", return_value="{input}"):
        graph = ShoppingListGraph(
            llm_chat=llm_chat,
            shopping_list_service=shopping_list_service,
        )

    return graph


def _configure_llm_output(graph: ShoppingListGraph, raw_string: str) -> None:
    """
    Configure graph.llm_chat so that the LangChain chain returns a response
    object whose .content attribute is raw_string.

    LangChain's pipe operator (prompt | llm_chat) calls llm_chat as a callable
    — i.e. llm_chat(...) — NOT llm_chat.invoke(...).  Therefore we set
    llm_chat.return_value, not llm_chat.invoke.return_value.

    _remove_thinking_tag is intentionally NOT mocked here.  Tests that need the
    full cleaning pipeline (markdown-fence tests) rely on the real implementation
    running against raw_string.
    """
    response = MagicMock()
    response.content = raw_string
    graph.llm_chat.return_value = response


def _make_invoke_request() -> MagicMock:
    """
    Return a minimal MagicMock that satisfies data["input"].message access
    inside _classify_intent.
    """
    request = MagicMock()
    request.message = "test message"
    return request


# ===========================================================================
# TestClassifyIntentDeleteItemValidJson
# ===========================================================================


class TestClassifyIntentDeleteItemValidJson:
    """
    Happy path: the LLM returns clean JSON (no fences, no think tags).
    These tests must PASS with the current implementation.
    """

    def test_classify_delete_item__valid_json__intent_is_delete_item(self):
        """
        Clean JSON with intents=["delete_item"] must produce
        result["intent"] == ["delete_item"].
        """
        graph = _make_graph()
        raw = (
            '{"intents": ["delete_item"], "delete_item": "cerveja,1|carvão,1",'
            ' "add_item": "", "edit_item": "", "check_item": "", "uncheck_item": ""}'
        )
        _configure_llm_output(graph, raw)

        result = graph._classify_intent({"input": _make_invoke_request()})

        assert result["intent"] == ["delete_item"], (
            f"Expected intent=['delete_item'], got {result['intent']!r}"
        )

    def test_classify_delete_item__valid_json__output_delete_item_populated(self):
        """
        The output_delete_item field must be populated with the value extracted
        from the 'delete_item' key in the LLM response.
        """
        graph = _make_graph()
        raw = (
            '{"intents": ["delete_item"], "delete_item": "cerveja,1|carvão,1",'
            ' "add_item": "", "edit_item": "", "check_item": "", "uncheck_item": ""}'
        )
        _configure_llm_output(graph, raw)

        result = graph._classify_intent({"input": _make_invoke_request()})

        assert result.get("output_delete_item") == "cerveja,1|carvão,1", (
            f"Expected output_delete_item='cerveja,1|carvão,1', "
            f"got {result.get('output_delete_item')!r}"
        )


# ===========================================================================
# TestClassifyIntentMarkdownFences  (Bug 1)
# ===========================================================================


class TestClassifyIntentMarkdownFences:
    """
    Bug 1: when the LLM wraps its JSON in markdown code fences, the current
    _remove_thinking_tag does not strip them, causing eval() to raise
    SyntaxError.  The except clause catches it and returns ["not_recognized"],
    so the delete (or any other) action never executes.

    Tests in this class FAIL with the current code and will PASS after
    _remove_thinking_tag (or _classify_intent) is fixed to strip fences.

    _configure_llm_output is used WITHOUT mocking _remove_thinking_tag so that
    the real cleaning pipeline runs against the fenced output.
    """

    def test_classify_delete_item__json_fenced_with_json_lang__intent_is_delete_item(
        self,
    ):
        """
        LLM response wrapped in ```json ... ``` fences must still produce
        result["intent"] == ["delete_item"].

        FAILS with current implementation: eval() raises SyntaxError on the
        opening "```" characters, fallback sets intent=["not_recognized"].
        """
        graph = _make_graph()
        inner_json = (
            '{"intents": ["delete_item"], "delete_item": "cerveja,1|carvão,1",'
            ' "add_item": "", "edit_item": "", "check_item": "", "uncheck_item": ""}'
        )
        raw = f"```json\n{inner_json}\n```"
        _configure_llm_output(graph, raw)

        result = graph._classify_intent({"input": _make_invoke_request()})

        assert result["intent"] == ["delete_item"], (
            f"Expected intent=['delete_item'] when JSON is wrapped in ```json fences, "
            f"got {result['intent']!r}. "
            "Likely cause: _remove_thinking_tag does not strip markdown code fences."
        )

    def test_classify_delete_item__json_fenced_without_lang__intent_is_delete_item(
        self,
    ):
        """
        LLM response wrapped in plain ``` ... ``` fences (no language tag) must
        still produce result["intent"] == ["delete_item"].

        FAILS with current implementation for the same reason as the ```json variant.
        """
        graph = _make_graph()
        inner_json = (
            '{"intents": ["delete_item"], "delete_item": "carvão,1|cerveja,1",'
            ' "add_item": "", "edit_item": "", "check_item": "", "uncheck_item": ""}'
        )
        raw = f"```\n{inner_json}\n```"
        _configure_llm_output(graph, raw)

        result = graph._classify_intent({"input": _make_invoke_request()})

        assert result["intent"] == ["delete_item"], (
            f"Expected intent=['delete_item'] when JSON is wrapped in plain ``` fences, "
            f"got {result['intent']!r}. "
            "Likely cause: _remove_thinking_tag does not strip markdown code fences."
        )


# ===========================================================================
# TestClassifyIntentFallback
# ===========================================================================


class TestClassifyIntentFallback:
    """
    Robustness: completely unparseable LLM output must produce
    intent=["not_recognized"] without raising any exception.
    """

    def test_classify_intent__unparseable_response__returns_not_recognized(self):
        """
        A string that is not valid Python/JSON (e.g. a natural-language sentence)
        must not propagate any exception and must return intent=["not_recognized"].
        """
        graph = _make_graph()
        _configure_llm_output(
            graph, "Desculpe, não entendi o que você quis dizer sobre a lista."
        )

        result = graph._classify_intent({"input": _make_invoke_request()})

        assert result["intent"] == ["not_recognized"], (
            f"Expected intent=['not_recognized'] for unparseable LLM output, "
            f"got {result['intent']!r}"
        )

    def test_classify_intent__empty_string__returns_not_recognized(self):
        """
        An empty string from the LLM must trigger the not_recognized fallback
        without raising.
        """
        graph = _make_graph()
        _configure_llm_output(graph, "")

        result = graph._classify_intent({"input": _make_invoke_request()})

        assert result["intent"] == ["not_recognized"], (
            f"Expected intent=['not_recognized'] for empty LLM output, "
            f"got {result['intent']!r}"
        )


# ===========================================================================
# TestClassifyIntentRecentHistory  (feature: add items from conversation
# context — TDD, RED phase)
# ===========================================================================


def _make_graph_with_history_template() -> ShoppingListGraph:
    """
    Build a graph whose (patched) prompt template declares BOTH variables the
    real shopping_list_graph.md will declare: {recent_history} and {input}.
    _classify_intent must therefore always supply recent_history — with the
    hint value when present, with the literal "(vazio)" otherwise.
    """
    llm_chat = MagicMock()
    shopping_list_service = MagicMock()

    template = "history:\n{recent_history}\nmessage: {input}"
    with patch.object(ShoppingListGraph, "load_prompt", return_value=template):
        graph = ShoppingListGraph(
            llm_chat=llm_chat,
            shopping_list_service=shopping_list_service,
        )

    return graph


def _make_invoke_request_with_hints(context_hints=None) -> "GraphInvokeRequest":
    from domain.entities import GraphInvokeRequest, User

    return GraphInvokeRequest(
        message="adicione esses ingredientes na lista",
        user=User(id="user-1"),
        context_hints=context_hints if context_hints is not None else {},
    )


def _llm_prompt_text(graph: ShoppingListGraph) -> str:
    """The full prompt text the (mocked) LLM was called with."""
    graph.llm_chat.assert_called_once()
    prompt_value = graph.llm_chat.call_args[0][0]
    return prompt_value.to_string()


_VALID_ADD_OUTPUT = (
    "{'intents': ['add_item'], 'add_item': 'ovos,3|leite,1',"
    " 'edit_item': '', 'delete_item': '', 'check_item': '', 'uncheck_item': ''}"
)


class TestClassifyIntentRecentHistory:
    def test_classify_intent__recent_history_hint_present__injected_into_prompt(
        self,
    ):
        """The recent_history context hint must reach the prompt template."""
        graph = _make_graph_with_history_template()
        _configure_llm_output(graph, _VALID_ADD_OUTPUT)
        hint = (
            "usuario: como se faz bolo de laranja?\n"
            "peruca: Você vai precisar de 3 ovos e leite."
        )
        request = _make_invoke_request_with_hints({"recent_history": hint})

        graph._classify_intent({"input": request})

        prompt_text = _llm_prompt_text(graph)
        assert "usuario: como se faz bolo de laranja?" in prompt_text
        assert "peruca: Você vai precisar de 3 ovos e leite." in prompt_text

    def test_classify_intent__no_recent_history_hint__uses_vazio_without_keyerror(
        self,
    ):
        """
        A request without the hint (context_hints has no "recent_history" key)
        must inject the literal "(vazio)" — never raise KeyError against the
        template.
        """
        graph = _make_graph_with_history_template()
        _configure_llm_output(graph, _VALID_ADD_OUTPUT)
        request = _make_invoke_request_with_hints({})

        result = graph._classify_intent({"input": request})

        prompt_text = _llm_prompt_text(graph)
        assert "(vazio)" in prompt_text
        assert result["intent"] == ["add_item"]

    def test_classify_intent__recent_history_hint_none__uses_vazio(self):
        """A None hint value degrades to "(vazio)", never to "None"."""
        graph = _make_graph_with_history_template()
        _configure_llm_output(graph, _VALID_ADD_OUTPUT)
        request = _make_invoke_request_with_hints({"recent_history": None})

        graph._classify_intent({"input": request})

        prompt_text = _llm_prompt_text(graph)
        assert "(vazio)" in prompt_text

    def test_classify_intent__history_with_braces_and_quotes__does_not_break_template(
        self,
    ):
        """
        History content containing "{", "}" and quotes is DATA injected as a
        template variable — it must not be re-interpreted by the template
        engine nor raise.
        """
        graph = _make_graph_with_history_template()
        _configure_llm_output(graph, _VALID_ADD_OUTPUT)
        hint = (
            "usuario: adicione {\"leite\"} e {ovos} na lista\n"
            "peruca: pode deixar, 'anotado'"
        )
        request = _make_invoke_request_with_hints({"recent_history": hint})

        result = graph._classify_intent({"input": request})

        prompt_text = _llm_prompt_text(graph)
        assert '{"leite"}' in prompt_text
        assert "{ovos}" in prompt_text
        assert result["intent"] == ["add_item"]

    def test_classify_intent__single_quoted_llm_output__still_parses_via_literal_eval(
        self,
    ):
        """
        Regression: the parser stays ast.literal_eval — a single-quoted Python
        dict literal from the LLM must keep parsing with the history block in
        the template.
        """
        graph = _make_graph_with_history_template()
        _configure_llm_output(graph, _VALID_ADD_OUTPUT)
        request = _make_invoke_request_with_hints(
            {"recent_history": "usuario: oi\nperuca: olá"}
        )

        result = graph._classify_intent({"input": request})

        assert result["intent"] == ["add_item"]
        assert result["output_add_item"] == "ovos,3|leite,1"
