"""
Sanitize attacker-controllable text before it is injected into an LLM prompt.

Any field a user (or an OCR'd image) controls and that is later re-injected into
a prompt — an image description, a maintenance record's free-text description, a
vehicle name — is collapsed to a single line and length-capped, so it cannot
forge extra history turns / record lines or smuggle instruction blocks.

The conversation summary is the one re-injected field that MUST keep its line
breaks (it is a multi-line "###" skeleton), so it gets its own sanitizer —
`sanitize_summary_for_prompt` — which neutralises the same attacks without
flattening the structure. The two live side by side on purpose: the trade-off
between them is the whole point.
"""

import re

_DEFAULT_MAX_CHARS = 500

_DEFAULT_SUMMARY_MAX_CHARS = 4_000

# "<<<DESC_IMAGEM>>>" would truncate the user-facing answer and "<<<REVER_IMAGEM: #N>>>"
# would force a vision pass — both are sentinels OnlyTalkGraph acts on.
_SENTINEL_RE = re.compile(r"<<<[^>]*>>>")


def sanitize_for_prompt(text, max_chars: int = _DEFAULT_MAX_CHARS) -> str:
    """
    Collapse all whitespace (including newlines) to single spaces and cap the
    length, appending an ellipsis when truncated. None/empty yields "".
    """
    if text is None:
        return ""
    collapsed = " ".join(str(text).split())
    if max_chars is not None and len(collapsed) > max_chars:
        collapsed = collapsed[:max_chars].rstrip() + "…"
    return collapsed


def sanitize_summary_for_prompt(
    summary, max_chars: int = _DEFAULT_SUMMARY_MAX_CHARS
) -> str:
    """
    Sanitize a conversation summary read back from the cache before it is
    re-injected into the prompt, PRESERVING its line breaks.

    The write path (`ContextSummaryGraph`) validates what the summarizer emits,
    but the cache itself is not a trust boundary — the project's Redis runs
    without authentication, so anything able to write `chat_summary:{user_id}`
    can put arbitrary text where the model will read it. This is the only control
    on the read path:

      - every "[" / "]" becomes "(" / ")", which kills forged
        "[Imagem #N ...]" / "[Resumo da conversa anterior: ...]" history lines and
        stops the summary from closing the template's own bracket early. The bare
        "Imagem #N" form survives ON PURPOSE: that is what the re-vision gate
        scans for;
      - "<<<...>>>" sentinels are dropped;
      - the length is capped on WHOLE LINES — a bullet sliced mid-sentence would
        be re-injected into every future turn as a misleading fact.

    Returns "" when nothing usable is left, which the caller reads as "no summary"
    (it degrades to the raw window, never to a failed turn).
    """
    if summary is None:
        return ""

    text = str(summary).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("[", "(").replace("]", ")")
    text = _SENTINEL_RE.sub("", text)

    lines = _normalize_lines(text.split("\n"))
    return "\n".join(_cap_whole_lines(lines, max_chars))


def _normalize_lines(lines: list[str]) -> list[str]:
    """Right-strip each line, drop the blank ones at both ends and collapse runs
    of blank lines into one (a wall of blank lines pushes the real turns out of
    the model's view)."""
    normalized: list[str] = []
    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            if not normalized or not normalized[-1]:
                continue
            normalized.append("")
        else:
            normalized.append(stripped)
    while normalized and not normalized[-1]:
        normalized.pop()
    return normalized


def _cap_whole_lines(lines: list[str], max_chars: int) -> list[str]:
    kept: list[str] = []
    length = 0
    for line in lines:
        candidate_length = length + len(line) + (1 if kept else 0)
        if candidate_length > max_chars:
            break
        kept.append(line)
        length = candidate_length
    while kept and not kept[-1]:
        kept.pop()
    return kept
