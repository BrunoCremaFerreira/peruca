
import uuid
from domain.exceptions import ValidationError


class BaseValidation:
    """
    Base class for validations
    """

    def __init__(self):
        self.errors = []

    def validate(self):
        if self.errors:
            raise ValidationError(self.errors)
        return self
    
    def is_valid_uuid4(self, value: str) -> bool:
        try:
            val = uuid.UUID(value, version=4)
            return str(val) == value.lower()
        except ValueError:
            return False