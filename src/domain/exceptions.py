class ValidationError(Exception):
    """
    Validation Errors Exception
    """
    
    def __init__(self, errors, status_code: int = 400):
        self.errors = errors
        self.status_code = status_code
        super().__init__("Validation failed")