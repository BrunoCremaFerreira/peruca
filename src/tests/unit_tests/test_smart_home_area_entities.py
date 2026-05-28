"""
SmartHomeArea + SmartHomeLight (area-aware) + SmartHomeEntityAlias (area-aware)
Entity Unit Tests.

These tests are written BEFORE the implementation exists (TDD/RED phase).
They test pure domain entities — if the import fails the test must FAIL (RED),
not skip. This matches the pattern used in test_smart_home_camera_entities.py.

Key design constraints verified:
  1. SmartHomeArea is a BaseEntity-like dataclass with area_id and name (both
     default to empty string), so it can be constructed without arguments.
  2. SmartHomeLight gains three optional fields: area_id, friendly_name,
     is_available. All default to None to preserve construction-time backward
     compatibility (existing tests that build SmartHomeLight without these
     fields must keep working).
  3. SmartHomeEntityAlias gains an optional area_id field that defaults to
     None — denormalized reference to SmartHomeArea.area_id.
"""

import pytest

from domain.entities import (
    SmartHomeArea,
    SmartHomeLight,
    SmartHomeEntityAlias,
)


# ===========================================================================
# Helpers / fixtures
# ===========================================================================


def _sample_area(
    area_id: str = "kitchen", name: str = "Cozinha"
) -> "SmartHomeArea":
    """Return a pre-built SmartHomeArea entity (TDD helper)."""
    return SmartHomeArea(area_id=area_id, name=name)


def _sample_light(
    entity_id: str = "light.sala",
    area_id: str = None,
    friendly_name: str = None,
    is_available: bool = None,
) -> "SmartHomeLight":
    """Return a pre-built SmartHomeLight entity exercising the new fields."""
    return SmartHomeLight(
        entity_id=entity_id,
        area_id=area_id,
        friendly_name=friendly_name,
        is_available=is_available,
    )


# ===========================================================================
# TestSmartHomeAreaEntity
# ===========================================================================


class TestSmartHomeAreaEntity:
    def test_area__defaults__has_empty_id_and_name(self):
        """
        SmartHomeArea must be constructable with no arguments and yield empty
        string defaults for area_id and name (mirrors BaseEntity default
        convention used by User, ShoppingListItem, SmartHomeEntityAlias).
        """
        area = SmartHomeArea()

        assert area.area_id == "", (
            f"Expected area_id='' by default, got {area.area_id!r}"
        )
        assert area.name == "", f"Expected name='' by default, got {area.name!r}"

    def test_area__with_values__assigns_id_and_name(self):
        """SmartHomeArea must store area_id and name exactly as provided."""
        area = SmartHomeArea(area_id="kitchen", name="Cozinha")

        assert area.area_id == "kitchen", (
            f"Expected area_id='kitchen', got {area.area_id!r}"
        )
        assert area.name == "Cozinha", f"Expected name='Cozinha', got {area.name!r}"

    def test_area__with_only_area_id__name_defaults_to_empty(self):
        area = SmartHomeArea(area_id="bedroom")

        assert area.area_id == "bedroom"
        assert area.name == ""

    def test_area__sample_helper__returns_kitchen_by_default(self):
        """_sample_area helper must produce a deterministic kitchen entity."""
        area = _sample_area()

        assert area.area_id == "kitchen"
        assert area.name == "Cozinha"


# ===========================================================================
# TestSmartHomeLightWithAreaFields
# ===========================================================================


class TestSmartHomeLightWithAreaFields:
    def test_light__defaults__area_id_and_friendly_name_are_none(self):
        """
        New optional fields area_id and friendly_name must default to None
        when omitted, preserving backward compatibility with existing
        SmartHomeLight construction calls.
        """
        light = SmartHomeLight(entity_id="light.sala")

        assert light.area_id is None, (
            f"Expected area_id=None by default, got {light.area_id!r}"
        )
        assert light.friendly_name is None, (
            f"Expected friendly_name=None by default, got {light.friendly_name!r}"
        )

    def test_light__is_available_defaults_to_none(self):
        """
        is_available must default to None (unknown) so existing call sites
        that never supplied it keep working — only the new HA mapping code
        will set True/False.
        """
        light = SmartHomeLight(entity_id="light.sala")

        assert light.is_available is None, (
            f"Expected is_available=None by default, got {light.is_available!r}"
        )

    def test_light__with_area_id__stored_correctly(self):
        light = SmartHomeLight(entity_id="light.cozinha_1", area_id="kitchen")

        assert light.area_id == "kitchen", (
            f"Expected area_id='kitchen', got {light.area_id!r}"
        )

    def test_light__with_friendly_name__stored_correctly(self):
        light = SmartHomeLight(
            entity_id="light.cozinha_1", friendly_name="Luz Central da Cozinha"
        )

        assert light.friendly_name == "Luz Central da Cozinha", (
            f"Expected friendly_name='Luz Central da Cozinha', got {light.friendly_name!r}"
        )

    def test_light__unavailable_state__is_available_false(self):
        """
        When the mapping layer detects HA state=='unavailable' it must set
        is_available=False. This test asserts the entity preserves False
        (and does not coerce it to None).
        """
        light = SmartHomeLight(entity_id="light.cozinha_1", is_available=False)

        assert light.is_available is False, (
            f"Expected is_available=False (preserved as bool), got {light.is_available!r}"
        )

    def test_light__is_available_true__stored_correctly(self):
        light = SmartHomeLight(entity_id="light.cozinha_1", is_available=True)

        assert light.is_available is True

    def test_light__all_new_fields_together__all_stored(self):
        light = SmartHomeLight(
            entity_id="light.cozinha_1",
            area_id="kitchen",
            friendly_name="Luz Central",
            is_available=True,
            is_on=False,
        )

        assert light.entity_id == "light.cozinha_1"
        assert light.area_id == "kitchen"
        assert light.friendly_name == "Luz Central"
        assert light.is_available is True
        assert light.is_on is False


# ===========================================================================
# TestSmartHomeEntityAliasWithAreaId
# ===========================================================================


class TestSmartHomeEntityAliasWithAreaId:
    def test_alias__defaults__area_id_is_none(self):
        """
        New optional area_id on SmartHomeEntityAlias must default to None,
        so existing alias rows without area_id continue to work.
        """
        alias = SmartHomeEntityAlias()

        assert alias.area_id is None, (
            f"Expected area_id=None by default, got {alias.area_id!r}"
        )

    def test_alias__with_area_id__stored_correctly(self):
        alias = SmartHomeEntityAlias(
            entity_id="light.cozinha_1", alias="Cozinha", area_id="kitchen"
        )

        assert alias.area_id == "kitchen", (
            f"Expected area_id='kitchen', got {alias.area_id!r}"
        )

    def test_alias__legacy_fields_preserved__entity_id_and_alias_default_empty(self):
        """Backward compatibility: existing fields must keep their defaults."""
        alias = SmartHomeEntityAlias()

        assert alias.entity_id == ""
        assert alias.alias == ""
