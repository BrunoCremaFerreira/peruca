"""
SmartHomeService area-related method unit tests.

These tests are written BEFORE the implementation exists (TDD/RED phase).
They cover the new behaviour described in the feature plan:

  - list_lights_grouped_by_area() -> Dict[area_label, List[SmartHomeLight]]
  - turn_on_by_area(area_alias)   /  turn_on_by_area(area_alias_list)
  - turn_off_by_area(area_alias)  /  turn_off_by_area(area_alias_list)
  - turn_on_all_house()
  - turn_off_all_house()
  - find_entity_ids_by_area(area_alias, entity_prefix='light.')
  - update_entity_aliases() regression: must also populate SmartHomeArea
    via the new repository.

Mocks follow the conventions used in test_smart_home_service.py.

Constructor change handled in this file:
  SmartHomeService gains a `smart_home_area_repository` (SmartHomeAreaRepository)
  dependency. _make_service() below builds the service with all required
  repositories plus the new area_repository as MagicMock.

  IMPORTANT: existing test_smart_home_service.py keeps working only if
  smart_home_area_repository is OPTIONAL (default None). Otherwise its
  _make_service() helper must be updated by the programmer in green phase.
  This file therefore always passes the new dependency explicitly.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, call
import pytest

from domain.entities import (
    SmartHomeEntityAlias,
    SmartHomeLight,
)
from domain.services.smart_home_service import SmartHomeService

try:
    from domain.entities import SmartHomeArea

    _AREA_ENTITY_AVAILABLE = True
except ImportError:
    SmartHomeArea = None  # type: ignore[assignment,misc]
    _AREA_ENTITY_AVAILABLE = False

try:
    from domain.exceptions import ValidationError, NofFoundValidationError
except ImportError:  # pragma: no cover
    ValidationError = Exception  # type: ignore[assignment,misc]
    NofFoundValidationError = Exception  # type: ignore[assignment,misc]


_SKIP_IF_AREA_NOT_IMPLEMENTED = pytest.mark.skipif(
    not _AREA_ENTITY_AVAILABLE,
    reason="SmartHomeArea entity not implemented yet (TDD/RED phase)",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(
    exposed_entities=None,
    areas=None,
    aliases=None,
    lights_states=None,
):
    """
    Build a SmartHomeService with controllable mocked repositories, including
    the new SmartHomeAreaRepository.

    Args:
      exposed_entities: list of dicts/objects to be returned by
                        config_repo.get_exposed_entities().
      areas: list of SmartHomeArea returned by config_repo.get_all_areas().
      aliases: list of SmartHomeEntityAlias returned by alias_repo.get_all().
      lights_states: list of SmartHomeLight returned by light_repo.get_all_states().

    Returns:
      tuple (service, light_repo, config_repo, alias_repo, climate_repo,
             area_repo)
    """
    light_repo = AsyncMock()
    config_repo = AsyncMock()
    alias_repo = MagicMock()
    climate_repo = AsyncMock()
    area_repo = MagicMock()

    # Defaults that mimic the existing _make_service() in test_smart_home_service.py
    config_repo.get_all_exposed_entities_ids.return_value = []
    config_repo.get_all_areas.return_value = areas if areas is not None else []
    config_repo.get_exposed_entities.return_value = (
        exposed_entities if exposed_entities is not None else []
    )
    alias_repo.get_all.return_value = aliases if aliases is not None else []
    area_repo.get_all.return_value = areas if areas is not None else []
    light_repo.get_all_states.return_value = (
        lights_states if lights_states is not None else []
    )

    service = SmartHomeService(
        smart_home_light_repository=light_repo,
        smart_home_configuration_repository=config_repo,
        smart_home_entity_alias_repository=alias_repo,
        smart_home_climate_repository=climate_repo,
        smart_home_area_repository=area_repo,
    )
    return service, light_repo, config_repo, alias_repo, climate_repo, area_repo


def _sample_area(area_id: str, name: str):
    return SmartHomeArea(area_id=area_id, name=name)


def _sample_light(
    entity_id: str,
    area_id: str = None,
    friendly_name: str = None,
    is_on: bool = False,
    is_available: bool = True,
):
    return SmartHomeLight(
        entity_id=entity_id,
        area_id=area_id,
        friendly_name=friendly_name,
        is_on=is_on,
        is_available=is_available,
    )


def _sample_alias(
    entity_id: str, alias: str, area_id: str = None
) -> SmartHomeEntityAlias:
    return SmartHomeEntityAlias(
        id=str(uuid.uuid4()),
        entity_id=entity_id,
        alias=alias,
        area_id=area_id,
    )


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ===========================================================================
# TestListLightsGroupedByArea
# ===========================================================================


@_SKIP_IF_AREA_NOT_IMPLEMENTED
class TestListLightsGroupedByArea:
    def test_list__lights_in_multiple_areas__groups_by_area_name(self):
        """
        Lights with different area_ids must end up in the right group whose
        key is the SmartHomeArea.name (not area_id).
        """
        areas = [
            _sample_area("kitchen", "Cozinha"),
            _sample_area("living_room", "Sala"),
        ]
        lights = [
            _sample_light("light.cozinha_1", area_id="kitchen", is_on=True),
            _sample_light("light.cozinha_2", area_id="kitchen", is_on=False),
            _sample_light("light.sala_1", area_id="living_room", is_on=True),
        ]
        service, *_ = _make_service(areas=areas, lights_states=lights)

        result = _run(service.list_lights_grouped_by_area())

        assert isinstance(result, dict)
        assert set(result.keys()) >= {"Cozinha", "Sala"}, (
            f"Expected groups for 'Cozinha' and 'Sala', got {list(result.keys())!r}"
        )
        assert len(result["Cozinha"]) == 2
        assert len(result["Sala"]) == 1
        cozinha_ids = {l.entity_id for l in result["Cozinha"]}
        assert cozinha_ids == {"light.cozinha_1", "light.cozinha_2"}

    def test_list__light_unavailable__still_present_in_group(self):
        """
        Lights with is_available=False (state='unavailable') must still appear
        in their area group. The graph/prompt layer is responsible for the
        'Offline' label — the service just preserves the entity as-is.
        """
        areas = [_sample_area("kitchen", "Cozinha")]
        lights = [
            _sample_light(
                "light.cozinha_quebrada", area_id="kitchen", is_available=False
            )
        ]
        service, *_ = _make_service(areas=areas, lights_states=lights)

        result = _run(service.list_lights_grouped_by_area())

        assert "Cozinha" in result
        assert len(result["Cozinha"]) == 1
        offline_light = result["Cozinha"][0]
        assert offline_light.is_available is False, (
            "Unavailable lights must be preserved with is_available=False"
        )

    def test_list__light_without_area_id__placed_in_unassigned_group(self):
        """
        Plan checkpoint: a light whose area_id is None must be grouped in
        'Sem cômodo' (without area).
        """
        areas = [_sample_area("kitchen", "Cozinha")]
        lights = [
            _sample_light("light.sem_area", area_id=None),
            _sample_light("light.cozinha_1", area_id="kitchen"),
        ]
        service, *_ = _make_service(areas=areas, lights_states=lights)

        result = _run(service.list_lights_grouped_by_area())

        assert "Sem cômodo" in result, (
            f"Expected 'Sem cômodo' group for area_id=None, "
            f"got keys {list(result.keys())!r}"
        )
        assert any(l.entity_id == "light.sem_area" for l in result["Sem cômodo"])

    def test_list__empty_lights__returns_empty_grouping(self):
        service, *_ = _make_service(areas=[], lights_states=[])

        result = _run(service.list_lights_grouped_by_area())

        assert result == {} or all(len(v) == 0 for v in result.values()), (
            f"Expected an empty grouping when there are no lights, got {result!r}"
        )

    def test_list__area_without_lights__returns_empty_group_no_raise(self):
        """
        Plan checkpoint: an area with no lights must NOT raise. Either the
        group is missing or it appears with an empty list — both are valid.
        """
        areas = [
            _sample_area("kitchen", "Cozinha"),
            _sample_area("garage", "Garagem"),
        ]
        lights = [_sample_light("light.cozinha_1", area_id="kitchen")]
        service, *_ = _make_service(areas=areas, lights_states=lights)

        result = _run(service.list_lights_grouped_by_area())

        # Must not raise — primary assertion. Optional empty group is fine too.
        assert "Cozinha" in result
        if "Garagem" in result:
            assert result["Garagem"] == []

    def test_list__calls_get_all_states_and_get_all_areas(self):
        """
        Service must fetch both light states and areas — exactly one call each.
        """
        areas = [_sample_area("kitchen", "Cozinha")]
        service, light_repo, config_repo, _, _, _ = _make_service(
            areas=areas, lights_states=[]
        )

        _run(service.list_lights_grouped_by_area())

        light_repo.get_all_states.assert_awaited_once()
        config_repo.get_all_areas.assert_awaited_once()


# ===========================================================================
# TestTurnOnByArea
# ===========================================================================


@_SKIP_IF_AREA_NOT_IMPLEMENTED
class TestTurnOnByArea:
    def test_turn_on_by_area__valid_area__calls_turn_on_for_each_light(self):
        """
        For an area with N lights, turn_on must be called N times on the
        light repository — one per resolved entity_id.
        """
        areas = [_sample_area("kitchen", "Cozinha")]
        aliases = [
            _sample_alias("light.cozinha_1", "Luz Central", area_id="kitchen"),
            _sample_alias("light.cozinha_2", "Luz da Pia", area_id="kitchen"),
        ]
        service, light_repo, _, _, _, _ = _make_service(
            areas=areas, aliases=aliases
        )

        _run(service.turn_on_by_area(area_alias="Cozinha"))

        assert light_repo.turn_on.await_count == 2, (
            f"Expected turn_on awaited 2 times, got {light_repo.turn_on.await_count}"
        )

    def test_turn_on_by_area__area_not_found__raises_validation_error(self):
        """
        Plan checkpoint: an unknown area must raise ValidationError
        (NofFoundValidationError is a subclass).
        """
        areas = [_sample_area("kitchen", "Cozinha")]
        service, _, _, _, _, _ = _make_service(areas=areas)

        with pytest.raises(ValidationError):
            _run(service.turn_on_by_area(area_alias="Banheiro"))

    def test_turn_on_by_area__area_without_lights__no_calls_made(self):
        """
        Plan checkpoint: empty area must NOT raise, must NOT call turn_on.
        """
        areas = [_sample_area("kitchen", "Cozinha")]
        # No aliases match kitchen
        service, light_repo, _, _, _, _ = _make_service(areas=areas, aliases=[])

        _run(service.turn_on_by_area(area_alias="Cozinha"))

        light_repo.turn_on.assert_not_awaited()

    def test_turn_on_by_area__case_insensitive_and_accent_insensitive(self):
        """
        Plan checkpoint: 'Cozinha' == 'cozinha' == 'COZINHA' (and accents).
        The match must normalize unicode (NFD strip) and case before comparing
        against SmartHomeArea.name.
        """
        areas = [_sample_area("kitchen", "Cozinha")]
        aliases = [_sample_alias("light.cozinha_1", "Luz Central", area_id="kitchen")]
        service, light_repo, _, _, _, _ = _make_service(
            areas=areas, aliases=aliases
        )

        for variant in ["Cozinha", "cozinha", "COZINHA", "cozínha"]:
            light_repo.turn_on.reset_mock()
            _run(service.turn_on_by_area(area_alias=variant))
            assert light_repo.turn_on.await_count == 1, (
                f"Variant {variant!r} should match 'Cozinha' (case/accent insensitive)"
            )


# ===========================================================================
# TestTurnOffByArea
# ===========================================================================


@_SKIP_IF_AREA_NOT_IMPLEMENTED
class TestTurnOffByArea:
    def test_turn_off_by_area__valid_area__calls_turn_off_for_each_light(self):
        areas = [_sample_area("living_room", "Sala")]
        aliases = [
            _sample_alias("light.sala_1", "Luz Principal", area_id="living_room"),
            _sample_alias("light.sala_2", "Luz Secundária", area_id="living_room"),
        ]
        service, light_repo, _, _, _, _ = _make_service(
            areas=areas, aliases=aliases
        )

        _run(service.turn_off_by_area(area_alias="Sala"))

        assert light_repo.turn_off.await_count == 2

    def test_turn_off_by_area__area_not_found__raises_validation_error(self):
        areas = [_sample_area("kitchen", "Cozinha")]
        service, _, _, _, _, _ = _make_service(areas=areas)

        with pytest.raises(ValidationError):
            _run(service.turn_off_by_area(area_alias="Escritorio"))

    def test_turn_off_by_area__area_without_lights__no_calls(self):
        areas = [_sample_area("kitchen", "Cozinha")]
        service, light_repo, _, _, _, _ = _make_service(areas=areas, aliases=[])

        _run(service.turn_off_by_area(area_alias="Cozinha"))

        light_repo.turn_off.assert_not_awaited()


# ===========================================================================
# TestTurnOnAllHouse
# ===========================================================================


@_SKIP_IF_AREA_NOT_IMPLEMENTED
class TestTurnOnAllHouse:
    def test_turn_on_all__has_lights__turns_on_every_light(self):
        lights = [
            _sample_light("light.cozinha_1", area_id="kitchen"),
            _sample_light("light.sala_1", area_id="living_room"),
            _sample_light("light.quarto_1", area_id="bedroom"),
        ]
        service, light_repo, _, _, _, _ = _make_service(lights_states=lights)

        _run(service.turn_on_all_house())

        assert light_repo.turn_on.await_count == 3, (
            f"Expected 3 turn_on calls, got {light_repo.turn_on.await_count}"
        )

    def test_turn_on_all__empty_house__returns_no_raise(self):
        """
        Plan checkpoint: empty house must complete silently (no raise, zero calls).
        """
        service, light_repo, _, _, _, _ = _make_service(lights_states=[])

        _run(service.turn_on_all_house())

        light_repo.turn_on.assert_not_awaited()

    def test_turn_on_all__partial_failure__continues_other_lights(self):
        """
        Plan checkpoint: a failure on one light must not abort the others —
        the service swallows the per-light exception and keeps going.
        """
        lights = [
            _sample_light("light.cozinha_1", area_id="kitchen"),
            _sample_light("light.sala_1", area_id="living_room"),
            _sample_light("light.quarto_1", area_id="bedroom"),
        ]
        service, light_repo, _, _, _, _ = _make_service(lights_states=lights)

        # First call fails, others succeed
        light_repo.turn_on.side_effect = [
            RuntimeError("HA timeout"),
            None,
            None,
        ]

        # Must not propagate
        _run(service.turn_on_all_house())

        assert light_repo.turn_on.await_count == 3, (
            f"Expected all 3 attempts even after first failure, "
            f"got {light_repo.turn_on.await_count}"
        )


# ===========================================================================
# TestTurnOffAllHouse
# ===========================================================================


@_SKIP_IF_AREA_NOT_IMPLEMENTED
class TestTurnOffAllHouse:
    def test_turn_off_all__has_lights__turns_off_every_light(self):
        lights = [
            _sample_light("light.cozinha_1", area_id="kitchen"),
            _sample_light("light.sala_1", area_id="living_room"),
        ]
        service, light_repo, _, _, _, _ = _make_service(lights_states=lights)

        _run(service.turn_off_all_house())

        assert light_repo.turn_off.await_count == 2

    def test_turn_off_all__empty_house__returns_no_raise(self):
        service, light_repo, _, _, _, _ = _make_service(lights_states=[])

        _run(service.turn_off_all_house())

        light_repo.turn_off.assert_not_awaited()

    def test_turn_off_all__partial_failure__continues_other_lights(self):
        lights = [
            _sample_light("light.cozinha_1", area_id="kitchen"),
            _sample_light("light.sala_1", area_id="living_room"),
        ]
        service, light_repo, _, _, _, _ = _make_service(lights_states=lights)

        light_repo.turn_off.side_effect = [RuntimeError("HA timeout"), None]

        _run(service.turn_off_all_house())

        assert light_repo.turn_off.await_count == 2


# ===========================================================================
# TestFindEntityIdsByArea
# ===========================================================================


@_SKIP_IF_AREA_NOT_IMPLEMENTED
class TestFindEntityIdsByArea:
    """
    find_entity_ids_by_area(area_alias, entity_prefix='light.') resolves an
    area's human name into the list of entity_ids belonging to it.

    Algorithm constraints (from the plan):
      - Deterministic resolution in Python (no LLM call).
      - Case-insensitive + accent-insensitive lookup against SmartHomeArea.name.
      - Returns entity_ids from SmartHomeEntityAlias filtered by area_id and
        by entity_prefix.
      - Unknown area raises ValidationError.
    """

    def test_find__valid_area__returns_matching_entity_ids(self):
        areas = [_sample_area("kitchen", "Cozinha")]
        aliases = [
            _sample_alias("light.cozinha_1", "Luz Central", area_id="kitchen"),
            _sample_alias("light.cozinha_2", "Luz da Pia", area_id="kitchen"),
            _sample_alias("light.sala_1", "Luz Principal", area_id="living_room"),
        ]
        service, *_ = _make_service(areas=areas, aliases=aliases)

        result = service.find_entity_ids_by_area(
            area_alias="Cozinha", entity_prefix="light."
        )

        assert sorted(result) == ["light.cozinha_1", "light.cozinha_2"], (
            f"Expected only kitchen lights, got {result!r}"
        )

    def test_find__case_insensitive(self):
        areas = [_sample_area("kitchen", "Cozinha")]
        aliases = [_sample_alias("light.cozinha_1", "Luz", area_id="kitchen")]
        service, *_ = _make_service(areas=areas, aliases=aliases)

        for variant in ["Cozinha", "cozinha", "COZINHA"]:
            result = service.find_entity_ids_by_area(
                area_alias=variant, entity_prefix="light."
            )
            assert result == ["light.cozinha_1"], (
                f"Variant {variant!r} should match 'Cozinha'"
            )

    def test_find__accent_insensitive(self):
        """Plan checkpoint: 'Cozinha' == 'cozínha' via NFD normalization."""
        areas = [_sample_area("kitchen", "Cozinha")]
        aliases = [_sample_alias("light.cozinha_1", "Luz", area_id="kitchen")]
        service, *_ = _make_service(areas=areas, aliases=aliases)

        result = service.find_entity_ids_by_area(
            area_alias="cozínha", entity_prefix="light."
        )

        assert result == ["light.cozinha_1"]

    def test_find__area_not_found__raises_validation_error(self):
        areas = [_sample_area("kitchen", "Cozinha")]
        service, *_ = _make_service(areas=areas)

        with pytest.raises(ValidationError):
            service.find_entity_ids_by_area(
                area_alias="LugarInexistente", entity_prefix="light."
            )

    def test_find__entity_prefix_filter__excludes_non_matching_entities(self):
        """
        Even if the area contains other entities (e.g. switches), the
        entity_prefix filter must keep only those matching the prefix.
        """
        areas = [_sample_area("kitchen", "Cozinha")]
        aliases = [
            _sample_alias("light.cozinha_1", "Luz", area_id="kitchen"),
            _sample_alias("switch.tomada_1", "Tomada", area_id="kitchen"),
            _sample_alias("climate.cozinha_ar", "Ar", area_id="kitchen"),
        ]
        service, *_ = _make_service(areas=areas, aliases=aliases)

        result = service.find_entity_ids_by_area(
            area_alias="Cozinha", entity_prefix="light."
        )

        assert result == ["light.cozinha_1"], (
            f"Expected only light.* entities, got {result!r}"
        )

    def test_find__no_aliases_for_area__returns_empty_list(self):
        """An area exists but has no aliases: returns []. Must NOT raise."""
        areas = [_sample_area("garage", "Garagem")]
        service, *_ = _make_service(areas=areas, aliases=[])

        result = service.find_entity_ids_by_area(
            area_alias="Garagem", entity_prefix="light."
        )

        assert result == []


# ===========================================================================
# TestUpdateEntityAliasesPopulatesAreas (regression for plan decision #6)
# ===========================================================================


@_SKIP_IF_AREA_NOT_IMPLEMENTED
class TestUpdateEntityAliasesPopulatesAreas:
    """
    Plan decision #6 & checklist item 'update_entity_aliases agora também
    popula SmartHomeArea': the existing update_entity_aliases() method must,
    after the change, ALSO fetch areas via config_repo.get_all_areas() and
    persist them via area_repo (delete_all + add).
    """

    def test_update__fetches_all_areas_from_configuration_repo(self):
        areas = [
            _sample_area("kitchen", "Cozinha"),
            _sample_area("living_room", "Sala"),
        ]
        service, _, config_repo, _, _, _ = _make_service(areas=areas)

        _run(service.update_entity_aliases())

        config_repo.get_all_areas.assert_awaited_once()

    def test_update__persists_each_area_in_area_repository(self):
        areas = [
            _sample_area("kitchen", "Cozinha"),
            _sample_area("living_room", "Sala"),
        ]
        service, _, _, _, _, area_repo = _make_service(areas=areas)

        _run(service.update_entity_aliases())

        assert area_repo.add.call_count == 2, (
            f"Expected 2 area_repo.add() calls, got {area_repo.add.call_count}"
        )

    def test_update__clears_existing_areas_before_adding_new_ones(self):
        """delete_all() must be called before any add() — mirrors the alias flow."""
        areas = [_sample_area("kitchen", "Cozinha")]
        service, _, _, _, _, area_repo = _make_service(areas=areas)

        call_order = []
        area_repo.delete_all.side_effect = lambda: call_order.append("delete_all")
        area_repo.add.side_effect = lambda *a, **kw: call_order.append("add")

        _run(service.update_entity_aliases())

        assert call_order[0] == "delete_all", (
            f"delete_all must precede add, call_order={call_order!r}"
        )
        assert "add" in call_order
