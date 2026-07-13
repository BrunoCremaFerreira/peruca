from domain.services.clock import is_valid_timezone
from domain.validations.base_validation import BaseValidation


class UserSettingsValidator(BaseValidation):
    """
    User Settings Validation Class.
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

    def validate_timezone(self, timezone: str):
        """
        Only an existing IANA identifier is accepted — a city name ("Lisboa") is
        the timezone_resolver's input, never a stored value.
        """
        if not timezone or not timezone.strip():
            self.errors.append("The 'timezone' is empty")
        elif not is_valid_timezone(timezone):
            self.errors.append(f"Invalid timezone: {timezone}")
        return self
