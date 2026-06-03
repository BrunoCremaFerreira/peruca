from domain.validations.base_validation import BaseValidation
from infra.utils import is_null_or_whitespace


class UserMemoryValidator(BaseValidation):
    """
    UserMemory Validation Class
    """

    def __init__(self):
        super().__init__()

    def validate_id(self, id: str):
        if not id:
            self.errors.append("The 'Id' is empty")

        if not super().is_valid_uuid4(id):
            self.errors.append("The 'Id' is not a valid uuid4")
        return self

    def validate_user_id(self, user_id: str):
        if not user_id:
            self.errors.append("The 'user_id' is empty")

        if not super().is_valid_uuid4(user_id):
            self.errors.append("The 'user_id' is not a valid uuid4")
        return self

    def validate_content(self, content: str):
        if is_null_or_whitespace(content):
            self.errors.append("The 'content' is empty")
        elif len(content) > 1000:
            self.errors.append("The 'content' has more than 1000 characters")
        return self
