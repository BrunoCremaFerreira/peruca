from typing import List
import uuid
from domain.commands import LightTurnOn, ClimateSetTemperature, ClimateSetHvacMode, ClimateTurnOn, ClimateTurnOff
from domain.entities import SmartHomeEntityAlias, SmartHomeClimate
from domain.interfaces.data_repository import SmartHomeEntityAliasRepository
from domain.interfaces.smart_home_repository import SmartHomeConfigurationRepository, SmartHomeLightRepository, SmartHomeClimateRepository


class SmartHomeService:
    """
    Smart Home Service
    """

    def __init__(self,
                 smart_home_light_repository: SmartHomeLightRepository,
                 smart_home_configuration_repository: SmartHomeConfigurationRepository,
                 smart_home_entity_alias_repository: SmartHomeEntityAliasRepository,
                 smart_home_climate_repository: SmartHomeClimateRepository):
        self.smart_home_light_repository = smart_home_light_repository
        self.smart_home_configuration_repository = smart_home_configuration_repository
        self.smart_home_entity_alias_repository = smart_home_entity_alias_repository
        self.smart_home_climate_repository = smart_home_climate_repository

    async def update_entity_aliases(self) -> None:
        """
        Update all entities aliases
        """
        try:
            # Get all entity ids exposed to Virtual Asistant
            exposed_entities_ids = \
                await self.smart_home_configuration_repository.get_all_exposed_entities_ids()

            entity_alias_to_add: List[SmartHomeEntityAlias] = []

            # For each entity, get all aliases attached to it
            for entity_id in exposed_entities_ids:
                try:
                    aliases = await self.smart_home_configuration_repository \
                        .get_aliases_by_entity_id(entity_id=entity_id)

                    if not aliases:
                        continue

                    for alias in aliases:
                        entity_alias_item = SmartHomeEntityAlias(
                            id=str(uuid.uuid4()),
                            entity_id=entity_id,
                            alias=alias)
                        entity_alias_to_add.append(entity_alias_item)
                except:
                    # Ignore entity if exception was raised
                    continue

            # Updating all Entity x Aliases on the database
            print(f"[smart_home_service]: Removing all Entity X Alias")
            self.smart_home_entity_alias_repository.delete_all()
            for item in entity_alias_to_add:
                print(f"[smart_home_service]: Adding alias for entity '{item.entity_id}' => '{item.alias}'")
                self.smart_home_entity_alias_repository.add(entity_alias=item)
        finally:
            await self.smart_home_configuration_repository.close()

    async def light_turn_on(self, turn_on_command: LightTurnOn) -> dict:
        await self.smart_home_light_repository.turn_on(turn_on_command=turn_on_command)

    async def light_turn_off(self, entity_id: str) -> dict:
        await self.smart_home_light_repository.turn_off(entity_id=entity_id)

    async def climate_turn_on(self, command: ClimateTurnOn) -> dict:
        return await self.smart_home_climate_repository.turn_on(command=command)

    async def climate_turn_off(self, command: ClimateTurnOff) -> dict:
        return await self.smart_home_climate_repository.turn_off(command=command)

    async def climate_set_temperature(self, command: ClimateSetTemperature) -> dict:
        return await self.smart_home_climate_repository.set_temperature(command=command)

    async def climate_set_hvac_mode(self, command: ClimateSetHvacMode) -> dict:
        return await self.smart_home_climate_repository.set_hvac_mode(command=command)

    async def climate_get_state(self, entity_id: str) -> SmartHomeClimate:
        return await self.smart_home_climate_repository.get_state(entity_id=entity_id)