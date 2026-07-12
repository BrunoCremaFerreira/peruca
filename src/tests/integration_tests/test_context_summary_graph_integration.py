"""
ContextSummaryGraph Integration Tests (Fase F) — real Ollama round-trip.

Exercises the graph the unit tests can only fake: the real prompt
(`infra/prompts/context_summary_graph.md`), the real model, and the real
post-processing/validation pipeline.

Assertions are deliberately TOLERANT (plan §7): the summary's *structure* plus
one or two substrings of hard facts. We never assert on phrasing, bullet count,
or the language of the body — a 12b model rewords freely and such asserts would
be flaky without testing anything the system depends on.

The two things the rest of the system genuinely relies on ARE asserted:
  - the "###" skeleton (OnlyTalkGraph only ever sees a summary that passed the
    graph's own validation, which rejects anything not starting with "###");
  - the literal "Imagem #N" marker (it is what keeps the re-vision gate in
    OnlyTalkGraph alive across a compaction).

Requires a live Ollama at LLM_PROVIDER_URL.
"""

import uuid

import pytest

import infra.ioc as ioc
from domain.entities import GraphInvokeRequest, User
from infra.ioc import get_context_summary_graph


pytestmark = pytest.mark.integration


# The fixed headers the prompt mandates (empty sections are omitted, so we only
# require that AT LEAST ONE shows up).
FIXED_HEADERS = (
    "### Assuntos em andamento",
    "### Combinados e pendências",
    "### Contexto e preferências desta conversa",
    "### Imagens mencionadas",
)


def _turn(human: str, ai: str) -> list[dict]:
    return [{"type": "human", "content": human}, {"type": "ai", "content": ai}]


def _synthetic_history() -> list[dict]:
    """~20 messages (10 turns) of PT-BR chat carrying concrete, checkable facts."""
    history: list[dict] = []
    history += _turn(
        "Oi Peruca! Comprei um Fiat Argo prata no mês passado.",
        "Que legal, parabéns pelo carro novo!",
    )
    history += _turn(
        "Ele está com 15.000 km e a revisão está marcada para 2026-08-10.",
        "Anotado: revisão do Argo em 10 de agosto de 2026.",
    )
    history += _turn(
        "Preciso trocar o óleo antes da viagem para Campos do Jordão.",
        "Certo, a troca de óleo fica pendente antes da viagem.",
    )
    history += _turn(
        "A viagem é com a Marina e com o Rex, meu cachorro.",
        "Vocês vão de carro, então.",
    )
    history += _turn(
        "[Imagem #1: foto do painel do carro com a luz de óleo acesa] "
        "O que significa essa luz?",
        "Pela foto, é a luz de pressão do óleo. Verifique o nível antes de dirigir.",
    )
    history += _turn(
        "Consegui um orçamento de R$ 380 na oficina do Zé.",
        "É um preço razoável para óleo e filtro.",
    )
    history += _turn(
        "Também quero um pneu novo, mas ainda não decidi a marca.",
        "Podemos comparar as opções quando você quiser.",
    )
    history += _turn(
        "Me lembra de pagar o IPVA até 2026-07-20.",
        "Combinado, o IPVA vence em 20 de julho de 2026.",
    )
    history += _turn(
        "Prefiro que você me responda sempre de forma bem curta.",
        "Beleza, vou ser breve.",
    )
    history += _turn(
        "Qual era mesmo a data da revisão?",
        "10 de agosto de 2026.",
    )
    return history


def _sample_user() -> User:
    return User(id=str(uuid.uuid4()), external_id="1000", name="Bruno", summary="")


def _invoke(graph, old_messages: list[dict], previous_summary: str = "") -> str | None:
    request = GraphInvokeRequest(
        message="",
        user=_sample_user(),
        context_hints={
            "previous_summary": previous_summary,
            "old_messages": old_messages,
        },
    )
    return graph.invoke(request).get("summary")


@pytest.fixture
def context_summary_graph(integration_env):
    # The IoC cache may hold a graph built under a different environment; rebuild
    # it under the integration env (same pattern as `redis_backed_env`).
    ioc._repo_cache.clear()
    yield get_context_summary_graph()
    ioc._repo_cache.clear()


class TestContextSummaryGraphIntegration:
    def test_summarize__real_history__returns_structurally_valid_summary(
        self, context_summary_graph
    ):
        # Act
        summary = _invoke(context_summary_graph, _synthetic_history())

        # Assert — the graph accepted its own output (None means it discarded it).
        assert summary, "The graph discarded the summary (validation returned None)"
        assert summary.startswith("###"), (
            f"Summary must open with the fixed '###' skeleton, got: {summary[:80]!r}"
        )
        assert any(header in summary for header in FIXED_HEADERS), (
            f"Expected at least one of the fixed headers {FIXED_HEADERS}, got: {summary}"
        )
        assert len(summary) <= context_summary_graph.max_summary_chars, (
            f"Summary exceeds the cap of "
            f"{context_summary_graph.max_summary_chars} chars: {len(summary)}"
        )

    def test_summarize__history_with_image__preserves_image_marker(
        self, context_summary_graph
    ):
        # Act
        summary = _invoke(context_summary_graph, _synthetic_history())

        # Assert — the literal marker is the re-vision gate OnlyTalkGraph scans
        # for; losing it on compaction silently disables re-vision of the photo.
        assert summary, "The graph discarded the summary (validation returned None)"
        assert "Imagem #1" in summary, (
            f"Expected the literal 'Imagem #1' marker to survive, got: {summary}"
        )

    def test_summarize__real_history__keeps_at_least_one_hard_fact(
        self, context_summary_graph
    ):
        # Act
        summary = _invoke(context_summary_graph, _synthetic_history()).lower()

        # Assert — tolerant: the summary must carry SOMETHING concrete from the
        # conversation, not just headers. We accept any of the salient nouns
        # instead of pinning a phrasing.
        facts = ("argo", "óleo", "oleo", "ipva", "revisão", "revisao")
        assert any(fact in summary for fact in facts), (
            f"Expected at least one concrete fact from the conversation, got: {summary}"
        )


class TestContextSummaryGraphIncremental:
    def test_summarize__second_pass_with_previous_summary__stays_valid(
        self, context_summary_graph
    ):
        # Arrange — first pass produces the summary the second pass will merge.
        first_summary = _invoke(context_summary_graph, _synthetic_history())
        assert first_summary, "First pass produced no summary; cannot test the merge"

        new_messages = []
        new_messages += _turn(
            "Fiz a troca de óleo hoje, já está resolvido.",
            "Ótimo, então a pendência do óleo está encerrada.",
        )
        new_messages += _turn(
            "Escolhi o pneu Michelin para o Argo.",
            "Boa escolha, anotado.",
        )

        # Act — incremental pass: previous summary + the newly dropped turns.
        second_summary = _invoke(
            context_summary_graph, new_messages, previous_summary=first_summary
        )

        # Assert — structural validity only. The merge policy (what survives, what
        # is dropped as resolved) is a model judgement; asserting on it would be
        # asserting on phrasing.
        assert second_summary, "The graph discarded the incremental summary"
        assert second_summary.startswith("###"), (
            f"Incremental summary must open with '###', got: {second_summary[:80]!r}"
        )
        assert any(header in second_summary for header in FIXED_HEADERS), (
            f"Expected a fixed header in the incremental summary, got: {second_summary}"
        )
        assert len(second_summary) <= context_summary_graph.max_summary_chars
