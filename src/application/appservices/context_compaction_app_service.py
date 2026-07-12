import logging

from application.graphs.context_summary_graph import ContextSummaryGraph
from domain.entities import GraphInvokeRequest
from domain.interfaces.data_repository import ConversationContextStore, UserRepository
from domain.services.conversation_digest import conversation_digest


logger = logging.getLogger(__name__)


class ContextCompactionAppService:
    """
    Chat context compaction Application Service (background summarization).

    Synchronous, with no notion of background tasks. The entire body of
    compact_if_needed is wrapped in try/except so failures never propagate to
    the caller (it runs in a background threadpool, after the response was
    already sent) and it always returns None.

    Compaction is opportunistic: any failure — an unreachable store, a rejected
    summary, a lost CAS — leaves the conversation exactly as it was ("not
    compacted yet"), never with turns lost.
    """

    def __init__(
        self,
        context_summary_graph: ContextSummaryGraph,
        user_repository: UserRepository,
        store: ConversationContextStore,
        enabled: bool = True,
        trigger_messages: int = 30,
        trigger_chars: int = 24_000,
        keep_tail_messages: int = 16,
    ) -> None:
        self.context_summary_graph = context_summary_graph
        self.user_repository = user_repository
        self.store = store
        self.enabled = enabled
        self.trigger_messages = trigger_messages
        self.trigger_chars = trigger_chars
        self.keep_tail_messages = keep_tail_messages

    def compact_if_needed(self, external_user_id: str) -> None:
        try:
            if not self.enabled:
                return

            user = self.user_repository.get_by_external_id(external_id=external_user_id)
            if not user:
                return

            history = self.store.read_history(user.id)
            if not history or not self._should_compact(history):
                return

            cut = self._turn_boundary_cut(history)
            if cut <= 0:
                return

            prefix = history[:cut]
            expected_count = len(prefix)
            expected_digest = conversation_digest(prefix)

            record = self.store.get_summary(user.id)
            previous_summary = record["summary"] if record else ""

            request = GraphInvokeRequest(
                message="",
                user=user,
                context_hints={
                    "previous_summary": previous_summary,
                    "old_messages": prefix,
                },
            )

            result = self.context_summary_graph.invoke(request)
            summary = result.get("summary")
            if not summary:
                return

            self.store.apply_compaction(
                user.id, expected_count, expected_digest, summary
            )
        except Exception as e:
            logger.error("compact_if_needed failed: %s", e, exc_info=True)

    def _should_compact(self, history: list[dict]) -> bool:
        if len(history) >= self.trigger_messages:
            return True

        total_chars = sum(len(message.get("content", "")) for message in history)
        return total_chars >= self.trigger_chars

    def _turn_boundary_cut(self, history: list[dict]) -> int:
        """
        Where the tail starts: the naive cut pulled BACK to the "human" message
        that opens a turn, so a human/ai pair is never split. It only ever
        shrinks the prefix — compact less, never more. A degenerate history with
        no "human" to anchor the tail on walks down to 0, meaning "do not
        compact".
        """
        cut = len(history) - self.keep_tail_messages
        while cut > 0 and history[cut].get("type") != "human":
            cut -= 1
        return cut
