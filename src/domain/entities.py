from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import List, Optional, Tuple


# ====================================
# Base entities Classes
# ====================================
@dataclass
class BaseEntity:
    id: str = ""
    when_created: datetime = datetime.now(timezone.utc)
    when_updated: Optional[datetime] = None
    when_deleted: Optional[datetime] = None


# ====================================
# User Related Classes
# ====================================


@dataclass
class User(BaseEntity):
    external_id: str = ""
    name: str = ""
    summary: str = ""


@dataclass
class UserMemory(BaseEntity):
    user_id: str = ""
    content: str = ""


# ====================================
# Shopping List Related Classes
# ====================================
@dataclass
class ShoppingListItem(BaseEntity):
    name: str = ""
    quantity: float = 1
    checked: bool = False


# ====================================
# Disambiguation Related Classes
# ====================================
@dataclass
class DisambiguationCandidate:
    """A single item a pending disambiguation question refers to."""

    id: str = ""
    name: str = ""


@dataclass
class PendingDisambiguation:
    """
    A disambiguation question awaiting the user's next reply. Persisted between
    turns so the follow-up ("a primeira", "carne de panela", "cancelar") can be
    applied to the operation that raised it. The TTL is embedded in the payload
    (expires_at, epoch seconds) so it survives both Redis and in-memory stores.
    """

    operation: str = ""  # "delete" | "check" | "uncheck"
    query: str = ""
    candidates: List["DisambiguationCandidate"] = field(default_factory=list)
    expires_at: float = 0.0  # epoch seconds


# ====================================
# Vehicle Maintenance Related Classes
# ====================================
@dataclass
class Vehicle(BaseEntity):
    user_id: str = ""
    name: str = ""
    brand: str = ""
    model: str = ""
    year: Optional[int] = None


@dataclass
class MaintenanceRecord(BaseEntity):
    vehicle_id: str = ""
    description: str = ""
    performed_at: Optional[date] = None
    odometer_km: Optional[int] = None


@dataclass
class PendingFlow:
    """
    A multi-turn flow awaiting the user's next reply, persisted between turns
    (JSON payload with an embedded TTL, mirroring PendingDisambiguation).
    ``flow_domain`` discriminates which consumer owns this pending state
    ("maintenance" | "pet_health"), so a single pending slot can dispatch by
    domain instead of relying on the order of sequential checks. ``slots`` holds
    the data gathered so far (e.g. description, vehicle_id, performed_at ISO
    string, odometer_km, record_id); ``missing_slots`` is the ordered queue of
    what to ask next (e.g. veículo -> data -> km); ``candidates`` reuses the
    disambiguation candidate shape for a "choose_*" operation.
    """

    operation: str = ""  # "register" | "edit" | "delete_confirm" | "choose_vehicle"
    slots: dict = field(default_factory=dict)
    missing_slots: List[str] = field(default_factory=list)
    candidates: List["DisambiguationCandidate"] = field(default_factory=list)
    expires_at: float = 0.0  # epoch seconds
    flow_domain: str = ""  # "maintenance" | "pet_health"


# Backwards-compat alias: existing imports/tests reference the old name.
PendingMaintenanceFlow = PendingFlow


# ====================================
# Pet Health Related Classes
# ====================================
@dataclass
class Pet(BaseEntity):
    user_id: str = ""
    name: str = ""
    # The first nickname is the primary one. An empty list is valid (the pet is
    # only ever referred to by name).
    nicknames: List[str] = field(default_factory=list)
    birth_date: Optional[date] = None
    sex: str = ""  # "male" | "female" | "unknown" (closed set)
    species: str = ""  # free text: "dog", "cat", "fish", ...
    description: str = ""  # physical/behavioral notes


@dataclass
class PetHealthEvent(BaseEntity):
    pet_id: str = ""
    event_type: str = ""  # closed set: vaccine|dewormer|antiparasitic|medication|vet_visit|other
    description: str = ""  # e.g. "DHPPI", "Leptospirose", "vermifugo Bravecto"
    occurred_at: Optional[date] = None


# ====================================
# Smart Home Entity Alias
# ====================================
@dataclass
class SmartHomeEntityAlias(BaseEntity):
    entity_id: str = ""
    alias: str = ""
    area_id: Optional[str] = None


# ====================================
# Smart Home Area
# ====================================
@dataclass
class SmartHomeArea(BaseEntity):
    area_id: str = ""
    name: str = ""


# ====================================
# Smart Home Exposed Entity (DTO returned by configuration repository)
# ====================================
@dataclass
class ExposedEntity:
    entity_id: str
    area_id: Optional[str] = None


# ====================================
# Graph Related Classes
# ====================================


@dataclass
class GraphInvokeRequest:
    """
    LLM processing request entity
    """

    message: str
    user: User
    memories: list[str] = field(default_factory=list)
    context_hints: dict = field(default_factory=dict)
    # Inbound images as full data URIs ("data:image/jpeg;base64,..."). Only the
    # OnlyTalkGraph consumes them; action graphs ignore them. Default empty keeps
    # every existing construction valid.
    images: list[str] = field(default_factory=list)


# ====================================
# Smart Home Related Classes
# ====================================


class SmartHomeColorMode(Enum):
    """
    Defines the supported color modes for smart lighting devices.

    Attributes:
        UNKNOWN:
            The color mode is not known or not reported by the device.
        ONOFF:
            The light supports only on/off control without brightness or color adjustments.
        BRIGHTNESS:
            The light supports brightness control but no color adjustments.
        COLOR_TEMP:
            The light supports color temperature control (warm to cool white).
        HS:
            The light supports Hue/Saturation color mode.
        RGB:
            The light supports RGB color mode (red, green, blue channels).
        RGBW:
            The light supports RGB + white channel.
        RGBWW:
            The light supports RGB + warm white + cool white channels.
        WHITE:
            The light supports white color only, possibly with adjustable brightness.
        XY:
            The light supports CIE 1931 XY color space.
    """

    UNKNOWN = "UNKNOWN"
    ONOFF = "ONOFF"
    BRIGHTNESS = "BRIGHTNESS"
    COLOR_TEMP = "COLOR_TEMP"
    HS = "HS"
    RGB = "RGB"
    RGBW = "RGBW"
    RGBWW = "RGBWW"
    WHITE = "WHITE"
    XY = "XY"


@dataclass
class SmartHomeLight:
    """
    Representa o estado e parâmetros configuráveis de uma lâmpada inteligente.

    Attributes:
        entity_id:
            Entity id
        brightness (Optional[int]):
            The brightness of this light between 1..255
        color_mode (Optional[SmartHomeColorMode]):
            The color mode of the light. The returned color mode must be present in the supported_color_modes property unless the light is rendering an effect.
        color_temp_kelvin (Optional[int]):
            The CT color value in K. This property will be copied to the light's state attribute when the light's color mode is set to ColorMode.COLOR_TEMP and ignored otherwise.
        effect (Optional[str]):
            The current effect. Should be EFFECT_OFF if the light supports effects and no effect is currently rendered.
        effect_list (List[str]):
            The list of supported effects.
        hs_color (Optional[Tuple[float, float]]):
            The hue and saturation color value (float, float). This property will be copied to the light's state attribute when the light's color mode is set to ColorMode.HS and ignored otherwise.
        is_on (Optional[bool]):
            If the light entity is on or not.
        max_color_temp_kelvin (Optional[int]):
            The coldest color_temp_kelvin that this light supports.
        min_color_temp_kelvin (Optional[int]):
            The warmest color_temp_kelvin that this light supports.
        rgb_color (Optional[Tuple[int, int, int]]):
            The rgb color value (int, int, int). This property will be copied to the light's state attribute when the light's color mode is set to ColorMode.RGB and ignored otherwise.
        rgbw_color (Optional[Tuple[int, int, int, int]]):
            The rgbw color value (int, int, int, int). This property will be copied to the light's state attribute when the light's color mode is set to ColorMode.RGBW and ignored otherwise.
        rgbww_color (Optional[Tuple[int, int, int, int, int]]):
            The rgbww color value (int, int, int, int, int). This property will be copied to the light's state attribute when the light's color mode is set to ColorMode.RGBWW and ignored otherwise.
        supported_color_modes (List[SmartHomeColorMode]):
            Flag supported color modes.
        xy_color (Optional[Tuple[float, float]]):
            The xy color value (float, float). This property will be copied to the light's state attribute when the light's color mode is set to ColorMode.XY and ignored otherwise.
    """

    entity_id: str
    brightness: Optional[int] = None
    color_mode: Optional["SmartHomeColorMode"] = None
    color_temp_kelvin: Optional[int] = None
    effect: Optional[str] = None
    effect_list: List[str] = None
    hs_color: Optional[Tuple[float, float]] = None
    is_on: Optional[bool] = None
    max_color_temp_kelvin: Optional[int] = None
    min_color_temp_kelvin: Optional[int] = None
    rgb_color: Optional[Tuple[int, int, int]] = None
    rgbw_color: Optional[Tuple[int, int, int, int]] = None
    rgbww_color: Optional[Tuple[int, int, int, int, int]] = None
    supported_color_modes: List["SmartHomeColorMode"] = None
    xy_color: Optional[Tuple[float, float]] = None
    area_id: Optional[str] = None
    friendly_name: Optional[str] = None
    is_available: Optional[bool] = None


# Smart Home Climate Related Classes


class SmartHomeHvacMode(Enum):
    COOL = "cool"
    HEAT = "heat"
    AUTO = "auto"
    FAN_ONLY = "fan_only"
    DRY = "dry"
    OFF = "off"


@dataclass
class SmartHomeClimate:
    entity_id: str
    is_on: Optional[bool] = None
    hvac_mode: Optional["SmartHomeHvacMode"] = None
    hvac_modes: Optional[List[str]] = None
    current_temperature: Optional[float] = None
    target_temperature: Optional[float] = None
    fan_mode: Optional[str] = None
    swing_mode: Optional[str] = None


# Smart Home Sensor Related Classes


class SensorType(Enum):
    TEMPERATURE = "temperature"
    DOOR = "door"
    WINDOW = "window"
    MOTION = "motion"
    PRESENCE = "presence"
    HUMIDITY = "humidity"
    SMOKE = "smoke"
    ILLUMINANCE = "illuminance"
    UNKNOWN = "unknown"


@dataclass
class SensorReading:
    entity_id: str
    sensor_type: SensorType
    state: str
    unit: Optional[str] = None
    friendly_name: Optional[str] = None
    last_changed: Optional[datetime] = None


# Smart Home Camera Related Classes


@dataclass
class SmartHomeCamera:
    entity_id: str
    state: str
    friendly_name: Optional[str] = None
    is_available: Optional[bool] = None


@dataclass
class SmartHomeCameraSnapshot:
    entity_id: str
    image_bytes: bytes
    content_type: str = "image/jpeg"


# ====================================
# Music Related Classes
# ====================================


@dataclass
class MusicPlayer:
    player_id: str
    name: str
    state: str
    volume_level: Optional[float] = None
    current_track: Optional[str] = None


@dataclass
class MusicSearchResult:
    media_id: str
    media_type: str
    name: str
    artist: Optional[str] = None
