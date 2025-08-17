from typing import List
from domain.entities import SmartHomeEntityAlias
from domain.interfaces.data_repository import SmartHomeEntityAliasRepository
from domain.interfaces.smart_home_repository import SmartHomeLightRepository
from domain.services.smart_home_service import SmartHomeService


class SmartHomeAppService:
    """
    Smart Home App Service
    """

    def __init__(self, 
                 smart_home_light_repository: SmartHomeLightRepository,
                 smart_home_entity_alias_repository: SmartHomeEntityAliasRepository,
                 smart_home_service: SmartHomeService):
        self.smart_home_light_repository = smart_home_light_repository
        self.smart_home_entity_alias_repository = smart_home_entity_alias_repository
        self.smart_home_service = smart_home_service


    # =====================================
    # Queries
    # =====================================

    def get_all_entity_aliases(self) -> List[SmartHomeEntityAlias]:
        self.smart_home_entity_alias_repository.get_all()

    # =====================================
    # Commands
    # =====================================

    async def update_entity_aliases(self) -> None:
        """
        Update all entities aliases
        """

        await self.smart_home_service.update_entity_aliases()