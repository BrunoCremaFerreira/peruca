from domain.validations.base_validation import BaseValidation


class ShoppingListItemValidator(BaseValidation):
    """
    Shopping List Item Validation Class
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
        elif len(name) < 2:
            self.errors.append("The 'Name' must be 2 or more characters long")
        elif not name.replace(" ", "").isalnum:
            self.errors.append("'Name' must contain letters")
        return self

    def validate_quantity(self, quantity: float):
        if quantity <= 0:
            self.errors.append(f"Invalid quantity: {quantity}")
        return self