from domain.interfaces.data_repository import SmartHomeEntityAliasRepository
from domain.interfaces.smart_home_repository import SmartHomeLightRepository


class SmartHomeService:
    """
    Smart Home Service
    """

    def __init__(self, 
                 smart_home_light_repository: SmartHomeLightRepository,
                 smart_home_entity_alias_repository: SmartHomeEntityAliasRepository):
        self.smart_home_light_repository = smart_home_light_repository
        self.smart_home_entity_alias_repository = smart_home_entity_alias_repository

    def update_entity_aliases(self) -> None:
        """
        Update all entities aliases
        """
        pass