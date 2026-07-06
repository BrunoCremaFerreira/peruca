from datetime import date

from domain.validations.base_validation import BaseValidation


_MAX_DESCRIPTION_LENGTH = 500
_MAX_ODOMETER_KM = 2_000_000
_MIN_DATE = date(1950, 1, 1)


class MaintenanceRecordValidator(BaseValidation):
    """
    Maintenance Record Validation Class
    """

    def __init__(self):
        super().__init__()

    def validate_id(self, id: str):
        if not id:
            self.errors.append("The 'Id' is empty")
        elif not super().is_valid_uuid4(id):
            self.errors.append("The 'Id' is not a valid uuid4")
        return self

    def validate_vehicle_id(self, vehicle_id: str):
        if not vehicle_id:
            self.errors.append("The 'vehicle_id' is empty")
        elif not super().is_valid_uuid4(vehicle_id):
            self.errors.append("The 'vehicle_id' is not a valid uuid4")
        return self

    def validate_description(self, description: str):
        if not description or not description.strip():
            self.errors.append("The 'description' is empty")
        elif len(description) > _MAX_DESCRIPTION_LENGTH:
            self.errors.append(
                f"The 'description' must be {_MAX_DESCRIPTION_LENGTH} characters or fewer"
            )
        return self

    def validate_performed_at(self, performed_at):
        if performed_at is None:
            self.errors.append("The 'performed_at' is empty")
        elif not isinstance(performed_at, date):
            self.errors.append("The 'performed_at' must be a date")
        elif performed_at > date.today():
            self.errors.append("The 'performed_at' cannot be in the future")
        elif performed_at < _MIN_DATE:
            self.errors.append("The 'performed_at' is too far in the past")
        return self

    def validate_odometer_km(self, odometer_km):
        if odometer_km is None:
            return self
        if not isinstance(odometer_km, int) or isinstance(odometer_km, bool):
            self.errors.append("The 'odometer_km' must be an integer")
        elif odometer_km <= 0:
            self.errors.append(f"Invalid odometer_km: {odometer_km}")
        elif odometer_km > _MAX_ODOMETER_KM:
            self.errors.append(f"odometer_km above the plausible ceiling: {odometer_km}")
        return self
