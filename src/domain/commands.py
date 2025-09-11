from dataclasses import dataclass
from typing import Optional, Tuple

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


# =====================================
# Shopping List
# =====================================
@dataclass
class ShoppingListItemAdd:
    name : str = ""
    quantity : float = 1

@dataclass
class ShoppingListItemUpdate:
    id: str = ""
    name : str = ""
    quantity : float = 1


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