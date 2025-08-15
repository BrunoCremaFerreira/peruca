from typing import List
from domain.interfaces.smart_home_repository import SmartHomeConfigurationRepository

class HomeAssistantSmartHomeConfigurationRepository(SmartHomeConfigurationRepository):
    """
    Home Assistant Configuration Integration
    """
    
    async def get_all_entities(self)-> List[object]:
        """
        Get all Smart Home Entities
        """
        pass