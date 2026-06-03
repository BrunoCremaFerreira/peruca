"""
UserMemoryValidator Unit Tests (TDD - RED phase)

Covers the fluent validation chain for the new UserMemory domain object:
  - validate_id(id)        -> must be a valid uuid4
  - validate_user_id(...)  -> must be a valid uuid4 / non-empty
  - validate_content(...)  -> non-empty (no whitespace-only) and len <= 1000

The validator inherits from BaseValidation, so it ONLY raises on the final
.validate() call. Each validate_* method returns self to allow chaining.

These tests are expected to FAIL with ImportError until
domain.validations.user_memory_validation.UserMemoryValidator exists.
"""

import uuid

import pytest

from domain.exceptions import ValidationError
from domain.validations.user_memory_validation import UserMemoryValidator


# ===========================================================================
# Helpers
# ===========================================================================


def _valid_uuid() -> str:
    return str(uuid.uuid4())


# ===========================================================================
# TestUserMemoryValidatorValid
# ===========================================================================


class TestUserMemoryValidatorValid:
    def test_validate__all_fields_valid__does_not_raise(self):
        # Arrange
        memory_id = _valid_uuid()
        user_id = _valid_uuid()
        content = "Prefere café sem açúcar"
        # Act / Assert (must not raise)
        (
            UserMemoryValidator()
            .validate_id(memory_id)
            .validate_user_id(user_id)
            .validate_content(content)
            .validate()
        )

    def test_validate__content_at_max_length__does_not_raise(self):
        # Arrange
        content = "x" * 1000
        # Act / Assert
        (
            UserMemoryValidator()
            .validate_id(_valid_uuid())
            .validate_user_id(_valid_uuid())
            .validate_content(content)
            .validate()
        )

    def test_methods_return_self_for_chaining(self):
        # Arrange
        validator = UserMemoryValidator()
        # Act
        result = validator.validate_id(_valid_uuid())
        # Assert
        assert result is validator


# ===========================================================================
# TestUserMemoryValidatorId
# ===========================================================================


class TestUserMemoryValidatorId:
    def test_validate_id__empty__raises_validation_error(self):
        # Arrange / Act / Assert
        with pytest.raises(ValidationError) as exc:
            UserMemoryValidator().validate_id("").validate()
        assert "Id" in str(exc.value.errors)

    def test_validate_id__not_uuid4__raises_validation_error(self):
        # Arrange / Act / Assert
        with pytest.raises(ValidationError) as exc:
            UserMemoryValidator().validate_id("not-a-uuid").validate()
        assert "Id" in str(exc.value.errors)


# ===========================================================================
# TestUserMemoryValidatorUserId
# ===========================================================================


class TestUserMemoryValidatorUserId:
    def test_validate_user_id__empty__raises_validation_error(self):
        # Arrange / Act / Assert
        with pytest.raises(ValidationError) as exc:
            UserMemoryValidator().validate_user_id("").validate()
        assert "user_id" in str(exc.value.errors)

    def test_validate_user_id__not_uuid4__raises_validation_error(self):
        # Arrange / Act / Assert
        with pytest.raises(ValidationError) as exc:
            UserMemoryValidator().validate_user_id("123-not-uuid").validate()
        assert "user_id" in str(exc.value.errors)


# ===========================================================================
# TestUserMemoryValidatorContent
# ===========================================================================


class TestUserMemoryValidatorContent:
    def test_validate_content__empty__raises_validation_error(self):
        # Arrange / Act / Assert
        with pytest.raises(ValidationError) as exc:
            UserMemoryValidator().validate_content("").validate()
        assert "content" in str(exc.value.errors)

    def test_validate_content__whitespace_only__raises_validation_error(self):
        # Arrange / Act / Assert
        with pytest.raises(ValidationError) as exc:
            UserMemoryValidator().validate_content("   \n\t ").validate()
        assert "content" in str(exc.value.errors)

    def test_validate_content__too_long__raises_validation_error(self):
        # Arrange
        content = "x" * 1001
        # Act / Assert
        with pytest.raises(ValidationError) as exc:
            UserMemoryValidator().validate_content(content).validate()
        assert "content" in str(exc.value.errors)


# ===========================================================================
# TestUserMemoryValidatorCombined
# ===========================================================================


class TestUserMemoryValidatorCombined:
    def test_validate__multiple_invalid_fields__collects_all_errors(self):
        # Arrange / Act / Assert
        with pytest.raises(ValidationError) as exc:
            (
                UserMemoryValidator()
                .validate_id("bad")
                .validate_user_id("bad")
                .validate_content("")
                .validate()
            )
        errors = str(exc.value.errors)
        assert "Id" in errors
        assert "user_id" in errors
        assert "content" in errors
