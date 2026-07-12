from datetime import datetime
from typing import Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from application.appservices.prompt_sanitizer import sanitize_for_prompt
from application.graphs.graph import Graph
from domain.entities import GraphInvokeRequest

NO_PREVIOUS_SUMMARY_TEXT = "nenhum resumo anterior"

_SPEAKER_LABELS = {"human": "Usuário", "ai": "Assistente"}
_DEFAULT_SPEAKER_LABEL = "Usuário"
_SUMMARY_HEADER_PREFIX = "###"

# Per-message cap on the summarizer's INPUT. Nothing bounds an incoming chat
# message, and Ollama serialises requests: a few megabyte-sized turns in the
# prefix would make this background prompt arbitrarily large and hold the GPU,
# showing up as latency on the NEXT user request. With the shipped thresholds a
# typical prefix is ~14 messages -> ~28k chars, which fits num_ctx with room to
# generate.
_DEFAULT_MAX_MESSAGE_CHARS = 2000


class ContextSummaryGraph(Graph):
    """
    Chat context compaction graph (single-step chain: prompt | llm).

    Summarizes the old part of a conversation — the previous summary plus the
    turns about to be dropped from the history — into a single dense summary
    that replaces both. It is the only owner of the summary validation: an
    output that is empty, not written in the fixed "###" skeleton, or too long
    to keep a whole bullet under the cap is discarded (`summary=None`).
    """

    def __init__(
        self,
        llm_chat: BaseChatModel,
        provider: str = "OLLAMA",
        max_summary_chars: int = 2500,
        max_message_chars: int = _DEFAULT_MAX_MESSAGE_CHARS,
    ):
        super().__init__(provider)
        self.llm_chat = llm_chat
        self.max_summary_chars = max_summary_chars
        self.max_message_chars = max_message_chars

    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        context_hints = invoke_request.context_hints or {}

        prompt = ChatPromptTemplate.from_template(
            self.load_prompt("context_summary_graph.md")
        )
        chain = prompt | self.llm_chat

        response = chain.invoke(
            {
                "current_datetime": datetime.now()
                .astimezone()
                .strftime("%d/%m/%Y %H:%M"),
                "previous_summary": self._format_previous_summary(
                    context_hints.get("previous_summary")
                ),
                "old_messages": self._format_old_messages(
                    context_hints.get("old_messages")
                ),
            }
        )

        return {"summary": self._validate_summary(response.content)}

    # ===============================================
    # Private Methods
    # ===============================================

    def _format_previous_summary(self, previous_summary) -> str:
        if not previous_summary or not str(previous_summary).strip():
            return NO_PREVIOUS_SUMMARY_TEXT
        return str(previous_summary).strip()

    def _format_old_messages(self, old_messages) -> str:
        lines = []
        for message in old_messages or []:
            label = _SPEAKER_LABELS.get(
                str(message.get("type", "")).lower(), _DEFAULT_SPEAKER_LABEL
            )
            # Collapsing newlines is CORRECT here (unlike the summary
            # reinjection): each message renders as ONE "Usuário: ..." line, so a
            # multi-line message could otherwise forge extra "Assistente: ..."
            # lines and rewrite the transcript the summarizer reads.
            content = sanitize_for_prompt(
                message.get("content"), max_chars=self.max_message_chars
            )
            if content:
                lines.append(f"{label}: {content}")
        return "\n".join(lines)

    def _validate_summary(self, raw) -> Optional[str]:
        raw_str = raw if isinstance(raw, str) else ""
        cleaned = self._remove_thinking_tag(raw_str).strip()

        if not cleaned:
            return None
        if not cleaned.startswith(_SUMMARY_HEADER_PREFIX):
            return None
        if len(cleaned) <= self.max_summary_chars:
            return cleaned

        return self._truncate_to_whole_lines(cleaned)

    def _truncate_to_whole_lines(self, summary: str) -> Optional[str]:
        """
        Cut the summary on a whole-line boundary so a bullet is never sliced
        mid-sentence: a truncated fact would be reinjected into every future
        turn as a broken, misleading one. A result that keeps only the header
        carries no information and is discarded.
        """
        kept_lines: list[str] = []
        length = 0
        for line in summary.splitlines():
            candidate_length = length + len(line) + (1 if kept_lines else 0)
            if candidate_length > self.max_summary_chars:
                break
            kept_lines.append(line)
            length = candidate_length

        if len(kept_lines) < 2:
            return None
        return "\n".join(kept_lines)
