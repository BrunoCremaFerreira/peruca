"""
PetHealthEventValidator unit tests (TDD — written before implementation, Fase A).

event_type is a closed set (§2.8); description is free text (non-empty, capped);
occurred_at must be a real, non-future date not before 1980-01-01.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from domain.validations.pet_health_event_validation import PetHealthEventValidator


def _valid_uuid() -> str:
    return str(uuid.uuid4())


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


class TestPetHealthEventValidatorId:
    def test_valid_uuid__no_error(self):
        assert PetHealthEventValidator().validate_id(_valid_uuid()).errors == []

    def test_empty__error(self):
        assert PetHealthEventValidator().validate_id("").errors


class TestPetHealthEventValidatorPetId:
    def test_valid_uuid__no_error(self):
        assert PetHealthEventValidator().validate_pet_id(_valid_uuid()).errors == []

    def test_invalid__error(self):
        assert PetHealthEventValidator().validate_pet_id("nope").errors


class TestPetHealthEventValidatorEventType:
    def test_vaccine__no_error(self):
        assert PetHealthEventValidator().validate_event_type("vaccine").errors == []

    def test_vet_visit__no_error(self):
        assert PetHealthEventValidator().validate_event_type("vet_visit").errors == []

    def test_other__no_error(self):
        assert PetHealthEventValidator().validate_event_type("other").errors == []

    def test_out_of_set__error(self):
        assert PetHealthEventValidator().validate_event_type("surgery").errors

    def test_empty__error(self):
        assert PetHealthEventValidator().validate_event_type("").errors


class TestPetHealthEventValidatorDescription:
    def test_valid__no_error(self):
        assert PetHealthEventValidator().validate_description("DHPPI").errors == []

    def test_empty__error(self):
        assert PetHealthEventValidator().validate_description("").errors

    def test_too_long__error(self):
        assert PetHealthEventValidator().validate_description("x" * 501).errors


class TestPetHealthEventValidatorOccurredAt:
    def test_today__no_error(self):
        assert PetHealthEventValidator().validate_occurred_at(date.today()).errors == []

    def test_past__no_error(self):
        assert (
            PetHealthEventValidator().validate_occurred_at(date(2026, 2, 20)).errors == []
        )

    def test_future__error(self):
        # "Future" is measured against the greatest civil date existing anywhere
        # on Earth (UTC+14) — see TestPetHealthEventValidatorOccurredAtEarthBoundary.
        beyond_earth = _utc_today() + timedelta(days=2)
        assert PetHealthEventValidator().validate_occurred_at(beyond_earth).errors

    def test_none__error(self):
        assert PetHealthEventValidator().validate_occurred_at(None).errors

    def test_before_1980__error(self):
        assert PetHealthEventValidator().validate_occurred_at(date(1979, 12, 31)).errors


class TestPetHealthEventValidatorOccurredAtEarthBoundary:
    """
    occurred_at is a CIVIL date (no timezone): the future guard must compare it
    to ``clock.max_civil_date_on_earth()`` (UTC today + 1 day = the local date at
    UTC+14), never to the server's ``date.today()`` — otherwise a user in a
    timezone ahead of the server cannot register a vaccine given "today".
    """

    def test_utc_today__accepted(self):
        assert PetHealthEventValidator().validate_occurred_at(_utc_today()).errors == []

    def test_utc_today_plus_one_day__accepted(self):
        earth_max = _utc_today() + timedelta(days=1)
        assert PetHealthEventValidator().validate_occurred_at(earth_max).errors == []

    def test_utc_today_plus_two_days__rejected(self):
        beyond_earth = _utc_today() + timedelta(days=2)
        assert PetHealthEventValidator().validate_occurred_at(beyond_earth).errors


class TestPetHealthEventValidatorChain:
    def test_full_valid_chain_does_not_raise(self):
        (
            PetHealthEventValidator()
            .validate_id(_valid_uuid())
            .validate_pet_id(_valid_uuid())
            .validate_event_type("vaccine")
            .validate_description("DHPPI")
            .validate_occurred_at(date(2026, 2, 20))
            .validate()
        )
