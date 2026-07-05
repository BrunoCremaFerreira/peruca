"""
ImageValidator unit tests (TDD - RED phase).

Fase A adds a domain validator for inbound chat images. It follows the fluent
BaseValidation pattern: granular methods append errors, and the terminal
`.validate()` raises ValidationError if any accumulated. Limits (allowed mimes,
max bytes, max count) are injected by the caller (domain never imports
settings).

Contract:
    ImageValidator(allowed_mimes, max_bytes, max_count)
        .validate_count(images)         # too many images
        .validate_data_uri(uri)         # well-formed `data:<mime>;base64,<b64>`
        .validate_mime(uri)             # mime in allowlist
        .validate_size(uri)             # decoded size within max_bytes (len-based,
                                        # checked BEFORE decoding — DoS guard)
        .validate()                     # raises if any error accumulated

Expected to FAIL (ImportError) until image_validation.py exists.
"""

from unittest.mock import patch

import pytest

from domain.exceptions import ValidationError
from domain.validations.image_validation import ImageValidator


ALLOWED = ["image/jpeg", "image/png", "image/webp"]
# "hello" base64 == "aGVsbG8=" → decodes to 5 bytes.
VALID_PNG = "data:image/png;base64,aGVsbG8="
VALID_JPEG = "data:image/jpeg;base64,aGVsbG8="


def _validator(allowed=None, max_bytes=10_000_000, max_count=5):
    return ImageValidator(
        allowed_mimes=allowed if allowed is not None else ALLOWED,
        max_bytes=max_bytes,
        max_count=max_count,
    )


class TestImageValidatorValidCases:
    def test_valid_png_data_uri_passes(self):
        _validator().validate_data_uri(VALID_PNG).validate_mime(
            VALID_PNG
        ).validate_size(VALID_PNG).validate()

    def test_valid_jpeg_data_uri_passes(self):
        _validator().validate_data_uri(VALID_JPEG).validate_mime(
            VALID_JPEG
        ).validate_size(VALID_JPEG).validate()

    def test_count_within_limit_passes(self):
        _validator(max_count=3).validate_count([VALID_PNG, VALID_JPEG]).validate()

    def test_size_at_exact_limit_passes(self):
        # "aGVsbG8=" estimates to 5 bytes; max_bytes=5 is the exact boundary.
        _validator(max_bytes=5).validate_size(VALID_PNG).validate()

    def test_missing_terminal_validate_does_not_raise(self):
        # Documents the fluent pattern: without .validate(), accumulated errors
        # are silently swallowed (no raise).
        _validator().validate_data_uri("garbage")  # error accumulated, not raised


class TestImageValidatorInvalidCases:
    def test_malformed_base64_raises(self):
        with pytest.raises(ValidationError):
            _validator().validate_data_uri(
                "data:image/png;base64,@@@not-base64@@@"
            ).validate()

    def test_not_a_data_uri_raises(self):
        with pytest.raises(ValidationError):
            _validator().validate_data_uri("aGVsbG8=").validate()

    def test_empty_string_raises(self):
        with pytest.raises(ValidationError):
            _validator().validate_data_uri("").validate()

    def test_unsupported_mime_raises(self):
        gif = "data:image/gif;base64,aGVsbG8="
        with pytest.raises(ValidationError):
            _validator().validate_mime(gif).validate()

    def test_size_above_limit_raises(self):
        with pytest.raises(ValidationError):
            _validator(max_bytes=4).validate_size(VALID_PNG).validate()

    def test_count_above_limit_raises(self):
        with pytest.raises(ValidationError):
            _validator(max_count=1).validate_count([VALID_PNG, VALID_JPEG]).validate()

    def test_invalid_item_in_list_raises(self):
        # A convenience path that validates a whole list must flag a bad item.
        with pytest.raises(ValidationError):
            _validator().validate_all([VALID_PNG, "garbage"]).validate()

    def test_valid_list_via_validate_all_passes(self):
        _validator().validate_all([VALID_PNG, VALID_JPEG]).validate()


class TestImageValidatorDosGuard:
    """H-01: an oversized payload must be rejected WITHOUT ever being decoded."""

    def test_oversized_payload_is_not_decoded(self):
        # ~1000 base64 chars estimate to ~750 bytes; cap it well below that.
        oversized = "data:image/png;base64," + ("A" * 1000)
        with patch(
            "domain.validations.image_validation.base64.b64decode"
        ) as decode_spy:
            with pytest.raises(ValidationError):
                _validator(max_bytes=100).validate_all([oversized]).validate()
        decode_spy.assert_not_called()

    def test_validate_data_uri_does_not_decode_when_over_limit(self):
        oversized = "data:image/png;base64," + ("A" * 1000)
        with patch(
            "domain.validations.image_validation.base64.b64decode"
        ) as decode_spy:
            _validator(max_bytes=100).validate_data_uri(oversized)
        decode_spy.assert_not_called()

    def test_within_limit_is_still_decoded_and_validated(self):
        # A small malformed payload within the size limit must still be caught.
        with pytest.raises(ValidationError):
            _validator(max_bytes=10_000).validate_data_uri(
                "data:image/png;base64,@@@@"
            ).validate()


class TestImageValidatorErrorMessages:
    def test_unsupported_mime_message_names_mime(self):
        gif = "data:image/gif;base64,aGVsbG8="
        validator = _validator().validate_mime(gif)
        assert any("image/gif" in e or "mime" in e.lower() for e in validator.errors)

    def test_size_error_message_mentions_size(self):
        validator = _validator(max_bytes=4).validate_size(VALID_PNG)
        assert any(
            "size" in e.lower() or "large" in e.lower() or "bytes" in e.lower()
            for e in validator.errors
        )

    def test_count_error_message_mentions_count(self):
        validator = _validator(max_count=1).validate_count([VALID_PNG, VALID_JPEG])
        assert any(
            "count" in e.lower() or "many" in e.lower() or "images" in e.lower()
            for e in validator.errors
        )
