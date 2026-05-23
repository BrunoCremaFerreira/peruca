import pytest

from domain.exceptions import ValidationError
from domain.validations.shopping_list_item_validation import ShoppingListItemValidator


"""
ShoppingListItemValidator Unit Tests
"""


class TestShoppingListItemValidatorId:

    def test_validate_id_valid_uuid4_passes(self):
        # Arrange
        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
        validator = ShoppingListItemValidator()
        # Act
        validator.validate_id(valid_uuid)
        # Assert
        assert validator.errors == []

    def test_validate_id_empty_adds_error(self):
        # Arrange
        validator = ShoppingListItemValidator()
        # Act
        validator.validate_id("")
        # Assert
        assert any("Id" in e for e in validator.errors)

    def test_validate_id_invalid_format_adds_error(self):
        # Arrange
        validator = ShoppingListItemValidator()
        # Act
        validator.validate_id("not-a-uuid")
        # Assert
        assert any("uuid4" in e for e in validator.errors)

    def test_validate_id_none_adds_error(self):
        # Arrange
        validator = ShoppingListItemValidator()
        # Act
        validator.validate_id(None)
        # Assert
        assert any("Id" in e or "uuid4" in e for e in validator.errors)


class TestShoppingListItemValidatorName:

    def test_validate_name_valid_passes(self):
        # Arrange
        validator = ShoppingListItemValidator()
        # Act
        validator.validate_name("Milk")
        # Assert
        assert validator.errors == []

    def test_validate_name_empty_adds_error(self):
        # Arrange
        validator = ShoppingListItemValidator()
        # Act
        validator.validate_name("")
        # Assert
        assert any("Name" in e for e in validator.errors)

    def test_validate_name_single_char_adds_error(self):
        # Arrange
        validator = ShoppingListItemValidator()
        # Act
        validator.validate_name("A")
        # Assert
        assert any("2" in e or "characters" in e for e in validator.errors)

    def test_validate_name_exactly_two_chars_passes(self):
        # Arrange
        validator = ShoppingListItemValidator()
        # Act
        validator.validate_name("AB")
        # Assert
        assert validator.errors == []

    def test_validate_name_with_spaces_passes(self):
        # Arrange
        validator = ShoppingListItemValidator()
        # Act
        validator.validate_name("Orange Juice")
        # Assert
        assert validator.errors == []


class TestShoppingListItemValidatorQuantity:

    def test_validate_quantity_positive_passes(self):
        # Arrange
        validator = ShoppingListItemValidator()
        # Act
        validator.validate_quantity(2.5)
        # Assert
        assert validator.errors == []

    def test_validate_quantity_zero_adds_error(self):
        # Arrange
        validator = ShoppingListItemValidator()
        # Act
        validator.validate_quantity(0)
        # Assert
        assert any("quantity" in e.lower() or "Invalid" in e for e in validator.errors)

    def test_validate_quantity_negative_adds_error(self):
        # Arrange
        validator = ShoppingListItemValidator()
        # Act
        validator.validate_quantity(-1.0)
        # Assert
        assert any("quantity" in e.lower() or "Invalid" in e for e in validator.errors)

    def test_validate_quantity_fractional_positive_passes(self):
        # Arrange
        validator = ShoppingListItemValidator()
        # Act
        validator.validate_quantity(0.5)
        # Assert
        assert validator.errors == []


class TestShoppingListItemValidatorChaining:

    def test_chained_errors_are_all_collected(self):
        # Arrange / Act
        with pytest.raises(ValidationError) as exc:
            ShoppingListItemValidator() \
                .validate_name("") \
                .validate_quantity(-3) \
                .validate()
        # Assert
        assert len(exc.value.errors) >= 2

    def test_valid_item_raises_no_exception(self):
        # Arrange / Act / Assert — no exception expected
        ShoppingListItemValidator() \
            .validate_name("Bread") \
            .validate_quantity(1) \
            .validate()
