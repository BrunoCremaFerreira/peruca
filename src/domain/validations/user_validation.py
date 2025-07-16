from domain.validations.base_validation import BaseValidation


class UserValidator(BaseValidation):
    """
    User Validation Class
    """

    def __init__(self):
        super().__init__()

    def validate_id(self, id: str):
        if not id:
            self.errors.append("The 'Id' is empty")
        
        if not super().is_valid_uuid4(id):
            self.errors.append("The 'Id' is not a valid uuid4")
        return self

    def validate_name(self, name: str):
        if not name:
            self.errors.append("The 'Name' is empty")
        elif len(name) < 3:
            self.errors.append("The 'Name' must be 3 or more characters long")
        elif not name.replace(" ", "").isalpha():
            self.errors.append("'Name' must contain only letters")
        return self

    def validate_summary(self, summary: str):
        if summary and len(summary) > 10000:
            self.errors.append("The 'summary' has more than 1000 caracteres.")
        return self