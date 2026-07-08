from datetime import date

from domain.services.text_matching import normalize
from domain.validations.base_validation import BaseValidation


_MAX_TEXT_LENGTH = 60
_MAX_DESCRIPTION_LENGTH = 500
_SEX_VALUES = frozenset({"male", "female", "unknown"})


class PetValidator(BaseValidation):
    """
    Pet Validation Class.
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

    def validate_nicknames(self, nicknames, name: str = ""):
        """
        Nicknames are validated as a group against the pet's own ``name``. An
        empty list is valid; a blank/too-long item, a normalized duplicate, or a
        term normalizing to the pet's own name is an error (§2.8).
        """
        if nicknames is None:
            return self
        if not isinstance(nicknames, list):
            self.errors.append("The 'nicknames' must be a list")
            return self

        name_norm = normalize(name)
        seen = set()
        for nickname in nicknames:
            if not isinstance(nickname, str) or not nickname.strip():
                self.errors.append("A nickname is empty")
                continue
            if len(nickname) > _MAX_TEXT_LENGTH:
                self.errors.append(
                    f"A nickname must be {_MAX_TEXT_LENGTH} characters or fewer"
                )
            normalized = normalize(nickname)
            if name_norm and normalized == name_norm:
                self.errors.append(
                    f"The nickname '{nickname}' collides with the pet's name"
                )
            if normalized in seen:
                self.errors.append(f"The nickname '{nickname}' is duplicated")
            else:
                seen.add(normalized)
        return self

    def validate_birth_date(self, birth_date):
        if birth_date is None:
            return self
        if not isinstance(birth_date, date):
            self.errors.append("The 'birth_date' must be a date")
        elif birth_date > date.today():
            self.errors.append("The 'birth_date' cannot be in the future")
        return self

    def validate_sex(self, sex: str):
        if not sex:
            self.errors.append("The 'sex' is empty")
        elif sex not in _SEX_VALUES:
            self.errors.append(f"Invalid sex: {sex}")
        return self

    def validate_species(self, species: str):
        if not species:
            self.errors.append("The 'species' is empty")
        elif len(species) > _MAX_TEXT_LENGTH:
            self.errors.append(
                f"The 'species' must be {_MAX_TEXT_LENGTH} characters or fewer"
            )
        return self

    def validate_description(self, description: str):
        if description and len(description) > _MAX_DESCRIPTION_LENGTH:
            self.errors.append(
                f"The 'description' must be {_MAX_DESCRIPTION_LENGTH} characters or fewer"
            )
        return self
