import pytest

from domain.exceptions import ValidationError
from domain.validations.user_validation import UserValidator


"""
UserValidator Unit Tests
"""


class TestUserValidatorId:
    def test_validate_id_valid_uuid4_passes(self):
        # Arrange
        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
        validator = UserValidator()
        # Act / Assert (no exception raised)
        validator.validate_id(valid_uuid)
        assert validator.errors == []

    def test_validate_id_empty_string_adds_error(self):
        # Arrange
        validator = UserValidator()
        # Act
        validator.validate_id("")
        # Assert
        assert any("Id" in e for e in validator.errors)

    def test_validate_id_non_uuid_adds_error(self):
        # Arrange
        validator = UserValidator()
        # Act
        validator.validate_id("not-a-uuid")
        # Assert
        assert any("uuid4" in e for e in validator.errors)

    def test_validate_id_none_adds_error(self):
        # Arrange
        validator = UserValidator()
        # Act
        validator.validate_id(None)
        # Assert
        assert any("Id" in e or "uuid4" in e for e in validator.errors)


class TestUserValidatorExternalId:
    def test_validate_external_id_short_value_passes(self):
        # Arrange
        validator = UserValidator()
        # Act
        validator.validate_external_id("ext-123")
        # Assert
        assert validator.errors == []

    def test_validate_external_id_empty_passes(self):
        # Arrange
        validator = UserValidator()
        # Act
        validator.validate_external_id("")
        # Assert
        assert validator.errors == []

    def test_validate_external_id_too_long_adds_error(self):
        # Arrange
        long_ext_id = "x" * 101
        validator = UserValidator()
        # Act
        validator.validate_external_id(long_ext_id)
        # Assert
        assert any("external_id" in e for e in validator.errors)

    def test_validate_external_id_exactly_100_chars_passes(self):
        # Arrange
        exactly_100 = "a" * 100
        validator = UserValidator()
        # Act
        validator.validate_external_id(exactly_100)
        # Assert
        assert validator.errors == []


class TestUserValidatorName:
    def test_validate_name_valid_passes(self):
        # Arrange
        validator = UserValidator()
        # Act
        validator.validate_name("Alice")
        # Assert
        assert validator.errors == []

    def test_validate_name_empty_adds_error(self):
        # Arrange
        validator = UserValidator()
        # Act
        validator.validate_name("")
        # Assert
        assert any("Name" in e for e in validator.errors)

    def test_validate_name_too_short_adds_error(self):
        # Arrange
        validator = UserValidator()
        # Act
        validator.validate_name("Jo")
        # Assert
        assert any("3" in e or "characters" in e for e in validator.errors)

    def test_validate_name_with_digits_adds_error(self):
        # Arrange
        validator = UserValidator()
        # Act
        validator.validate_name("Alice1")
        # Assert
        assert any("letters" in e for e in validator.errors)

    def test_validate_name_with_special_chars_adds_error(self):
        # Arrange
        validator = UserValidator()
        # Act
        validator.validate_name("Al!ce")
        # Assert
        assert any("letters" in e for e in validator.errors)

    def test_validate_name_with_spaces_allowed(self):
        # Arrange
        validator = UserValidator()
        # Act
        validator.validate_name("Anna Maria")
        # Assert
        assert validator.errors == []


class TestUserValidatorSummary:
    def test_validate_summary_valid_passes(self):
        # Arrange
        validator = UserValidator()
        # Act
        validator.validate_summary("A short summary")
        # Assert
        assert validator.errors == []

    def test_validate_summary_empty_passes(self):
        # Arrange
        validator = UserValidator()
        # Act
        validator.validate_summary("")
        # Assert
        assert validator.errors == []

    def test_validate_summary_too_long_adds_error(self):
        # Arrange
        long_summary = "x" * 10001
        validator = UserValidator()
        # Act
        validator.validate_summary(long_summary)
        # Assert
        assert any("summary" in e for e in validator.errors)

    def test_validate_summary_exactly_10000_chars_passes(self):
        # Arrange
        max_summary = "a" * 10000
        validator = UserValidator()
        # Act
        validator.validate_summary(max_summary)
        # Assert
        assert validator.errors == []


class TestUserValidatorChaining:
    def test_multiple_errors_are_collected(self):
        # Arrange / Act
        with pytest.raises(ValidationError) as exc:
            UserValidator().validate_name("Jo").validate_summary("x" * 10001).validate()
        # Assert
        assert len(exc.value.errors) >= 2

    def test_validate_raises_only_when_errors_exist(self):
        # Arrange / Act / Assert – no exception
        UserValidator().validate_name("Carlos").validate_summary("ok").validate()
