"""
Graph base class unit tests — _extract_structured_output and load_prompt.

Covers the new _extract_structured_output method that replaces the fragile
combination of _remove_thinking_tag + raw eval/json.loads calls that silently
fell back to "only_talking" / "not_recognized" whenever gemma4 (or any model)
produced prose around the structured output.

Contract for _extract_structured_output(raw: str) -> str | None:
  1. Applies _remove_thinking_tag first (removes <think> blocks and bare
     markdown fences that wrap the entire output).
  2. Normalises curly/smart quotes to straight ASCII equivalents.
  3. Finds the FIRST balanced [...] or {...} span in the remaining string.
  4. Returns that substring unchanged, or None if no balanced bracket is found.

Also covers load_prompt with the planned llm_strip_think_directive flag:
  - When True (regardless of provider), the /no_think* line is removed.
  - When False (default), OLLAMA keeps the directive; non-OLLAMA strips it
    (existing behaviour, guarded here as a regression test).

Additionally covers:
  - MainGraph._classify_intent: malformed LLM output → ["only_talking"] + print
  - ShoppingListGraph._classify_intent: malformed output → ["not_recognized"]
"""

import pytest
from unittest.mock import MagicMock, patch, call

from application.graphs.graph import Graph
from domain.entities import GraphInvokeRequest, User


# ===========================================================================
# Minimal concrete Graph for testing the base class in isolation
# ===========================================================================


class _ConcreteGraph(Graph):
    """Minimal non-abstract subclass so Graph can be instantiated directly."""

    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        return {}


def _make_graph(provider: str = "OLLAMA") -> _ConcreteGraph:
    return _ConcreteGraph(provider=provider)


# ===========================================================================
# Shared helpers
# ===========================================================================


def _sample_user() -> User:
    return User(id="u1", external_id="u1", name="Tester", summary="")


def _sample_request(message: str = "test") -> GraphInvokeRequest:
    return GraphInvokeRequest(message=message, user=_sample_user())


# ===========================================================================
# TestExtractStructuredOutputCleanInput
# ===========================================================================


class TestExtractStructuredOutputCleanInput:
    """Input that is already a clean structured literal — must be returned as-is."""

    def test_extract__clean_list__returns_same_string(self):
        graph = _make_graph()
        raw = '["smart_home_lights"]'

        result = graph._extract_structured_output(raw)

        assert result == '["smart_home_lights"]', (
            f"Expected the clean list string unchanged, got {result!r}"
        )

    def test_extract__clean_dict__returns_same_string(self):
        graph = _make_graph()
        raw = '{"intents": ["add_item"], "add_item": "leite,1"}'

        result = graph._extract_structured_output(raw)

        assert result == '{"intents": ["add_item"], "add_item": "leite,1"}', (
            f"Expected the clean dict string unchanged, got {result!r}"
        )

    def test_extract__multi_intent_list__returns_same_string(self):
        graph = _make_graph()
        raw = '["smart_home_lights", "music"]'

        result = graph._extract_structured_output(raw)

        assert result == '["smart_home_lights", "music"]', (
            f"Expected multi-intent list unchanged, got {result!r}"
        )


# ===========================================================================
# TestExtractStructuredOutputProseAround
# ===========================================================================


class TestExtractStructuredOutputProseAround:
    """LLM wraps the literal in natural language — extract only the bracket span."""

    def test_extract__prose_before_list__returns_list_substring(self):
        graph = _make_graph()
        raw = 'The classification is: ["shopping_list"]'

        result = graph._extract_structured_output(raw)

        assert result == '["shopping_list"]', (
            f"Expected list extracted from prose-prefixed output, got {result!r}"
        )

    def test_extract__prose_after_list__returns_list_substring(self):
        graph = _make_graph()
        raw = '["music"] is the intent.'

        result = graph._extract_structured_output(raw)

        assert result == '["music"]', (
            f"Expected list extracted from prose-suffixed output, got {result!r}"
        )

    def test_extract__prose_before_dict__returns_dict_substring(self):
        graph = _make_graph()
        raw = 'Here you go: {"intents": ["add_item"]}'

        result = graph._extract_structured_output(raw)

        assert result == '{"intents": ["add_item"]}', (
            f"Expected dict extracted from prose-prefixed output, got {result!r}"
        )

    def test_extract__prose_surrounding_list__returns_list_substring(self):
        graph = _make_graph()
        raw = 'Based on your request, I classify it as ["only_talking"] because it is conversational.'

        result = graph._extract_structured_output(raw)

        assert result == '["only_talking"]', (
            f"Expected list extracted from surrounding prose, got {result!r}"
        )


# ===========================================================================
# TestExtractStructuredOutputMarkdownFences
# ===========================================================================


class TestExtractStructuredOutputMarkdownFences:
    """LLM wraps the literal in markdown code fences."""

    def test_extract__python_fence_list__returns_list_substring(self):
        graph = _make_graph()
        raw = '```python\n["only_talking"]\n```'

        result = graph._extract_structured_output(raw)

        assert result == '["only_talking"]', (
            f"Expected list extracted from python-fenced output, got {result!r}"
        )

    def test_extract__json_fence_dict__returns_dict_substring(self):
        graph = _make_graph()
        raw = '```json\n{"intents": ["add_item"], "add_item": "leite,1"}\n```'

        result = graph._extract_structured_output(raw)

        assert result == '{"intents": ["add_item"], "add_item": "leite,1"}', (
            f"Expected dict extracted from json-fenced output, got {result!r}"
        )

    def test_extract__plain_fence_list__returns_list_substring(self):
        graph = _make_graph()
        raw = '```\n["smart_home_lights"]\n```'

        result = graph._extract_structured_output(raw)

        assert result == '["smart_home_lights"]', (
            f"Expected list extracted from plain-fenced output, got {result!r}"
        )


# ===========================================================================
# TestExtractStructuredOutputCurlyQuotes
# ===========================================================================


class TestExtractStructuredOutputCurlyQuotes:
    """Models mimicking prompt examples emit curly/smart quotes — must normalise."""

    def test_extract__curly_double_quotes__normalises_and_extracts(self):
        graph = _make_graph()
        raw = '[“only_talking”]'  # ["only_talking"] with U+201C/U+201D

        result = graph._extract_structured_output(raw)

        assert result is not None, "Expected a non-None result for curly-double-quoted list"
        assert "only_talking" in result, (
            f"Expected 'only_talking' in extracted result, got {result!r}"
        )

    def test_extract__curly_single_quotes__normalises_and_extracts(self):
        graph = _make_graph()
        raw = "[‘music’]"  # ['music'] with U+2018/U+2019

        result = graph._extract_structured_output(raw)

        assert result is not None, "Expected a non-None result for curly-single-quoted list"
        assert "music" in result, (
            f"Expected 'music' in extracted result, got {result!r}"
        )

    def test_extract__mixed_curly_quotes__normalises_and_extracts(self):
        graph = _make_graph()
        # ["smart_home_lights", "music"] using various curly quote combinations
        raw = '[“smart_home_lights”, ‘music’]'

        result = graph._extract_structured_output(raw)

        assert result is not None, "Expected a non-None result for mixed curly-quoted list"
        assert "smart_home_lights" in result and "music" in result, (
            f"Expected both intents in result, got {result!r}"
        )


# ===========================================================================
# TestExtractStructuredOutputThinkBlocks
# ===========================================================================


class TestExtractStructuredOutputThinkBlocks:
    """<think> blocks before the structured output must be stripped first."""

    def test_extract__think_block_before_list__returns_list_only(self):
        graph = _make_graph()
        raw = '<think>\nSome internal reasoning.\n</think>\n["shopping_list"]'

        result = graph._extract_structured_output(raw)

        assert result == '["shopping_list"]', (
            f"Expected list after think block was stripped, got {result!r}"
        )

    def test_extract__think_block_before_dict__returns_dict_only(self):
        graph = _make_graph()
        raw = (
            '<think>\nLet me analyze this.\n</think>\n'
            '{"intents": ["add_item"], "add_item": "leite,1"}'
        )

        result = graph._extract_structured_output(raw)

        assert result == '{"intents": ["add_item"], "add_item": "leite,1"}', (
            f"Expected dict after think block was stripped, got {result!r}"
        )


# ===========================================================================
# TestExtractStructuredOutputNoStructure
# ===========================================================================


class TestExtractStructuredOutputNoStructure:
    """When no balanced bracket can be found, must return None."""

    def test_extract__plain_prose__returns_none(self):
        graph = _make_graph()
        raw = 'I cannot classify this.'

        result = graph._extract_structured_output(raw)

        assert result is None, (
            f"Expected None for plain prose without brackets, got {result!r}"
        )

    def test_extract__empty_string__returns_none(self):
        graph = _make_graph()

        result = graph._extract_structured_output('')

        assert result is None, (
            f"Expected None for empty string input, got {result!r}"
        )

    def test_extract__only_whitespace__returns_none(self):
        graph = _make_graph()

        result = graph._extract_structured_output('   \n\t  ')

        assert result is None, (
            f"Expected None for whitespace-only input, got {result!r}"
        )

    def test_extract__unbalanced_open_bracket__returns_none(self):
        graph = _make_graph()
        raw = 'The result is [incomplete'

        result = graph._extract_structured_output(raw)

        assert result is None, (
            f"Expected None for unbalanced bracket, got {result!r}"
        )

    def test_extract__unbalanced_open_brace__returns_none(self):
        graph = _make_graph()
        raw = 'Starting { but never closing'

        result = graph._extract_structured_output(raw)

        assert result is None, (
            f"Expected None for unbalanced brace, got {result!r}"
        )


# ===========================================================================
# TestExtractStructuredOutputFirstMatch
# ===========================================================================


class TestExtractStructuredOutputFirstMatch:
    """When multiple balanced brackets exist, the FIRST one must be returned."""

    def test_extract__two_lists_in_string__returns_first(self):
        graph = _make_graph()
        raw = 'First: ["music"] and also ["shopping_list"]'

        result = graph._extract_structured_output(raw)

        assert result == '["music"]', (
            f"Expected the FIRST bracket span, got {result!r}"
        )

    def test_extract__list_then_dict__returns_first(self):
        graph = _make_graph()
        raw = '["only_talking"] {"extra": "data"}'

        result = graph._extract_structured_output(raw)

        assert result == '["only_talking"]', (
            f"Expected the first span (list) when list appears before dict, got {result!r}"
        )


# ===========================================================================
# TestLoadPromptStripThinkDirectiveFlag
# ===========================================================================


class TestLoadPromptStripThinkDirectiveFlag:
    """
    load_prompt with the planned llm_strip_think_directive=True flag.

    When llm_strip_think_directive=True is passed, the /no_think* line must be
    removed from the prompt regardless of the provider setting.  This is the
    mechanism that will allow gemma4 (which does not support /no_think) to
    receive clean prompts even when the provider is OLLAMA.
    """

    def test_load_prompt__strip_flag_true_ollama__removes_directive(self):
        """
        An OLLAMA provider graph must still strip /no_think when the caller
        explicitly requests stripping via llm_strip_think_directive=True.
        """
        graph = _make_graph(provider="OLLAMA")
        raw = "/no_think\nConteúdo do prompt."

        with patch("pathlib.Path.read_text", return_value=raw):
            result = graph.load_prompt("main_graph.md", llm_strip_think_directive=True)

        assert not result.startswith("/no_think"), (
            "Expected /no_think stripped when llm_strip_think_directive=True, "
            f"even for OLLAMA provider. Got: {result[:50]!r}"
        )

    def test_load_prompt__strip_flag_true__content_preserved(self):
        """
        The prompt body after the directive must be intact when flag is True.
        """
        graph = _make_graph(provider="OLLAMA")
        body = "Você é um assistente doméstico.\nResponda de forma concisa."
        raw = f"/no_think\n{body}"

        with patch("pathlib.Path.read_text", return_value=raw):
            result = graph.load_prompt("main_graph.md", llm_strip_think_directive=True)

        assert body in result, (
            f"Expected prompt body to be preserved after stripping directive, got {result!r}"
        )

    def test_load_prompt__strip_flag_false_ollama__preserves_directive(self):
        """
        Default behaviour (flag=False, provider=OLLAMA): /no_think is kept.
        Regression guard for existing behaviour.
        """
        graph = _make_graph(provider="OLLAMA")
        raw = "/no_think\nConteúdo do prompt."

        with patch("pathlib.Path.read_text", return_value=raw):
            result = graph.load_prompt("main_graph.md", llm_strip_think_directive=False)

        assert result.startswith("/no_think"), (
            "Expected /no_think preserved for OLLAMA with flag=False, "
            f"got: {result[:50]!r}"
        )

    def test_load_prompt__strip_flag_true_no_directive__content_unchanged(self):
        """
        When there is no /no_think directive, stripping must not alter the body.
        """
        graph = _make_graph(provider="OLLAMA")
        raw = "Prompt sem diretiva.\nSegunda linha."

        with patch("pathlib.Path.read_text", return_value=raw):
            result = graph.load_prompt("some_prompt.md", llm_strip_think_directive=True)

        assert result == raw, (
            f"Expected unchanged content when no directive present, got {result!r}"
        )

    def test_load_prompt__strip_flag_true_no_thinking_variant__removes_directive(self):
        """
        The /no_thinking variant must also be removed when the flag is True.
        """
        graph = _make_graph(provider="OLLAMA")
        raw = "/no_thinking\nAlgum conteúdo aqui."

        with patch("pathlib.Path.read_text", return_value=raw):
            result = graph.load_prompt("shopping_list_graph.md", llm_strip_think_directive=True)

        assert not result.startswith("/no_thinking"), (
            "Expected /no_thinking stripped when llm_strip_think_directive=True, "
            f"got: {result[:50]!r}"
        )


# ===========================================================================
# TestMainGraphClassifyIntentMalformedOutput
# ===========================================================================


class TestMainGraphClassifyIntentMalformedOutput:
    """
    MainGraph._classify_intent must fall back to ["only_talking"] and print
    diagnostic output whenever the LLM returns prose it cannot parse.
    """

    def _make_main_graph(self):
        from application.graphs.main_graph import MainGraph

        llm_chat = MagicMock()
        sub = MagicMock()
        sub.invoke.return_value = {"output": "ok"}

        with patch.object(MainGraph, "load_prompt", return_value="{input} {music_is_playing}"):
            graph = MainGraph(
                llm_chat=llm_chat,
                only_talk_graph=sub,
                shopping_list_graph=sub,
                smart_home_lights_graph=sub,
                smart_home_climate_graph=sub,
                smart_home_sensors_graph=sub,
            )
        return graph

    def _make_invoke_data(self, message: str = "test") -> dict:
        request = MagicMock()
        request.message = message
        request.context_hints = {}
        return {"input": request}

    def test_classify_intent__pure_prose__falls_back_to_only_talking(self):
        """
        When _extract_structured_output returns None (no brackets found),
        _classify_intent must set intent to ["only_talking"].
        """
        graph = self._make_main_graph()
        # Bypass LLM + cleaning pipeline; simulate that extract returns None.
        graph._extract_structured_output = MagicMock(return_value=None)

        result = graph._classify_intent(self._make_invoke_data("blablabla"))

        assert result["intent"] == ["only_talking"], (
            f"Expected fallback to ['only_talking'] when no structure found, "
            f"got {result['intent']!r}"
        )

    def test_classify_intent__malformed_output__prints_raw(self, capsys):
        """
        When the LLM output cannot be parsed into a valid intent, the node
        must print diagnostic information that includes the raw LLM string,
        so operators can diagnose model regressions.
        """
        graph = self._make_main_graph()
        raw_output = "Não consigo classificar sua mensagem."
        # Simulate the full cleaning pipeline returning no structure
        graph._extract_structured_output = MagicMock(return_value=None)
        # Make the LLM return the raw string so it can appear in print output
        llm_response = MagicMock()
        llm_response.content = raw_output
        graph.llm_chat.return_value = llm_response

        graph._classify_intent(self._make_invoke_data("???"))

        captured = capsys.readouterr()
        assert raw_output in captured.out, (
            f"Expected raw LLM output printed for diagnostics. "
            f"stdout was: {captured.out!r}"
        )

    def test_classify_intent__extract_returns_unparseable_eval__falls_back(self):
        """
        _extract_structured_output may return a string that still cannot be
        eval()'d (e.g. partial bracket match on garbled text). The except clause
        must catch that and produce ["only_talking"].
        """
        graph = self._make_main_graph()
        # Return something that looks like a bracket span but is not valid Python
        graph._extract_structured_output = MagicMock(return_value="[broken {{")

        result = graph._classify_intent(self._make_invoke_data("???"))

        assert result["intent"] == ["only_talking"], (
            f"Expected ['only_talking'] when eval() fails on extracted span, "
            f"got {result['intent']!r}"
        )

    def test_classify_intent__extract_returns_valid_list__uses_parsed_intent(self):
        """
        Happy path via _extract_structured_output: when the method returns a
        parseable list string, _classify_intent must use it as the intent.
        """
        graph = self._make_main_graph()
        graph._extract_structured_output = MagicMock(return_value='["shopping_list"]')

        result = graph._classify_intent(self._make_invoke_data("adiciona leite"))

        assert result["intent"] == ["shopping_list"], (
            f"Expected ['shopping_list'] from extracted output, got {result['intent']!r}"
        )


# ===========================================================================
# TestShoppingListGraphClassifyIntentMalformedOutput
# ===========================================================================


class TestShoppingListGraphClassifyIntentMalformedOutput:
    """
    ShoppingListGraph._classify_intent must fall back to ["not_recognized"] and
    not raise whenever the LLM emits prose that cannot be parsed.
    """

    def _make_graph(self):
        from application.graphs.shopping_list_graph import ShoppingListGraph

        llm_chat = MagicMock()
        service = MagicMock()

        with patch.object(ShoppingListGraph, "load_prompt", return_value="{input}"):
            graph = ShoppingListGraph(
                llm_chat=llm_chat,
                shopping_list_service=service,
            )
        return graph

    def _make_invoke_data(self, message: str = "test") -> dict:
        request = MagicMock()
        request.message = message
        return {"input": request}

    def test_classify_intent__prose_output__falls_back_to_not_recognized(self):
        """
        When _extract_structured_output returns None, intent must be
        ["not_recognized"] without raising.
        """
        graph = self._make_graph()
        graph._extract_structured_output = MagicMock(return_value=None)

        result = graph._classify_intent(self._make_invoke_data("xyz"))

        assert result["intent"] == ["not_recognized"], (
            f"Expected ['not_recognized'] for unparseable prose, got {result['intent']!r}"
        )

    def test_classify_intent__extract_returns_invalid_dict_string__falls_back(self):
        """
        Even if _extract_structured_output returns a bracket span, if it is not
        a valid dict then the fallback to ["not_recognized"] must trigger.
        """
        graph = self._make_graph()
        graph._extract_structured_output = MagicMock(return_value='{"broken": }')

        result = graph._classify_intent(self._make_invoke_data("???"))

        assert result["intent"] == ["not_recognized"], (
            f"Expected ['not_recognized'] when dict parse fails, got {result['intent']!r}"
        )

    def test_classify_intent__extract_returns_valid_dict__uses_intents_key(self):
        """
        Happy path: when extracted string is a valid dict with an 'intents' key,
        the intents must be used as the intent list.
        """
        graph = self._make_graph()
        graph._extract_structured_output = MagicMock(
            return_value='{"intents": ["add_item"], "add_item": "leite,1"}'
        )

        result = graph._classify_intent(self._make_invoke_data("adiciona leite"))

        assert result["intent"] == ["add_item"], (
            f"Expected ['add_item'] from extracted dict, got {result['intent']!r}"
        )

    def test_classify_intent__extract_returns_dict_missing_intents_key__falls_back(self):
        """
        If the extracted dict does not contain the 'intents' key, the fallback
        must be ["not_recognized"] without raising.
        """
        graph = self._make_graph()
        graph._extract_structured_output = MagicMock(
            return_value='{"action": "add_item", "add_item": "leite,1"}'
        )

        result = graph._classify_intent(self._make_invoke_data("adiciona leite"))

        assert result["intent"] == ["not_recognized"], (
            f"Expected ['not_recognized'] when 'intents' key absent, got {result['intent']!r}"
        )

    def test_classify_intent__empty_string_output__returns_not_recognized_no_raise(self):
        """
        Empty string from the LLM must not raise any exception and must produce
        intent=["not_recognized"].
        """
        graph = self._make_graph()
        # Simulate the LLM returning an empty string through the full pipeline
        response = MagicMock()
        response.content = ""
        graph.llm_chat.return_value = response

        result = graph._classify_intent(self._make_invoke_data("???"))

        assert result["intent"] == ["not_recognized"], (
            f"Expected ['not_recognized'] for empty LLM output, got {result['intent']!r}"
        )

    def test_classify_intent__prose_with_dict_via_extract__populates_output_fields(self):
        """
        When _extract_structured_output successfully pulls a full dict from prose,
        the output_* fields in the result must be populated from that dict.
        """
        graph = self._make_graph()
        graph._extract_structured_output = MagicMock(
            return_value=(
                '{"intents": ["add_item"], "add_item": "leite,2|ovos,12",'
                ' "edit_item": "", "delete_item": "", "check_item": "", "uncheck_item": ""}'
            )
        )

        result = graph._classify_intent(self._make_invoke_data("adiciona leite e ovos"))

        assert result.get("output_add_item") == "leite,2|ovos,12", (
            f"Expected output_add_item populated from extracted dict, got {result!r}"
        )
