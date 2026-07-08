"""
PetValidator unit tests (TDD — written before implementation, Fase A / RED).

Fluent validator: each validate_* appends to .errors and returns self; the final
.validate() raises ValidationError when any error was collected. Tests inspect
.errors directly (without .validate()) so each rule is asserted in isolation.

nicknames are validated as a group against the pet's own ``name``:
    validate_nicknames(nicknames, name)
An empty nickname list is valid; a blank/too-long item, a duplicate normalized
term, or a term normalizing to the pet's own name is an error (§2.8).
"""

import uuid
from datetime import date, timedelta

from domain.validations.pet_validation import PetValidator


def _valid_uuid() -> str:
    return str(uuid.uuid4())


class TestPetValidatorId:
    def test_valid_uuid__no_error(self):
        assert PetValidator().validate_id(_valid_uuid()).errors == []

    def test_empty__error(self):
        assert PetValidator().validate_id("").errors

    def test_not_a_uuid__error(self):
        assert PetValidator().validate_id("not-a-uuid").errors


class TestPetValidatorUserId:
    def test_valid_uuid__no_error(self):
        assert PetValidator().validate_user_id(_valid_uuid()).errors == []

    def test_empty__error(self):
        assert PetValidator().validate_user_id("").errors

    def test_not_a_uuid__error(self):
        assert PetValidator().validate_user_id("nope").errors


class TestPetValidatorName:
    def test_valid__no_error(self):
        assert PetValidator().validate_name("Caçolin").errors == []

    def test_empty__error(self):
        assert PetValidator().validate_name("").errors

    def test_too_long__error(self):
        assert PetValidator().validate_name("x" * 61).errors


class TestPetValidatorNicknames:
    def test_empty_list_is_valid(self):
        assert PetValidator().validate_nicknames([], "Caçolin").errors == []

    def test_valid_list__no_error(self):
        assert PetValidator().validate_nicknames(["Lilo", "Suzu"], "Caçolin").errors == []

    def test_blank_item__error(self):
        assert PetValidator().validate_nicknames(["   "], "Caçolin").errors

    def test_item_too_long__error(self):
        assert PetValidator().validate_nicknames(["x" * 61], "Caçolin").errors

    def test_normalized_duplicate__error(self):
        # "Lilo" and "lilo" normalize to the same term.
        assert PetValidator().validate_nicknames(["Lilo", "lilo"], "Caçolin").errors

    def test_collides_with_name__error(self):
        # A nickname normalizing to the pet's own name is rejected.
        assert PetValidator().validate_nicknames(["Caçolin"], "Caçolin").errors


class TestPetValidatorBirthDate:
    def test_none_is_valid(self):
        assert PetValidator().validate_birth_date(None).errors == []

    def test_past_date__no_error(self):
        assert PetValidator().validate_birth_date(date(2020, 1, 1)).errors == []

    def test_future__error(self):
        assert PetValidator().validate_birth_date(date.today() + timedelta(days=1)).errors

    def test_not_a_date__error(self):
        assert PetValidator().validate_birth_date("2020-01-01").errors


class TestPetValidatorSex:
    def test_male__no_error(self):
        assert PetValidator().validate_sex("male").errors == []

    def test_female__no_error(self):
        assert PetValidator().validate_sex("female").errors == []

    def test_unknown__no_error(self):
        assert PetValidator().validate_sex("unknown").errors == []

    def test_empty__error(self):
        assert PetValidator().validate_sex("").errors

    def test_out_of_set__error(self):
        assert PetValidator().validate_sex("other").errors


class TestPetValidatorSpecies:
    def test_valid__no_error(self):
        assert PetValidator().validate_species("dog").errors == []

    def test_empty__error(self):
        assert PetValidator().validate_species("").errors

    def test_too_long__error(self):
        assert PetValidator().validate_species("x" * 61).errors


class TestPetValidatorDescription:
    def test_empty_is_valid(self):
        # description is optional.
        assert PetValidator().validate_description("").errors == []

    def test_valid__no_error(self):
        assert PetValidator().validate_description("vira-lata caramelo").errors == []

    def test_too_long__error(self):
        assert PetValidator().validate_description("x" * 501).errors


class TestPetValidatorChainAndValidate:
    def test_full_valid_chain_does_not_raise(self):
        (
            PetValidator()
            .validate_id(_valid_uuid())
            .validate_user_id(_valid_uuid())
            .validate_name("Caçolin")
            .validate_nicknames(["Lilo", "Suzu"], "Caçolin")
            .validate_birth_date(date(2020, 1, 1))
            .validate_sex("male")
            .validate_species("dog")
            .validate_description("preguiçoso, adora o sofá")
            .validate()
        )
