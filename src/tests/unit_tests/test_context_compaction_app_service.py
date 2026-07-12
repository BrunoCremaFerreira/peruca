"""
ContextCompactionAppService Unit Tests (Phase D / F4).

ContextCompactionAppService.compact_if_needed(external_user_id) is SYNCHRONOUS
(it has no notion of background tasks) and its entire body is wrapped in
try/except so failures NEVER propagate — it runs as a FastAPI BackgroundTask
after the response was already sent. It ALWAYS returns None.

Constructor contract (mirrors MemoryAppService; thresholds are injected, the
service NEVER instantiates Settings itself):

    ContextCompactionAppService(
        context_summary_graph,
        user_repository,
        store,                          # ConversationContextStore
        enabled: bool = True,
        trigger_messages: int = 30,
        trigger_chars: int = 24_000,
        keep_tail_messages: int = 16,
    )

Flow under test (plan §3.4 / §6):
  1. early-exit: disabled / unknown user / history under BOTH triggers.
  2. prefix P = messages[0 : len - keep_tail_messages], pulled BACK to a turn
     boundary (the tail must start on a "human" message). The adjustment only
     ever shrinks the prefix — compact less, never more.
  3. snapshot len(P) + conversation_digest(P) BEFORE the (slow) LLM call.
  4. graph gets context_hints={"previous_summary": str, "old_messages": P}.
  5. summary None -> nothing is truncated.
  6. summary -> store.apply_compaction(user.id, count, digest, summary); a False
     return (logical CAS lost) is discarded silently, with NO retry.
"""

import uuid
from unittest.mock import MagicMock, patch

from application.appservices.context_compaction_app_service import (
    ContextCompactionAppService,
)
from domain.entities import GraphInvokeRequest, User
from domain.services.conversation_digest import conversation_digest


# ===========================================================================
# Helpers
# ===========================================================================


def _sample_user() -> User:
    return User(id=str(uuid.uuid4()), external_id="ext-1", name="Alice", summary="")


def _history_dicts(n_turns: int) -> list[dict]:
    """
    A well-formed history: n_turns human/ai pairs, so 2 * n_turns messages,
    always starting on a "human" message.
    """
    messages: list[dict] = []
    for index in range(n_turns):
        messages.append({"type": "human", "content": f"pergunta {index}"})
        messages.append({"type": "ai", "content": f"resposta {index}"})
    return messages


def _make_service(
    history=None,
    user=None,
    previous_summary_record=None,
    graph_summary="### Assuntos em andamento\n- Alice vai viajar",
    apply_result=True,
    enabled=True,
    trigger_messages=30,
    trigger_chars=24_000,
    keep_tail_messages=16,
    graph_raises=False,
    store_raises_on=None,
    user_repository_raises=False,
):
    user = user if user is not None else _sample_user()

    store = MagicMock()
    store.read_history.return_value = history if history is not None else []
    store.get_summary.return_value = previous_summary_record
    store.apply_compaction.return_value = apply_result
    if store_raises_on:
        getattr(store, store_raises_on).side_effect = RuntimeError("store boom")

    user_repository = MagicMock()
    if user_repository_raises:
        user_repository.get_by_external_id.side_effect = RuntimeError("db boom")
    else:
        user_repository.get_by_external_id.return_value = user

    graph = MagicMock()
    if graph_raises:
        graph.invoke.side_effect = RuntimeError("llm boom")
    else:
        graph.invoke.return_value = {"summary": graph_summary}

    service = ContextCompactionAppService(
        graph,
        user_repository,
        store,
        enabled=enabled,
        trigger_messages=trigger_messages,
        trigger_chars=trigger_chars,
        keep_tail_messages=keep_tail_messages,
    )
    return service, graph, user_repository, store, user


def _invoked_request(graph) -> GraphInvokeRequest:
    return graph.invoke.call_args.args[0]


def _sent_prefix(graph) -> list[dict]:
    return _invoked_request(graph).context_hints["old_messages"]


# ===========================================================================
# TestContextCompactionAppServiceEarlyExit
# ===========================================================================


class TestContextCompactionAppServiceEarlyExit:
    def test_compact_if_needed__disabled__does_nothing(self):
        service, graph, user_repository, store, _ = _make_service(
            history=_history_dicts(20), enabled=False
        )

        service.compact_if_needed("ext-1")

        user_repository.get_by_external_id.assert_not_called()
        store.read_history.assert_not_called()
        graph.invoke.assert_not_called()
        store.apply_compaction.assert_not_called()

    def test_compact_if_needed__unknown_user__does_not_read_history(self):
        service, graph, user_repository, store, _ = _make_service(
            history=_history_dicts(20), user=None
        )
        user_repository.get_by_external_id.return_value = None

        service.compact_if_needed("ghost")

        user_repository.get_by_external_id.assert_called_once_with(
            external_id="ghost"
        )
        store.read_history.assert_not_called()
        graph.invoke.assert_not_called()
        store.apply_compaction.assert_not_called()

    def test_compact_if_needed__empty_history__does_not_call_graph(self):
        service, graph, _, store, _ = _make_service(history=[])

        service.compact_if_needed("ext-1")

        graph.invoke.assert_not_called()
        store.apply_compaction.assert_not_called()

    def test_compact_if_needed__below_both_triggers__does_not_call_graph(self):
        # 20 messages < trigger_messages(30); their contents are far below
        # trigger_chars(24_000).
        service, graph, _, store, _ = _make_service(
            history=_history_dicts(10), trigger_messages=30, trigger_chars=24_000
        )

        service.compact_if_needed("ext-1")

        graph.invoke.assert_not_called()
        store.apply_compaction.assert_not_called()

    def test_compact_if_needed__one_message_short_of_trigger__does_not_compact(self):
        history = _history_dicts(10)[:-1]  # 19 messages

        service, graph, _, _, _ = _make_service(
            history=history, trigger_messages=20, keep_tail_messages=4
        )

        service.compact_if_needed("ext-1")

        graph.invoke.assert_not_called()

    def test_compact_if_needed__message_count_equals_trigger__compacts(self):
        # The trigger is ">=", not ">".
        history = _history_dicts(10)  # 20 messages

        service, graph, _, store, _ = _make_service(
            history=history, trigger_messages=20, keep_tail_messages=4
        )

        service.compact_if_needed("ext-1")

        graph.invoke.assert_called_once()
        store.apply_compaction.assert_called_once()

    def test_compact_if_needed__char_trigger_alone__compacts_with_few_messages(self):
        # Few messages, but their contents alone blow past trigger_chars.
        history = [
            {"type": "human", "content": "a" * 300},
            {"type": "ai", "content": "b" * 300},
            {"type": "human", "content": "c" * 10},
            {"type": "ai", "content": "d" * 10},
        ]

        service, graph, _, store, _ = _make_service(
            history=history,
            trigger_messages=30,  # not reached
            trigger_chars=500,  # reached (620 chars)
            keep_tail_messages=2,
        )

        service.compact_if_needed("ext-1")

        graph.invoke.assert_called_once()
        store.apply_compaction.assert_called_once()

    def test_compact_if_needed__chars_below_trigger__does_not_compact(self):
        history = [
            {"type": "human", "content": "a" * 100},
            {"type": "ai", "content": "b" * 100},
            {"type": "human", "content": "c" * 100},
            {"type": "ai", "content": "d" * 100},
        ]

        service, graph, _, _, _ = _make_service(
            history=history,
            trigger_messages=30,
            trigger_chars=1_000,  # 400 chars is below it
            keep_tail_messages=2,
        )

        service.compact_if_needed("ext-1")

        graph.invoke.assert_not_called()

    def test_compact_if_needed__history_shorter_than_tail__does_not_compact(self):
        # Trigger fires on count, but there is nothing older than the tail.
        history = _history_dicts(2)  # 4 messages

        service, graph, _, store, _ = _make_service(
            history=history, trigger_messages=2, keep_tail_messages=16
        )

        service.compact_if_needed("ext-1")

        graph.invoke.assert_not_called()
        store.apply_compaction.assert_not_called()

    def test_compact_if_needed__history_equals_tail__does_not_compact(self):
        # len(history) == keep_tail_messages -> the prefix is empty.
        history = _history_dicts(3)  # 6 messages

        service, graph, _, store, _ = _make_service(
            history=history, trigger_messages=6, keep_tail_messages=6
        )

        service.compact_if_needed("ext-1")

        graph.invoke.assert_not_called()
        store.apply_compaction.assert_not_called()

    def test_compact_if_needed__reads_history_only_once(self):
        service, _, _, store, _ = _make_service(
            history=_history_dicts(10), trigger_messages=20, keep_tail_messages=4
        )

        service.compact_if_needed("ext-1")

        store.read_history.assert_called_once()


# ===========================================================================
# TestContextCompactionAppServiceTurnBoundary
# ===========================================================================


class TestContextCompactionAppServiceTurnBoundary:
    def test_compact_if_needed__cut_lands_on_ai__moves_cut_backwards(self):
        # 6 messages: h0 a0 h1 a1 h2 a2. keep_tail=3 -> raw cut = index 3 ("ai"),
        # which would split the h1/a1 pair. The cut moves BACK to index 2 (the
        # "human" that opens that turn): the prefix shrinks, the tail grows.
        history = _history_dicts(3)

        service, graph, _, store, user = _make_service(
            history=history, trigger_messages=6, keep_tail_messages=3
        )

        service.compact_if_needed("ext-1")

        sent = _sent_prefix(graph)
        assert sent == history[:2]
        assert len(sent) == 2  # never the naive 3
        store.apply_compaction.assert_called_once_with(
            user.id,
            2,
            conversation_digest(history[:2]),
            "### Assuntos em andamento\n- Alice vai viajar",
        )

    def test_compact_if_needed__cut_already_on_human__prefix_unchanged(self):
        # 6 messages, keep_tail=2 -> raw cut = index 4, already a "human".
        history = _history_dicts(3)

        service, graph, _, _, _ = _make_service(
            history=history, trigger_messages=6, keep_tail_messages=2
        )

        service.compact_if_needed("ext-1")

        assert _sent_prefix(graph) == history[:4]

    def test_compact_if_needed__tail_starts_on_human_after_adjustment(self):
        history = _history_dicts(5)  # 10 messages

        service, graph, _, _, _ = _make_service(
            history=history, trigger_messages=10, keep_tail_messages=5
        )

        service.compact_if_needed("ext-1")

        prefix = _sent_prefix(graph)
        tail = history[len(prefix) :]
        assert tail[0]["type"] == "human"
        assert len(prefix) <= 10 - 5  # the adjustment never compacts MORE

    def test_compact_if_needed__no_human_message_at_all__does_not_compact(self):
        # Degenerate history: there is no "human" to anchor the tail on.
        history = [{"type": "ai", "content": f"resposta {i}"} for i in range(8)]

        service, graph, _, store, _ = _make_service(
            history=history, trigger_messages=8, keep_tail_messages=3
        )

        service.compact_if_needed("ext-1")

        graph.invoke.assert_not_called()
        store.apply_compaction.assert_not_called()

    def test_compact_if_needed__only_human_is_first_message__does_not_compact(self):
        # The cut walks back to index 0 -> the prefix would be empty.
        history = [{"type": "human", "content": "oi"}] + [
            {"type": "ai", "content": f"resposta {i}"} for i in range(7)
        ]

        service, graph, _, store, _ = _make_service(
            history=history, trigger_messages=8, keep_tail_messages=3
        )

        service.compact_if_needed("ext-1")

        graph.invoke.assert_not_called()
        store.apply_compaction.assert_not_called()

    def test_compact_if_needed__consecutive_human_messages__cuts_on_nearest(self):
        # h h a h a a h a : keep_tail=3 -> raw cut = 5 ("ai") -> back to 3.
        history = [
            {"type": "human", "content": "m0"},
            {"type": "human", "content": "m1"},
            {"type": "ai", "content": "m2"},
            {"type": "human", "content": "m3"},
            {"type": "ai", "content": "m4"},
            {"type": "ai", "content": "m5"},
            {"type": "human", "content": "m6"},
            {"type": "ai", "content": "m7"},
        ]

        service, graph, _, _, _ = _make_service(
            history=history, trigger_messages=8, keep_tail_messages=3
        )

        service.compact_if_needed("ext-1")

        assert _sent_prefix(graph) == history[:3]


# ===========================================================================
# TestContextCompactionAppServiceGraphCall
# ===========================================================================


class TestContextCompactionAppServiceGraphCall:
    def test_compact_if_needed__passes_user_and_prefix_to_graph(self):
        history = _history_dicts(10)  # 20 messages

        service, graph, _, _, user = _make_service(
            history=history, trigger_messages=20, keep_tail_messages=4
        )

        service.compact_if_needed("ext-1")

        request = _invoked_request(graph)
        assert isinstance(request, GraphInvokeRequest)
        assert request.user is user
        assert isinstance(request.message, str)
        assert request.context_hints["old_messages"] == history[:16]

    def test_compact_if_needed__no_previous_summary__passes_empty_string(self):
        service, graph, _, _, _ = _make_service(
            history=_history_dicts(10),
            trigger_messages=20,
            keep_tail_messages=4,
            previous_summary_record=None,
        )

        service.compact_if_needed("ext-1")

        assert _invoked_request(graph).context_hints["previous_summary"] == ""

    def test_compact_if_needed__previous_summary__is_forwarded_to_graph(self):
        service, graph, _, store, user = _make_service(
            history=_history_dicts(10),
            trigger_messages=20,
            keep_tail_messages=4,
            previous_summary_record={
                "summary": "### Assuntos em andamento\n- viagem a Lisboa",
                "covers": 12,
                "updated_at": "2026-07-12T10:00:00",
            },
        )

        service.compact_if_needed("ext-1")

        store.get_summary.assert_called_once_with(user.id)
        assert (
            _invoked_request(graph).context_hints["previous_summary"]
            == "### Assuntos em andamento\n- viagem a Lisboa"
        )

    def test_compact_if_needed__digest_matches_the_prefix_sent_to_the_graph(self):
        # The CAS digest must fingerprint EXACTLY the messages the summary was
        # built from; otherwise the store would swap away turns the summary
        # never saw.
        history = _history_dicts(10)

        service, graph, _, store, user = _make_service(
            history=history, trigger_messages=20, keep_tail_messages=5
        )

        service.compact_if_needed("ext-1")

        sent_prefix = _sent_prefix(graph)
        user_id, count, digest, summary = store.apply_compaction.call_args.args
        assert user_id == user.id
        assert count == len(sent_prefix)
        assert digest == conversation_digest(sent_prefix)
        assert summary == "### Assuntos em andamento\n- Alice vai viajar"

    def test_compact_if_needed__snapshot_taken_before_the_llm_call(self):
        # The store must not be re-read after the graph returns: the count and
        # digest handed to the CAS are the ones snapshotted beforehand.
        history = _history_dicts(10)
        service, graph, _, store, _ = _make_service(
            history=history, trigger_messages=20, keep_tail_messages=4
        )

        def _mutate_history_during_llm_call(_request):
            store.read_history.return_value = _history_dicts(30)
            return {"summary": "### Assuntos em andamento\n- Alice vai viajar"}

        graph.invoke.side_effect = _mutate_history_during_llm_call

        service.compact_if_needed("ext-1")

        _, count, digest, _ = store.apply_compaction.call_args.args
        assert count == 16
        assert digest == conversation_digest(history[:16])


# ===========================================================================
# TestContextCompactionAppServiceApplyCompaction
# ===========================================================================


class TestContextCompactionAppServiceApplyCompaction:
    def test_compact_if_needed__summary_none__does_not_apply_compaction(self):
        # The graph is the sole owner of summary validation: a rejected summary
        # comes back as None and NOTHING may be truncated.
        service, graph, _, store, _ = _make_service(
            history=_history_dicts(10),
            trigger_messages=20,
            keep_tail_messages=4,
            graph_summary=None,
        )

        service.compact_if_needed("ext-1")

        graph.invoke.assert_called_once()
        store.apply_compaction.assert_not_called()

    def test_compact_if_needed__summary_key_missing__does_not_apply_compaction(self):
        service, graph, _, store, _ = _make_service(
            history=_history_dicts(10), trigger_messages=20, keep_tail_messages=4
        )
        graph.invoke.return_value = {}

        service.compact_if_needed("ext-1")

        store.apply_compaction.assert_not_called()

    def test_compact_if_needed__blank_summary__does_not_apply_compaction(self):
        service, graph, _, store, _ = _make_service(
            history=_history_dicts(10),
            trigger_messages=20,
            keep_tail_messages=4,
            graph_summary="",
        )

        service.compact_if_needed("ext-1")

        store.apply_compaction.assert_not_called()

    def test_compact_if_needed__cas_lost__does_not_retry(self):
        # apply_compaction False = a reset or a concurrent compaction won the
        # race. Discard silently; the next trigger will redo the work.
        service, graph, _, store, _ = _make_service(
            history=_history_dicts(10),
            trigger_messages=20,
            keep_tail_messages=4,
            apply_result=False,
        )

        service.compact_if_needed("ext-1")

        assert store.apply_compaction.call_count == 1
        assert graph.invoke.call_count == 1

    def test_compact_if_needed__cas_applied__calls_store_once(self):
        service, _, _, store, _ = _make_service(
            history=_history_dicts(10),
            trigger_messages=20,
            keep_tail_messages=4,
            apply_result=True,
        )

        service.compact_if_needed("ext-1")

        assert store.apply_compaction.call_count == 1


# ===========================================================================
# TestContextCompactionAppServiceSwallowsExceptions
# ===========================================================================


class TestContextCompactionAppServiceSwallowsExceptions:
    def test_compact_if_needed__user_repository_raises__is_swallowed(self):
        service, graph, _, store, _ = _make_service(
            history=_history_dicts(10),
            trigger_messages=20,
            keep_tail_messages=4,
            user_repository_raises=True,
        )

        assert service.compact_if_needed("ext-1") is None
        graph.invoke.assert_not_called()
        store.apply_compaction.assert_not_called()

    def test_compact_if_needed__read_history_raises__is_swallowed(self):
        service, graph, _, store, _ = _make_service(
            history=_history_dicts(10),
            trigger_messages=20,
            keep_tail_messages=4,
            store_raises_on="read_history",
        )

        assert service.compact_if_needed("ext-1") is None
        graph.invoke.assert_not_called()
        store.apply_compaction.assert_not_called()

    def test_compact_if_needed__get_summary_raises__is_swallowed(self):
        service, graph, _, store, _ = _make_service(
            history=_history_dicts(10),
            trigger_messages=20,
            keep_tail_messages=4,
            store_raises_on="get_summary",
        )

        assert service.compact_if_needed("ext-1") is None
        store.apply_compaction.assert_not_called()

    def test_compact_if_needed__graph_raises__is_swallowed(self):
        # ContextSummaryGraph propagates LLM errors on purpose; the app service
        # is the layer that absorbs them.
        service, graph, _, store, _ = _make_service(
            history=_history_dicts(10),
            trigger_messages=20,
            keep_tail_messages=4,
            graph_raises=True,
        )

        assert service.compact_if_needed("ext-1") is None
        graph.invoke.assert_called_once()
        store.apply_compaction.assert_not_called()

    def test_compact_if_needed__apply_compaction_raises__is_swallowed(self):
        service, _, _, store, _ = _make_service(
            history=_history_dicts(10),
            trigger_messages=20,
            keep_tail_messages=4,
            store_raises_on="apply_compaction",
        )

        assert service.compact_if_needed("ext-1") is None
        store.apply_compaction.assert_called_once()

    def test_compact_if_needed__failure__is_logged(self):
        service, _, _, _, _ = _make_service(
            history=_history_dicts(10),
            trigger_messages=20,
            keep_tail_messages=4,
            graph_raises=True,
        )

        with patch(
            "application.appservices.context_compaction_app_service.logger"
        ) as logger:
            service.compact_if_needed("ext-1")

        logger.error.assert_called_once()


# ===========================================================================
# TestContextCompactionAppServiceReturnValue
# ===========================================================================


class TestContextCompactionAppServiceReturnValue:
    def test_compact_if_needed__disabled__returns_none(self):
        service, _, _, _, _ = _make_service(history=_history_dicts(20), enabled=False)

        assert service.compact_if_needed("ext-1") is None

    def test_compact_if_needed__below_trigger__returns_none(self):
        service, _, _, _, _ = _make_service(history=_history_dicts(2))

        assert service.compact_if_needed("ext-1") is None

    def test_compact_if_needed__compaction_applied__returns_none(self):
        service, _, _, _, _ = _make_service(
            history=_history_dicts(10), trigger_messages=20, keep_tail_messages=4
        )

        assert service.compact_if_needed("ext-1") is None

    def test_compact_if_needed__cas_lost__returns_none(self):
        service, _, _, _, _ = _make_service(
            history=_history_dicts(10),
            trigger_messages=20,
            keep_tail_messages=4,
            apply_result=False,
        )

        assert service.compact_if_needed("ext-1") is None
