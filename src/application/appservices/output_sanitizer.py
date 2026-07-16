"""
Output sanitizer (F1, cameras review plan §3.2).

A camera snapshot data URI is the HTTP deliverable, but it must never be
persisted into the conversation history nor fed to the MemoryGraph LLM —
a multi-MB base64 line would explode the context window on the next turn.
"""

from application.graphs.markers import IMAGE_DATA_URI_PREFIX


DEFAULT_IMAGE_PLACEHOLDER = "[snapshot da câmera exibido]"


def replace_image_data_uris(
    text: str, placeholder: str = DEFAULT_IMAGE_PLACEHOLDER
) -> str:
    """
    Replace every WHOLE LINE starting with the image data URI prefix by the
    placeholder. Detection is by line prefix, never substring — a sentence
    merely mentioning "data:image/" mid-string survives untouched.
    """
    if not text or IMAGE_DATA_URI_PREFIX not in text:
        return text
    return "\n".join(
        placeholder if line.startswith(IMAGE_DATA_URI_PREFIX) else line
        for line in text.splitlines()
    )
