from datetime import datetime

from domain.validations.base_validation import BaseValidation


_MAX_TEXT_LENGTH = 60
_MIN_YEAR = 1950


class VehicleValidator(BaseValidation):
    """
    Vehicle Validation Class
    """

    def __init__(self):
        super().__init__()

    def validate_id(self, id: str):
        if not id:
            self.errors.append("The 'Id' is empty")
        elif not super().is_valid_uuid4(id):
            self.errors.append("The 'Id' is not a valid uuid4")
        return self

    def validate_user_id(self, user_id: str):
        if not user_id:
            self.errors.append("The 'user_id' is empty")
        elif not super().is_valid_uuid4(user_id):
            self.errors.append("The 'user_id' is not a valid uuid4")
        return self

    def validate_name(self, name: str):
        if not name:
            self.errors.append("The 'Name' is empty")
        elif len(name) > _MAX_TEXT_LENGTH:
            self.errors.append(
                f"The 'Name' must be {_MAX_TEXT_LENGTH} characters or fewer"
            )
        return self

    def validate_brand(self, brand: str):
        if not brand:
            self.errors.append("The 'brand' is empty")
        elif len(brand) > _MAX_TEXT_LENGTH:
            self.errors.append(
                f"The 'brand' must be {_MAX_TEXT_LENGTH} characters or fewer"
            )
        return self

    def validate_model(self, model: str):
        if not model:
            self.errors.append("The 'model' is empty")
        elif len(model) > _MAX_TEXT_LENGTH:
            self.errors.append(
                f"The 'model' must be {_MAX_TEXT_LENGTH} characters or fewer"
            )
        return self

    def validate_year(self, year):
        if year is None:
            self.errors.append("The 'year' is empty")
        elif not isinstance(year, int) or isinstance(year, bool):
            self.errors.append("The 'year' must be an integer")
        elif year < _MIN_YEAR or year > datetime.now().year + 1:
            self.errors.append(f"Invalid year: {year}")
        return self
