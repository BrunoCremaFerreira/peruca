import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import List

from domain.commands import VehicleAdd, VehicleUpdate
from domain.entities import Vehicle
from domain.exceptions import NofFoundValidationError, ValidationError
from domain.interfaces.vehicle_repository import (
    MaintenanceRecordRepository,
    VehicleRepository,
)
from domain.services.text_matching import name_tokens, normalize
from domain.validations.vehicle_validation import VehicleValidator
from infra.utils import auto_map


_FUZZY_THRESHOLD = 0.8
_FUZZY_MIN_LENGTH = 4


def _searchables(vehicle: Vehicle) -> List[str]:
    """Every string a term may legitimately match a vehicle by."""
    return [
        vehicle.name,
        vehicle.brand,
        vehicle.model,
        f"{vehicle.brand} {vehicle.model}".strip(),
    ]


def find_vehicles_by_term(term: str, vehicles: List[Vehicle]) -> List[Vehicle]:
    """
    Resolve a user-typed term against already-loaded vehicles, deterministically
    (no LLM, no repository access). Three layers in priority order; the first
    non-empty layer wins:

      1. exact normalized match on any searchable field — short-circuits so a
         literal name is never treated as ambiguous;
      2. partial — the query tokens are a subset of a field's tokens;
      3. typo — difflib ratio >= threshold, guarded by a minimum length.

    Returns 0, 1 or many; the caller uses the count to act or disambiguate.
    """
    normalized_query = normalize(term)
    if not normalized_query or not vehicles:
        return []

    exact = [
        v
        for v in vehicles
        if any(normalize(s) == normalized_query for s in _searchables(v))
    ]
    if exact:
        return exact

    query_tokens = name_tokens(term)
    if query_tokens:
        partial = [
            v
            for v in vehicles
            if any(query_tokens <= name_tokens(s) for s in _searchables(v))
        ]
        if partial:
            return partial

    if len(normalized_query) >= _FUZZY_MIN_LENGTH:
        fuzzy = [
            v
            for v in vehicles
            if any(
                SequenceMatcher(None, normalized_query, normalize(s)).ratio()
                >= _FUZZY_THRESHOLD
                for s in _searchables(v)
            )
        ]
        if fuzzy:
            return fuzzy

    return []


class VehicleService:
    """
    Vehicle CRUD (REST-side), per-user name uniqueness and cascade delete.
    """

    def __init__(
        self,
        vehicle_repository: VehicleRepository,
        maintenance_record_repository: MaintenanceRecordRepository,
    ):
        self.vehicle_repository = vehicle_repository
        self.maintenance_record_repository = maintenance_record_repository

    def add(self, command: VehicleAdd) -> str:
        vehicle = auto_map(command, Vehicle)
        vehicle.id = str(uuid.uuid4())
        vehicle.when_created = datetime.now(timezone.utc)

        VehicleValidator().validate_id(vehicle.id).validate_user_id(
            vehicle.user_id
        ).validate_name(vehicle.name).validate_brand(vehicle.brand).validate_model(
            vehicle.model
        ).validate_year(
            vehicle.year
        ).validate()

        existing = self.vehicle_repository.get_all_by_user_id(vehicle.user_id)
        if any(normalize(v.name) == normalize(vehicle.name) for v in existing):
            raise ValidationError(
                [f"The vehicle '{vehicle.name}' is already registered for this user"]
            )

        self.vehicle_repository.add(vehicle)
        return vehicle.id

    def get_by_id(self, vehicle_id: str):
        return self.vehicle_repository.get_by_id(vehicle_id)

    def get_all_by_user_id(self, user_id: str) -> List[Vehicle]:
        return self.vehicle_repository.get_all_by_user_id(user_id)

    def update(self, command: VehicleUpdate) -> None:
        vehicle = auto_map(command, Vehicle)

        VehicleValidator().validate_id(vehicle.id).validate_user_id(
            vehicle.user_id
        ).validate_name(vehicle.name).validate_brand(vehicle.brand).validate_model(
            vehicle.model
        ).validate_year(
            vehicle.year
        ).validate()

        db_vehicle = self.vehicle_repository.get_by_id(vehicle.id)
        if not db_vehicle or db_vehicle.user_id != vehicle.user_id:
            raise NofFoundValidationError("Vehicle", "id", vehicle.id)

        self.vehicle_repository.update(vehicle)

    def delete(self, vehicle_id: str, user_id: str) -> None:
        VehicleValidator().validate_id(vehicle_id).validate()

        db_vehicle = self.vehicle_repository.get_by_id(vehicle_id)
        if not db_vehicle or db_vehicle.user_id != user_id:
            raise NofFoundValidationError("Vehicle", "id", vehicle_id)

        # Cascade: children first, so a mid-operation failure never leaves an
        # orphan maintenance record (§9.4 invariant).
        self.maintenance_record_repository.delete_all_by_vehicle_id(vehicle_id)
        self.vehicle_repository.delete(vehicle_id)

    def find_vehicles_by_term(
        self, term: str, vehicles: List[Vehicle]
    ) -> List[Vehicle]:
        return find_vehicles_by_term(term, vehicles)
