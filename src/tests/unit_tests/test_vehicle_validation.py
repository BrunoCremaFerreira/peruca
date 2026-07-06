"""
VehicleValidator unit tests (TDD — written before implementation).

Fluent validator: each validate_* appends to .errors and returns self; the final
.validate() raises ValidationError when any error was collected. Tests inspect
.errors directly (without .validate()) so each rule is asserted in isolation.
"""

import uuid
from datetime import datetime

from domain.validations.vehicle_validation import VehicleValidator


def _valid_uuid() -> str:
    return str(uuid.uuid4())


class TestVehicleValidatorId:
    def test_valid_uuid__no_error(self):
        v = VehicleValidator().validate_id(_valid_uuid())
        assert v.errors == []

    def test_empty__error(self):
        v = VehicleValidator().validate_id("")
        assert v.errors

    def test_not_a_uuid__error(self):
        v = VehicleValidator().validate_id("not-a-uuid")
        assert v.errors


class TestVehicleValidatorUserId:
    def test_valid_uuid__no_error(self):
        v = VehicleValidator().validate_user_id(_valid_uuid())
        assert v.errors == []

    def test_empty__error(self):
        v = VehicleValidator().validate_user_id("")
        assert v.errors


class TestVehicleValidatorName:
    def test_valid__no_error(self):
        v = VehicleValidator().validate_name("Mitsubishi Outlander")
        assert v.errors == []

    def test_empty__error(self):
        v = VehicleValidator().validate_name("")
        assert v.errors

    def test_too_long__error(self):
        v = VehicleValidator().validate_name("x" * 61)
        assert v.errors


class TestVehicleValidatorBrandModel:
    def test_valid_brand__no_error(self):
        assert VehicleValidator().validate_brand("Mitsubishi").errors == []

    def test_empty_brand__error(self):
        assert VehicleValidator().validate_brand("").errors

    def test_brand_too_long__error(self):
        assert VehicleValidator().validate_brand("x" * 61).errors

    def test_valid_model__no_error(self):
        assert VehicleValidator().validate_model("Outlander").errors == []

    def test_model_too_long__error(self):
        assert VehicleValidator().validate_model("x" * 61).errors


class TestVehicleValidatorYear:
    def test_valid__no_error(self):
        assert VehicleValidator().validate_year(2015).errors == []

    def test_none__error(self):
        assert VehicleValidator().validate_year(None).errors

    def test_before_1950__error(self):
        assert VehicleValidator().validate_year(1949).errors

    def test_after_current_plus_one__error(self):
        future = datetime.now().year + 2
        assert VehicleValidator().validate_year(future).errors

    def test_next_year_is_allowed(self):
        # A model-year one ahead of the current calendar year is legitimate.
        assert VehicleValidator().validate_year(datetime.now().year + 1).errors == []


class TestVehicleValidatorChainAndValidate:
    def test_full_valid_chain_does_not_raise(self):
        (
            VehicleValidator()
            .validate_id(_valid_uuid())
            .validate_user_id(_valid_uuid())
            .validate_name("Mitsubishi Pajero")
            .validate_brand("Mitsubishi")
            .validate_model("Pajero")
            .validate_year(2018)
            .validate()
        )
