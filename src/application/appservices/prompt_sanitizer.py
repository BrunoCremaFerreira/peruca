"""
Sanitize attacker-controllable text before it is injected into an LLM prompt.

Any field a user (or an OCR'd image) controls and that is later re-injected into
a prompt — an image description, a maintenance record's free-text description, a
vehicle name — is collapsed to a single line and length-capped, so it cannot
forge extra history turns / record lines or smuggle instruction blocks.
"""

_DEFAULT_MAX_CHARS = 500


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
