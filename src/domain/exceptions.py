class ValidationError(Exception):
    """
    Validation Errors Exception
    """
    
    def __init__(self, errors, status_code: int = 400):
        self.errors = errors
        self.status_code = status_code
        super().__init__("Validation failed")

class NofFoundValidationError(ValidationError):
    """
    Resource Not Found Validation Error
    """

    def __init__(self, entity_name: str, key_name: str, value: str):
        super().__init__(errors = [f"The {entity_name} with {key_name} '{value}', was not Found"], status_code=404)