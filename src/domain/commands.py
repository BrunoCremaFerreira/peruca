from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple


# =====================================
# User
# =====================================
@dataclass
class UserAdd:
    name: str = ""
    external_id: str = ""
    summary: str = ""


@dataclass
class UserUpdate:
    id: str = ""
    external_id: str = ""
    name: str = ""
    summary: str = ""


@dataclass
class UserMemoryAdd:
    user_id: str = ""
    content: str = ""


# =====================================
# Shopping List
# =====================================
@dataclass
class ShoppingListItemAdd:
    name: str = ""
    quantity: float = 1


@dataclass
class ShoppingListItemUpdate:
    id: str = ""
    name: str = ""
    quantity: float = 1


@dataclass
class ShoppingListItemsAddResult:
    """
    Outcome of a batch add: ``added`` carries the items persisted by the call;
    ``duplicates`` carries the EXISTING list item that matched each skipped
    entry (what "already in the list" reports). Structured data only — the
    domain never phrases user-facing text.
    """

    added: List = field(default_factory=list)
    duplicates: List = field(default_factory=list)


# =====================================
# Vehicle Maintenance Commands
# =====================================
@dataclass
class VehicleAdd:
    user_id: str = ""
    name: str = ""
    brand: str = ""
    model: str = ""
    year: Optional[int] = None


@dataclass
class VehicleUpdate:
    id: str = ""
    user_id: str = ""
    name: str = ""
    brand: str = ""
    model: str = ""
    year: Optional[int] = None


@dataclass
class MaintenanceRecordAdd:
    vehicle_id: str = ""
    description: str = ""
    performed_at: Optional[date] = None
    odometer_km: Optional[int] = None


@dataclass
class MaintenanceRecordUpdate:
    id: str = ""
    description: Optional[str] = None
    performed_at: Optional[date] = None
    odometer_km: Optional[int] = None


# =====================================
# Pet Health Commands
# =====================================
@dataclass
class PetAdd:
    user_id: str = ""
    name: str = ""
    nicknames: List[str] = field(default_factory=list)
    birth_date: Optional[date] = None
    sex: str = ""
    species: str = ""
    description: str = ""


@dataclass
class PetUpdate:
    id: str = ""
    user_id: str = ""
    name: str = ""
    nicknames: List[str] = field(default_factory=list)
    birth_date: Optional[date] = None
    sex: str = ""
    species: str = ""
    description: str = ""


@dataclass
class PetHealthEventAdd:
    pet_id: str = ""
    event_type: str = ""
    description: str = ""
    occurred_at: Optional[date] = None


@dataclass
class PetHealthEventUpdate:
    id: str = ""
    event_type: Optional[str] = None
    description: Optional[str] = None
    occurred_at: Optional[date] = None


# =====================================
# Smart Home - Lights Commands
# =====================================
@dataclass
class LightTurnOn:
    """
    Represents the parameters accepted by smart home `light.turn_on` service.

    Attributes:
        entity_id str:
            The entity ID or a comma-separated list of entity IDs to turn on
            (e.g., "light.living_room", "light.kitchen").
        brightness (Optional[int]):
            Brightness level from 0 to 255.
        brightness_pct (Optional[int]):
            Brightness level as a percentage (0–100).
        color_name (Optional[str]):
            A named CSS color in English (e.g., "red", "blue", "green").
        hs_color (Optional[Tuple[float, float]]):
            Hue/Saturation color format (Hue: 0–360, Saturation: 0–100).
        rgb_color (Optional[Tuple[int, int, int]]):
            RGB color format (0–255 per channel).
        xy_color (Optional[Tuple[float, float]]):
            CIE 1931 XY color space coordinates.
        color_temp (Optional[int]):
            Color temperature in mireds (153 ≈ 6500K, 500 ≈ 2000K).
        kelvin (Optional[int]):
            Color temperature in Kelvin (e.g., 2000 for warm white, 6500 for daylight).
        transition (Optional[float]):
            Duration of the transition in seconds when changing state.
        flash (Optional[str]):
            Flash effect ("short" or "long") if supported by the light.
        effect (Optional[str]):
            The effect name to activate (e.g., "colorloop", "random").
        profile (Optional[str]):
            Name of a light profile saved in Home Assistant.
    """

    entity_id: str
    brightness: Optional[int] = None
    brightness_pct: Optional[int] = None
    color_name: Optional[str] = None
    hs_color: Optional[Tuple[float, float]] = None
    rgb_color: Optional[Tuple[int, int, int]] = None
    xy_color: Optional[Tuple[float, float]] = None
    color_temp: Optional[int] = None
    kelvin: Optional[int] = None
    transition: Optional[float] = None
    flash: Optional[str] = None
    effect: Optional[str] = None
    profile: Optional[str] = None


# =====================================
# Smart Home - Climate Commands
# =====================================
@dataclass
class ClimateSetTemperature:
    entity_id: str
    temperature: float


@dataclass
class ClimateSetHvacMode:
    entity_id: str
    hvac_mode: str


@dataclass
class ClimateTurnOn:
    entity_id: str


@dataclass
class ClimateTurnOff:
    entity_id: str


# =====================================
# Smart Home - Sensor Commands
# =====================================
@dataclass
class SensorQueryCurrent:
    sensor_type: str
    location: Optional[str] = None


@dataclass
class SensorQueryHistory:
    sensor_type: str
    location: Optional[str] = None
    hours_back: int = 3
