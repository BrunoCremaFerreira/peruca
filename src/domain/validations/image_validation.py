import base64
import binascii
import re

from domain.validations.base_validation import BaseValidation


# data:<mime>;base64,<payload>
_DATA_URI_RE = re.compile(r"^data:(?P<mime>[\w.+-]+/[\w.+-]+);base64,(?P<data>.+)$")


class ImageValidator(BaseValidation):
    """
    Validates inbound chat images provided as full data URIs
    ("data:image/jpeg;base64,...").

    Follows the fluent BaseValidation pattern: granular methods accumulate
    errors and the terminal ``.validate()`` raises ``ValidationError`` if any
    were recorded. Limits are injected by the caller so the domain layer never
    imports ``infra.settings``.
    """

    def __init__(
        self,
        allowed_mimes: list[str],
        max_bytes: int,
        max_count: int,
    ):
        super().__init__()
        self.allowed_mimes = [m.lower() for m in (allowed_mimes or [])]
        self.max_bytes = max_bytes
        self.max_count = max_count

    # ===============================================
    # Granular validators
    # ===============================================

    def validate_count(self, images: list[str]):
        count = len(images or [])
        if count > self.max_count:
            self.errors.append(
                f"Too many images: {count} exceeds the maximum of {self.max_count}"
            )
        return self

    def validate_data_uri(self, image: str):
        match = self._match(image)
        if match is None:
            self.errors.append(
                "The image is not a valid 'data:<mime>;base64,<data>' URI"
            )
            return self
        payload = match.group("data")
        # DoS guard: never decode a payload whose estimated size already exceeds
        # the limit — decoding would allocate ~75% of the string in memory. The
        # size error itself is raised by validate_size; here we only refuse to
        # decode so an oversized payload can never be materialised.
        if self._estimated_decoded_size(payload) > self.max_bytes:
            return self
        try:
            base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError):
            self.errors.append("The image payload is not valid base64")
        return self

    def validate_mime(self, image: str):
        match = self._match(image)
        if match is None:
            self.errors.append(
                "The image is not a valid 'data:<mime>;base64,<data>' URI"
            )
            return self
        mime = match.group("mime").lower()
        if mime not in self.allowed_mimes:
            self.errors.append(
                f"Unsupported image mime type '{mime}'. "
                f"Allowed: {', '.join(self.allowed_mimes)}"
            )
        return self

    def validate_size(self, image: str):
        match = self._match(image)
        if match is None:
            self.errors.append(
                "The image is not a valid 'data:<mime>;base64,<data>' URI"
            )
            return self
        # DoS guard: estimate the decoded size from the base64 string length
        # WITHOUT decoding, so a giant payload is rejected before allocation.
        payload = match.group("data")
        estimated_bytes = self._estimated_decoded_size(payload)
        if estimated_bytes > self.max_bytes:
            self.errors.append(
                f"Image size {estimated_bytes} bytes exceeds the maximum of "
                f"{self.max_bytes} bytes"
            )
        return self

    def validate_all(self, images: list[str]):
        """Run every check over a whole list (count + per-item)."""
        self.validate_count(images)
        for image in images or []:
            self.validate_data_uri(image)
            self.validate_mime(image)
            self.validate_size(image)
        return self

    # ===============================================
    # Helpers
    # ===============================================

    def _match(self, image: str):
        if not image or not isinstance(image, str):
            return None
        return _DATA_URI_RE.match(image.strip())

    def _estimated_decoded_size(self, payload: str) -> int:
        payload = payload.strip()
        padding = payload.count("=")
        return (len(payload) * 3) // 4 - padding
