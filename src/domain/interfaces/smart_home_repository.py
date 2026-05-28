from abc import ABC, abstractmethod
from typing import List

from domain.commands import (
    ClimateSetHvacMode,
    ClimateSetTemperature,
    ClimateTurnOff,
    ClimateTurnOn,
    LightTurnOn,
)
from domain.entities import (
    ExposedEntity,
    SmartHomeArea,
    SmartHomeClimate,
    SmartHomeLight,
    SensorReading,
    SmartHomeCamera,
    SmartHomeCameraSnapshot,
)


class SmartHomeLightRepository(ABC):
    """
    Interface for Smart Home Lights integration
    """

    @abstractmethod
    async def get_state(self, entity_id: str) -> SmartHomeLight:
        """
        Get entity current state.
        """
        pass

    @abstractmethod
    async def get_all_states(self) -> List[SmartHomeLight]:
        """
        Get the current state of every light exposed by the smart home in a
        single round-trip.
        """
        pass

    @abstractmethod
    async def turn_on(self, turn_on_command: LightTurnOn) -> dict:
        """
        Turn on light
        """
        pass

    @abstractmethod
    async def turn_off(self, entity_id: str) -> dict:
        """
        Turn off light
        """
        pass


class SmartHomeConfigurationRepository(ABC):
    """
    Interface for Smart Home Configuration Integration
    """

    @abstractmethod
    async def get_all_exposed_entities_ids(self) -> List[str]:
        """
        Get all Smart Home Entities Ids
        """
        pass

    @abstractmethod
    async def get_aliases_by_entity_id(self, entity_id: str) -> List[str]:
        """
        Get entity aliases
        """
        pass

    @abstractmethod
    async def get_all_areas(self) -> List[SmartHomeArea]:
        """
        Get every area registered in the smart home.
        """
        pass

    @abstractmethod
    async def get_exposed_entities(self) -> List[ExposedEntity]:
        """
        Get every exposed entity together with its area_id (denormalized).
        """
        pass


class SmartHomeClimateRepository(ABC):
    """
    Interface for Smart Home Climate integration
    """

    @abstractmethod
    async def get_state(self, entity_id: str) -> SmartHomeClimate:
        pass

    @abstractmethod
    async def set_temperature(self, command: ClimateSetTemperature) -> dict:
        pass

    @abstractmethod
    async def set_hvac_mode(self, command: ClimateSetHvacMode) -> dict:
        pass

    @abstractmethod
    async def turn_on(self, command: ClimateTurnOn) -> dict:
        pass

    @abstractmethod
    async def turn_off(self, command: ClimateTurnOff) -> dict:
        pass


class SmartHomeSensorRepository(ABC):
    """
    Interface for Smart Home Sensor integration
    """

    @abstractmethod
    async def get_state(self, entity_id: str) -> SensorReading:
        pass

    @abstractmethod
    async def get_history(self, entity_id: str, hours_back: int) -> List[SensorReading]:
        pass


class SmartHomeCameraRepository(ABC):
    """
    Interface for Smart Home Camera integration
    """

    @abstractmethod
    async def get_state(self, entity_id: str) -> SmartHomeCamera:
        pass

    @abstractmethod
    async def get_snapshot(self, entity_id: str) -> SmartHomeCameraSnapshot:
        pass
