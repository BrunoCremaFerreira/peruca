import unicodedata
import uuid
from typing import Dict, List, Optional

from domain.commands import (
    ClimateSetHvacMode,
    ClimateSetTemperature,
    ClimateTurnOff,
    ClimateTurnOn,
    LightTurnOn,
)
from domain.entities import (
    SensorReading,
    SmartHomeCamera,
    SmartHomeCameraSnapshot,
    SmartHomeClimate,
    SmartHomeEntityAlias,
    SmartHomeLight,
)
from domain.exceptions import NofFoundValidationError
from domain.interfaces.data_repository import (
    SmartHomeAreaRepository,
    SmartHomeEntityAliasRepository,
)
from domain.interfaces.smart_home_repository import (
    SmartHomeCameraRepository,
    SmartHomeClimateRepository,
    SmartHomeConfigurationRepository,
    SmartHomeLightRepository,
    SmartHomeSensorRepository,
)


_UNASSIGNED_AREA_LABEL = "Sem cômodo"

_ALIAS_STOPWORDS = {"do", "da", "de", "o", "a", "no", "na"}

_CLIMATE_EQUIPMENT_TOKENS = {
    "ar",
    "condicionado",
    "ar-condicionado",
    "climatizador",
    "split",
    "ac",
}


def _normalize(value: Optional[str]) -> str:
    """
    Normalize a string by stripping accents and lowercasing. Used to resolve
    user-provided area names against SmartHomeArea.name in a deterministic,
    case- and accent-insensitive way.
    """
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFD", value)
    stripped = decomposed.encode("ascii", "ignore").decode("ascii")
    return stripped.lower().strip()


class SmartHomeService:
    """
    Smart Home Service
    """

    def __init__(
        self,
        smart_home_light_repository: SmartHomeLightRepository,
        smart_home_configuration_repository: SmartHomeConfigurationRepository,
        smart_home_entity_alias_repository: SmartHomeEntityAliasRepository,
        smart_home_climate_repository: SmartHomeClimateRepository,
        smart_home_sensor_repository: Optional[SmartHomeSensorRepository] = None,
        smart_home_camera_repository: Optional[SmartHomeCameraRepository] = None,
        smart_home_area_repository: Optional[SmartHomeAreaRepository] = None,
    ):
        self.smart_home_light_repository = smart_home_light_repository
        self.smart_home_configuration_repository = smart_home_configuration_repository
        self.smart_home_entity_alias_repository = smart_home_entity_alias_repository
        self.smart_home_climate_repository = smart_home_climate_repository
        self.smart_home_sensor_repository = smart_home_sensor_repository
        self.smart_home_camera_repository = smart_home_camera_repository
        self.smart_home_area_repository = smart_home_area_repository

    async def update_entity_aliases(self) -> None:
        """
        Update all entities aliases. Also refreshes the SmartHomeArea catalog
        when an area repository is configured.
        """
        try:
            # Get all entity ids exposed to Virtual Asistant
            exposed_entities_ids = (
                await self.smart_home_configuration_repository.get_all_exposed_entities_ids()
            )

            entity_alias_to_add: List[SmartHomeEntityAlias] = []

            # For each entity, get all aliases attached to it
            for entity_id in exposed_entities_ids:
                try:
                    aliases = await self.smart_home_configuration_repository.get_aliases_by_entity_id(
                        entity_id=entity_id
                    )

                    aliases = [a for a in aliases if a]
                    if not aliases:
                        continue

                    for alias in aliases:
                        entity_alias_item = SmartHomeEntityAlias(
                            id=str(uuid.uuid4()), entity_id=entity_id, alias=alias
                        )
                        entity_alias_to_add.append(entity_alias_item)
                except:
                    # Ignore entity if exception was raised
                    continue

            # Updating all Entity x Aliases on the database
            print(f"[smart_home_service]: Removing all Entity X Alias")
            self.smart_home_entity_alias_repository.delete_all()
            for item in entity_alias_to_add:
                print(
                    f"[smart_home_service]: Adding alias for entity '{item.entity_id}' => '{item.alias}'"
                )
                self.smart_home_entity_alias_repository.add(entity_alias=item)

            # Refresh the area catalog (if an area repository is configured)
            if self.smart_home_area_repository is not None:
                try:
                    areas = (
                        await self.smart_home_configuration_repository.get_all_areas()
                    )
                except Exception as error:
                    print(f"[smart_home_service]: Failed to fetch areas: {error}")
                    areas = []

                print(f"[smart_home_service]: Removing all SmartHomeArea entries")
                self.smart_home_area_repository.delete_all()
                for area in areas:
                    print(
                        f"[smart_home_service]: Adding area '{area.area_id}' => '{area.name}'"
                    )
                    self.smart_home_area_repository.add(area)
        finally:
            await self.smart_home_configuration_repository.close()

    async def list_lights_grouped_by_area(
        self,
    ) -> Dict[str, List[SmartHomeLight]]:
        """
        List every light grouped by its area human name. Lights whose area_id
        is None (or unknown) are bucketed under the canonical label
        'Sem cômodo'.
        """
        self._require_area_repository("list_lights_grouped_by_area")

        lights = await self.smart_home_light_repository.get_all_states()
        areas = await self.smart_home_configuration_repository.get_all_areas()

        area_id_to_name: Dict[str, str] = {area.area_id: area.name for area in areas}

        grouping: Dict[str, List[SmartHomeLight]] = {}
        for light in lights:
            area_label = area_id_to_name.get(light.area_id) if light.area_id else None
            label = area_label if area_label else _UNASSIGNED_AREA_LABEL
            grouping.setdefault(label, []).append(light)

        return grouping

    async def turn_on_by_area(self, area_alias: str) -> None:
        """
        Turn on every light belonging to the given area.
        Raises NofFoundValidationError when the area cannot be resolved.
        """
        entity_ids = self.find_entity_ids_by_area(
            area_alias=area_alias, entity_prefix="light."
        )
        for entity_id in entity_ids:
            try:
                await self.smart_home_light_repository.turn_on(
                    turn_on_command=LightTurnOn(entity_id=entity_id)
                )
            except Exception as error:
                print(
                    f"[smart_home_service]: turn_on_by_area failed for '{entity_id}': {error}"
                )
                continue

    async def turn_off_by_area(self, area_alias: str) -> None:
        """
        Turn off every light belonging to the given area.
        Raises NofFoundValidationError when the area cannot be resolved.
        """
        entity_ids = self.find_entity_ids_by_area(
            area_alias=area_alias, entity_prefix="light."
        )
        for entity_id in entity_ids:
            try:
                await self.smart_home_light_repository.turn_off(entity_id=entity_id)
            except Exception as error:
                print(
                    f"[smart_home_service]: turn_off_by_area failed for '{entity_id}': {error}"
                )
                continue

    async def turn_on_all_house(self) -> None:
        """
        Turn on every light in the house. Partial failures are logged but do
        not abort the loop.
        """
        lights = await self.smart_home_light_repository.get_all_states()
        for light in lights:
            try:
                await self.smart_home_light_repository.turn_on(
                    turn_on_command=LightTurnOn(entity_id=light.entity_id)
                )
            except Exception as error:
                print(
                    f"[smart_home_service]: turn_on_all_house failed for '{light.entity_id}': {error}"
                )
                continue

    async def turn_off_all_house(self) -> None:
        """
        Turn off every light in the house. Partial failures are logged but do
        not abort the loop.
        """
        lights = await self.smart_home_light_repository.get_all_states()
        for light in lights:
            try:
                await self.smart_home_light_repository.turn_off(
                    entity_id=light.entity_id
                )
            except Exception as error:
                print(
                    f"[smart_home_service]: turn_off_all_house failed for '{light.entity_id}': {error}"
                )
                continue

    def find_entity_ids_by_area(
        self, area_alias: str, entity_prefix: str
    ) -> List[str]:
        """
        Resolve a user-provided area name into the list of entity_ids that
        belong to that area and match the given entity prefix.

        Resolution is deterministic (no LLM): the area alias is compared to
        SmartHomeArea.name after NFD-stripping accents and lowercasing.
        """
        self._require_area_repository("find_entity_ids_by_area")

        normalized_alias = _normalize(area_alias)
        areas = self.smart_home_area_repository.get_all()
        matching_area = next(
            (area for area in areas if _normalize(area.name) == normalized_alias),
            None,
        )
        if matching_area is None:
            raise NofFoundValidationError(
                entity_name="SmartHomeArea", key_name="name", value=area_alias
            )

        aliases = self.smart_home_entity_alias_repository.get_all(
            entity_id_starts_with=entity_prefix
        )

        seen: set = set()
        entity_ids: List[str] = []
        for alias in aliases:
            if alias.area_id != matching_area.area_id:
                continue
            if not alias.entity_id.startswith(entity_prefix):
                continue
            if alias.entity_id in seen:
                continue
            seen.add(alias.entity_id)
            entity_ids.append(alias.entity_id)
        return entity_ids

    def find_entity_ids_by_alias(
        self, query_alias: str, available_entities: dict
    ) -> List[str]:
        """
        Resolve a single device query against an {alias: entity_id} catalog
        deterministically, without any LLM call or repository access.

        Matching is by location tokens: equipment synonyms (ar, climatizador,
        split, ...) and stopwords (do, da, de, ...) are stripped from both the
        query and each alias, then the remaining location tokens are compared
        by subset containment. Returns [entity_id] on a single match, [] on no
        match, and [] when the query is ambiguous (matches more than one alias).
        """
        if not available_entities:
            return []

        query_tokens = self._location_tokens(query_alias)
        if not query_tokens:
            return []

        matches: List[str] = []
        for alias, entity_id in available_entities.items():
            alias_tokens = self._location_tokens(alias)
            if not alias_tokens:
                continue
            if query_tokens <= alias_tokens or alias_tokens <= query_tokens:
                matches.append(entity_id)

        if len(matches) == 1:
            return matches
        return []

    @staticmethod
    def _location_tokens(value: str) -> set:
        """
        Break a device alias/query into its location tokens: normalize accents
        and case, split on whitespace and hyphens, then drop stopwords and
        climate equipment synonyms.
        """
        normalized = _normalize(value).replace("-", " ")
        tokens = normalized.split()
        return {
            token
            for token in tokens
            if token
            and token not in _ALIAS_STOPWORDS
            and token not in _CLIMATE_EQUIPMENT_TOKENS
        }

    def _require_area_repository(self, method_name: str) -> None:
        if self.smart_home_area_repository is None:
            raise RuntimeError(
                f"SmartHomeService.{method_name}() requires an "
                f"area_repository — pass smart_home_area_repository in the "
                f"constructor."
            )

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

    async def sensor_get_state(self, entity_id: str) -> SensorReading:
        return await self.smart_home_sensor_repository.get_state(entity_id)

    async def sensor_get_history(
        self, entity_id: str, hours_back: int
    ) -> List[SensorReading]:
        return await self.smart_home_sensor_repository.get_history(
            entity_id, hours_back
        )

    async def camera_get_state(self, entity_id: str) -> SmartHomeCamera:
        return await self.smart_home_camera_repository.get_state(entity_id)

    async def camera_get_snapshot(self, entity_id: str) -> SmartHomeCameraSnapshot:
        return await self.smart_home_camera_repository.get_snapshot(entity_id)
