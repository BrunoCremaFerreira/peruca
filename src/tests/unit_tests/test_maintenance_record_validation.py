"""
MaintenanceRecordValidator unit tests (TDD — written before implementation).

odometer_km is optional (the multi-turn flow may skip it); when present it must
be strictly positive and within a plausible ceiling. performed_at must be a real,
non-future date not before 1950.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from domain.validations.maintenance_record_validation import (
    MaintenanceRecordValidator,
)


def _valid_uuid() -> str:
    return str(uuid.uuid4())


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


class TestMaintenanceRecordValidatorId:
    def test_valid_uuid__no_error(self):
        assert MaintenanceRecordValidator().validate_id(_valid_uuid()).errors == []

    def test_empty__error(self):
        assert MaintenanceRecordValidator().validate_id("").errors


class TestMaintenanceRecordValidatorVehicleId:
    def test_valid_uuid__no_error(self):
        assert (
            MaintenanceRecordValidator().validate_vehicle_id(_valid_uuid()).errors == []
        )

    def test_invalid__error(self):
        assert MaintenanceRecordValidator().validate_vehicle_id("nope").errors


class TestMaintenanceRecordValidatorDescription:
    def test_valid__no_error(self):
        assert (
            MaintenanceRecordValidator()
            .validate_description("troca dos 4 pneus")
            .errors
            == []
        )

    def test_empty__error(self):
        assert MaintenanceRecordValidator().validate_description("").errors

    def test_too_long__error(self):
        assert MaintenanceRecordValidator().validate_description("x" * 501).errors


class TestMaintenanceRecordValidatorPerformedAt:
    def test_today__no_error(self):
        assert (
            MaintenanceRecordValidator().validate_performed_at(date.today()).errors == []
        )

    def test_past__no_error(self):
        assert (
            MaintenanceRecordValidator()
            .validate_performed_at(date(2025, 10, 25))
            .errors
            == []
        )

    def test_future__error(self):
        # "Future" is now measured against the greatest civil date that exists
        # anywhere on Earth (UTC+14), not against the server's own date — see
        # TestMaintenanceRecordValidatorPerformedAtEarthBoundary below.
        beyond_earth = _utc_today() + timedelta(days=2)
        assert MaintenanceRecordValidator().validate_performed_at(beyond_earth).errors

    def test_none__error(self):
        assert MaintenanceRecordValidator().validate_performed_at(None).errors

    def test_before_1950__error(self):
        assert (
            MaintenanceRecordValidator().validate_performed_at(date(1949, 12, 31)).errors
        )


class TestMaintenanceRecordValidatorPerformedAtEarthBoundary:
    """
    performed_at is a CIVIL date (no timezone), so the future guard must compare
    it to ``clock.max_civil_date_on_earth()`` (= UTC today + 1 day, the local
    date at UTC+14) instead of the server's ``date.today()``. A user in a
    timezone ahead of the server registering "today" must not be rejected.
    """

    def test_utc_today__accepted(self):
        assert (
            MaintenanceRecordValidator().validate_performed_at(_utc_today()).errors == []
        )

    def test_utc_today_plus_one_day__accepted(self):
        # It is already "today" somewhere on Earth (UTC+14).
        earth_max = _utc_today() + timedelta(days=1)
        assert MaintenanceRecordValidator().validate_performed_at(earth_max).errors == []

    def test_utc_today_plus_two_days__rejected(self):
        # The guard is still a guard: no date exists this far ahead anywhere.
        beyond_earth = _utc_today() + timedelta(days=2)
        assert MaintenanceRecordValidator().validate_performed_at(beyond_earth).errors


class TestMaintenanceRecordValidatorOdometer:
    def test_positive__no_error(self):
        assert MaintenanceRecordValidator().validate_odometer_km(101127).errors == []

    def test_none_is_allowed(self):
        # km may be skipped ("não sei") — None is valid.
        assert MaintenanceRecordValidator().validate_odometer_km(None).errors == []

    def test_zero__error(self):
        assert MaintenanceRecordValidator().validate_odometer_km(0).errors

    def test_negative__error(self):
        assert MaintenanceRecordValidator().validate_odometer_km(-5).errors

    def test_above_ceiling__error(self):
        assert MaintenanceRecordValidator().validate_odometer_km(2_000_001).errors


class TestMaintenanceRecordValidatorChain:
    def test_full_valid_chain_does_not_raise(self):
        (
            MaintenanceRecordValidator()
            .validate_id(_valid_uuid())
            .validate_vehicle_id(_valid_uuid())
            .validate_description("troca de óleo")
            .validate_performed_at(date(2025, 10, 25))
            .validate_odometer_km(100232)
            .validate()
        )
