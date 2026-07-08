from datetime import date

from domain.validations.base_validation import BaseValidation


_MAX_DESCRIPTION_LENGTH = 500
_MIN_DATE = date(1980, 1, 1)
_EVENT_TYPES = frozenset(
    {"vaccine", "dewormer", "antiparasitic", "medication", "vet_visit", "other"}
)


class PetHealthEventValidator(BaseValidation):
    """
    Pet Health Event Validation Class.
    """

    def __init__(self):
        super().__init__()

    def validate_id(self, id: str):
        if not id:
            self.errors.append("The 'Id' is empty")
        elif not super().is_valid_uuid4(id):
            self.errors.append("The 'Id' is not a valid uuid4")
        return self

    def validate_pet_id(self, pet_id: str):
        if not pet_id:
            self.errors.append("The 'pet_id' is empty")
        elif not super().is_valid_uuid4(pet_id):
            self.errors.append("The 'pet_id' is not a valid uuid4")
        return self

    def validate_event_type(self, event_type: str):
        if not event_type:
            self.errors.append("The 'event_type' is empty")
        elif event_type not in _EVENT_TYPES:
            self.errors.append(f"Invalid event_type: {event_type}")
        return self

    def validate_description(self, description: str):
        if not description or not description.strip():
            self.errors.append("The 'description' is empty")
        elif len(description) > _MAX_DESCRIPTION_LENGTH:
            self.errors.append(
                f"The 'description' must be {_MAX_DESCRIPTION_LENGTH} characters or fewer"
            )
        return self

    def validate_occurred_at(self, occurred_at):
        if occurred_at is None:
            self.errors.append("The 'occurred_at' is empty")
        elif not isinstance(occurred_at, date):
            self.errors.append("The 'occurred_at' must be a date")
        elif occurred_at > date.today():
            self.errors.append("The 'occurred_at' cannot be in the future")
        elif occurred_at < _MIN_DATE:
            self.errors.append("The 'occurred_at' is too far in the past")
        return self
