from abc import ABC, abstractmethod
from typing import List

from domain.commands import LightTurnOn
from domain.entities import SmartHomeLight


class SmartHomeLightRepository(ABC):
    """
    Interface for Smart Home Lights integration
    """

    @abstractmethod
    async def get_state(self, entity_id: str)-> SmartHomeLight:
        """
        Get entity current state.
        """
        pass

    @abstractmethod
    async def turn_on(self, turn_on_command: LightTurnOn)-> dict:
        """
        Turn on light
        """
        pass

    @abstractmethod
    async def turn_off(self, entity_id: str)-> dict:
        """
        Turn off light
        """
        pass

class SmartHomeConfigurationRepository(ABC):
    """
    Interface for Smart Home Configuration Integration
    """

    @abstractmethod
    async def get_all_exposed_entities_ids(self)-> List[str]:
        """
        Get all Smart Home Entities Ids
        """
        pass