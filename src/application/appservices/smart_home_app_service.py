from domain.interfaces.repository import SmartHomeLightRepository


class SmartHomeAppService:
    """
    Smart Home App Service
    """

    def __init__(self, smart_home_light_repository: SmartHomeLightRepository):
        self.smart_home_light_repository = smart_home_light_repository

    def update_entity_aliases(self) -> None:
        """
        Update all entities aliases
        """
        pass