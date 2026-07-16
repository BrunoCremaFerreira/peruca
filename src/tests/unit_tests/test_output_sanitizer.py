"""
application/appservices/output_sanitizer.py Unit Tests (TDD RED).

F1 (cameras review plan §3.2): a camera snapshot data URI must never be
persisted into the conversation history nor fed to the MemoryGraph. The pure
helper ``replace_image_data_uris(text, placeholder="[snapshot da câmera
exibido]")`` replaces WHOLE LINES that start with the image data URI prefix
("data:image/") with the placeholder, leaving every other line intact.

Line-prefix semantics (mirrors the merge bypass): a sentence merely
mentioning 'data:image/' mid-string is NOT a URI line and must survive
untouched.

RED: the module application/appservices/output_sanitizer.py does not exist
yet — this file fails at collection until it is implemented.
"""

import base64

from application.appservices.output_sanitizer import replace_image_data_uris


_DEFAULT_PLACEHOLDER = "[snapshot da câmera exibido]"


def _png_data_uri(payload: bytes = b"\x89PNG\r\n\x1a\nfake_png") -> str:
    encoded = base64.b64encode(payload).decode()
    return f"data:image/png;base64,{encoded}"


class TestReplaceImageDataUris:
    def test_replace_image_data_uris__single_uri_line__replaced_with_placeholder(self):
        """A text that is a single data URI line becomes exactly the placeholder."""
        uri = _png_data_uri()

        result = replace_image_data_uris(uri)

        assert result == _DEFAULT_PLACEHOLDER, (
            f"Expected the URI line replaced by the default placeholder, "
            f"got: {result[:80]!r}"
        )
        assert "data:image/" not in result

    def test_replace_image_data_uris__mixed_uri_and_status_lines__only_uri_line_replaced(
        self,
    ):
        """
        In a mixed output (URI line + status line + merged text), ONLY the URI
        line is replaced; the other lines survive byte-identical.
        """
        uri = _png_data_uri()
        text = f"{uri}\nCamera Sala: gravando\n\nLiguei a luz da sala."

        result = replace_image_data_uris(text)

        assert "data:image/" not in result, (
            f"URI survived sanitization: {result[:120]!r}"
        )
        assert _DEFAULT_PLACEHOLDER in result.splitlines(), (
            f"Expected the placeholder as a full line, got: {result!r}"
        )
        assert "Camera Sala: gravando" in result.splitlines(), (
            f"Status line must survive intact, got: {result!r}"
        )
        assert "Liguei a luz da sala." in result.splitlines(), (
            f"Conversational line must survive intact, got: {result!r}"
        )

    def test_replace_image_data_uris__text_without_uri__returned_unchanged(self):
        """A text with no data URI line must be returned exactly as given."""
        text = "Camera Sala: em espera\n\nLiguei a luz da sala."

        result = replace_image_data_uris(text)

        assert result == text, (
            f"Text without any URI must be unchanged, got: {result!r}"
        )

    def test_replace_image_data_uris__multiple_uri_lines__all_replaced(self):
        """Every URI line (multi-camera output) must be replaced."""
        uri_sala = _png_data_uri(b"sala_bytes")
        uri_garagem = "data:image/jpeg;base64," + base64.b64encode(
            b"garagem_bytes"
        ).decode()
        text = f"{uri_sala}\n{uri_garagem}\nCamera Sala: gravando"

        result = replace_image_data_uris(text)

        assert "data:image/" not in result, (
            f"At least one URI survived sanitization: {result[:120]!r}"
        )
        placeholder_lines = [
            line for line in result.splitlines() if line == _DEFAULT_PLACEHOLDER
        ]
        assert len(placeholder_lines) == 2, (
            f"Expected one placeholder per URI line (2), got "
            f"{len(placeholder_lines)}: {result!r}"
        )
        assert "Camera Sala: gravando" in result.splitlines()

    def test_replace_image_data_uris__data_image_mid_sentence__returned_unchanged(self):
        """
        Line-prefix semantics: 'data:image/' in the middle of a sentence is
        not a URI line and the text must be returned unchanged.
        """
        text = "O snapshot vem no formato data:image/png em base64, tudo certo."

        result = replace_image_data_uris(text)

        assert result == text, (
            f"A mid-sentence 'data:image/' mention must not be replaced, "
            f"got: {result!r}"
        )
