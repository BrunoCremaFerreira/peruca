from typing import List
from domain.entities import SmartHomeEntityAlias
from domain.interfaces.data_repository import SmartHomeEntityAliasRepository
from domain.interfaces.smart_home_repository import SmartHomeConfigurationRepository, SmartHomeLightRepository


class SmartHomeService:
    """
    Smart Home Service
    """

    def __init__(self, 
                 smart_home_light_repository: SmartHomeLightRepository,
                 smart_home_configuration_repository: SmartHomeConfigurationRepository,
                 smart_home_entity_alias_repository: SmartHomeEntityAliasRepository):
        self.smart_home_light_repository = smart_home_light_repository
        self.smart_home_configuration_repository = smart_home_configuration_repository
        self.smart_home_entity_alias_repository = smart_home_entity_alias_repository

    async def update_entity_aliases(self) -> None:
        """
        Update all entities aliases
        """
        
        # Get all entity ids exposed to Virtual Asistant
        exposed_entities_ids = \
            await self.smart_home_configuration_repository.get_all_exposed_entities_ids()
        
        entity_alias_to_add: List[SmartHomeEntityAlias] = []

        # For each entity, get all aliases attached to it
        for entity_id in exposed_entities_ids:
            try:
                aliases = self.smart_home_configuration_repository \
                    .get_aliases_by_entity_id(entity_id=entity_id)
                
                if not aliases:
                    continue

                for alias in aliases:
                    entity_alias_item = SmartHomeEntityAlias(entity_id=entity_id, alias=alias)
                    entity_alias_to_add.append(entity_alias_item)
            except:
                # Ignore entity if exception was raised
                continue
        
        # Updating all Entity x Aliases on the database
        self.smart_home_entity_alias_repository.delete_all()
        for item in entity_alias_to_add:
            self.smart_home_entity_alias_repository.add(entity_alias=item)
