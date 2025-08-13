from dataclasses import dataclass
from datetime import datetime, timezone
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

# ====================================
# Shopping List Related Classes
# ====================================
@dataclass
class ShoppingListItem(BaseEntity):
    name: str = ""
    quantity: float = 1
    checked: bool = False

# ====================================
# Smart Home Entity Alias
# ====================================
@dataclass
class SmartHomeEntityAlias(BaseEntity):
    entity_id: str = ""
    alias: str = ""

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
    color_mode: Optional['SmartHomeColorMode'] = None
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
    supported_color_modes: List['SmartHomeColorMode'] = None
    xy_color: Optional[Tuple[float, float]] = None