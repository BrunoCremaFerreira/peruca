"""
REST/ViewModel contract freeze (plan §3.6 / §10.6).

Decision being frozen: the REST layer NEVER localizes. Datetimes stay UTC
(ISO-8601 with a "+00:00" offset) and civil dates (`performed_at`, `occurred_at`,
`birth_date`) are echoed exactly as stored — the client formats. The user's
timezone is a CHAT presentation concern only (`format_local` / the datetime
presenter); it must never leak into `auto_map`, a ViewModel, or an app service
that serves a route.

These tests are green today ON PURPOSE: they are the guard-rail that keeps someone
from "finishing the feature" by converting the API responses too — which would
silently move a civil date to the previous/next day and break every REST client.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional
from unittest.mock import MagicMock

from application.appservices.pet_app_service import PetAppService
from application.appservices.vehicle_app_service import VehicleAppService
from domain.entities import MaintenanceRecord, Pet, PetHealthEvent, Vehicle
from infra.utils import auto_map


def _uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class _DatetimeCarryingResponse:
    """Stand-in for a future ViewModel that decides to expose a timestamp."""

    id: str = ""
    when_created: Optional[datetime] = None


def _sample_record(vehicle_id: str) -> MaintenanceRecord:
    # An instant that is "the previous day" in São Paulo: 01:00Z on the 10th is
    # 22:00 on the 9th. Any accidental localization moves the day and this shows it.
    return MaintenanceRecord(
        id=_uuid(),
        vehicle_id=vehicle_id,
        description="troca de óleo",
        performed_at=date(2026, 7, 10),
        odometer_km=100232,
        when_created=datetime(2026, 7, 10, 1, 0, tzinfo=timezone.utc),
    )


def _sample_event(pet_id: str) -> PetHealthEvent:
    return PetHealthEvent(
        id=_uuid(),
        pet_id=pet_id,
        event_type="vaccine",
        description="DHPPI",
        occurred_at=date(2026, 7, 10),
        when_created=datetime(2026, 7, 10, 1, 0, tzinfo=timezone.utc),
    )


def _make_vehicle_service(vehicle_id, records):
    vehicle_repository = MagicMock()
    vehicle_repository.get_by_id.return_value = Vehicle(
        id=vehicle_id, user_id=_uuid(), name="Outlander"
    )
    maintenance_record_repository = MagicMock()
    maintenance_record_repository.get_all_by_vehicle_id.return_value = records
    return VehicleAppService(
        vehicle_service=MagicMock(),
        vehicle_repository=vehicle_repository,
        maintenance_record_repository=maintenance_record_repository,
        user_repository=MagicMock(),
    )


def _make_pet_service(pet_id, events):
    pet_repository = MagicMock()
    pet_repository.get_by_id.return_value = Pet(
        id=pet_id, user_id=_uuid(), name="Caçolin"
    )
    pet_health_event_repository = MagicMock()
    pet_health_event_repository.get_all_by_pet_id.return_value = events
    return PetAppService(
        pet_service=MagicMock(),
        pet_repository=pet_repository,
        pet_health_event_repository=pet_health_event_repository,
        user_repository=MagicMock(),
    )


class TestCivilDatesAreNeverConverted:
    def test_maintenance_record__performed_at_is_echoed_verbatim(self):
        # ISO-8601 civil date, byte-for-byte what was stored: not the 9th (São
        # Paulo) nor the 11th (Kiritimati).
        vehicle_id = _uuid()
        service = _make_vehicle_service(vehicle_id, [_sample_record(vehicle_id)])
        responses = service.get_maintenance(vehicle_id)
        assert responses[0].performed_at == "2026-07-10"

    def test_pet_health_event__occurred_at_is_echoed_verbatim(self):
        pet_id = _uuid()
        service = _make_pet_service(pet_id, [_sample_event(pet_id)])
        responses = service.get_health_events(pet_id)
        assert responses[0].occurred_at == "2026-07-10"


class TestDatetimesStayUtc:
    def test_auto_map__preserves_the_utc_offset(self):
        record = _sample_record(_uuid())
        mapped = auto_map(record, _DatetimeCarryingResponse)
        assert mapped.when_created.tzinfo is not None
        assert mapped.when_created.utcoffset() == timezone.utc.utcoffset(None)
        assert mapped.when_created.isoformat().endswith("+00:00")

    def test_auto_map__never_shifts_the_instant_to_a_local_zone(self):
        record = _sample_record(_uuid())
        mapped = auto_map(record, _DatetimeCarryingResponse)
        assert mapped.when_created.hour == 1  # not 22 (São Paulo)


class TestRestLayerHasNoTimezoneDependency:
    def test_vehicle_app_service__takes_no_settings_or_timezone(self):
        # Structural guard: if a timezone ever reaches the REST app services, the
        # decision of §3.6 has been reversed by accident.
        parameters = VehicleAppService.__init__.__code__.co_varnames
        assert not any("timezone" in name for name in parameters)
        assert not any("settings" in name for name in parameters)

    def test_pet_app_service__takes_no_settings_or_timezone(self):
        parameters = PetAppService.__init__.__code__.co_varnames
        assert not any("timezone" in name for name in parameters)
        assert not any("settings" in name for name in parameters)


class TestEntitiesRemainTimezoneAware:
    def test_pet_birth_date_is_a_civil_date(self):
        pet = Pet(id=_uuid(), user_id=_uuid(), name="Caçolin", birth_date=date(2020, 1, 5))
        assert isinstance(pet.birth_date, date) and not isinstance(
            pet.birth_date, datetime
        )

    def test_vehicle_when_created_default_is_utc_aware(self):
        vehicle = Vehicle(id=_uuid(), user_id=_uuid(), name="Outlander")
        assert vehicle.when_created.tzinfo is not None
