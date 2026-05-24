import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, call
import pytest

from domain.commands import LightTurnOn
from domain.entities import SmartHomeEntityAlias
from domain.services.smart_home_service import SmartHomeService


"""
SmartHomeService Unit Tests
"""


def _make_service(exposed_ids=None, aliases_map=None):
    """
    Helper that builds a SmartHomeService with controllable mocked repositories.

    exposed_ids: list of entity ids returned by get_all_exposed_entities_ids
    aliases_map: dict {entity_id: [alias, ...]} for get_aliases_by_entity_id
    """
    light_repo = AsyncMock()
    config_repo = AsyncMock()
    alias_repo = MagicMock()

    config_repo.get_all_exposed_entities_ids.return_value = exposed_ids or []

    async def _aliases(entity_id):
        if aliases_map:
            return aliases_map.get(entity_id, [])
        return []

    config_repo.get_aliases_by_entity_id.side_effect = _aliases

    service = SmartHomeService(
        smart_home_light_repository=light_repo,
        smart_home_configuration_repository=config_repo,
        smart_home_entity_alias_repository=alias_repo,
    )
    return service, light_repo, config_repo, alias_repo


class TestSmartHomeServiceUpdateEntityAliases:

    def test_no_exposed_entities_clears_existing_aliases(self):
        # Arrange
        service, _, _, alias_repo = _make_service(exposed_ids=[])
        # Act
        asyncio.get_event_loop().run_until_complete(service.update_entity_aliases())
        # Assert
        alias_repo.delete_all.assert_called_once()
        alias_repo.add.assert_not_called()

    def test_aliases_are_persisted_for_each_entity(self):
        # Arrange
        aliases_map = {
            "light.living_room": ["Sala", "Sala de Estar"],
            "light.bedroom": ["Quarto"],
        }
        service, _, _, alias_repo = _make_service(
            exposed_ids=list(aliases_map.keys()),
            aliases_map=aliases_map,
        )
        # Act
        asyncio.get_event_loop().run_until_complete(service.update_entity_aliases())
        # Assert – 3 aliases total
        assert alias_repo.add.call_count == 3

    def test_entity_with_no_aliases_is_skipped(self):
        # Arrange
        service, _, _, alias_repo = _make_service(
            exposed_ids=["light.garage"],
            aliases_map={"light.garage": []},  # empty alias list
        )
        # Act
        asyncio.get_event_loop().run_until_complete(service.update_entity_aliases())
        # Assert
        alias_repo.add.assert_not_called()

    def test_entity_that_raises_is_ignored(self):
        # Arrange
        light_repo = AsyncMock()
        config_repo = AsyncMock()
        alias_repo = MagicMock()

        config_repo.get_all_exposed_entities_ids.return_value = [
            "light.ok",
            "light.bad",
        ]

        async def _aliases(entity_id):
            if entity_id == "light.bad":
                raise RuntimeError("HA timeout")
            return ["Good Light"]

        config_repo.get_aliases_by_entity_id.side_effect = _aliases

        service = SmartHomeService(
            smart_home_light_repository=light_repo,
            smart_home_configuration_repository=config_repo,
            smart_home_entity_alias_repository=alias_repo,
        )
        # Act – should not propagate the exception
        asyncio.get_event_loop().run_until_complete(service.update_entity_aliases())
        # Assert – only the good entity was added
        assert alias_repo.add.call_count == 1
        added: SmartHomeEntityAlias = alias_repo.add.call_args[1]["entity_alias"]
        assert added.entity_id == "light.ok"

    def test_added_aliases_have_valid_uuid_ids(self):
        # Arrange
        service, _, _, alias_repo = _make_service(
            exposed_ids=["light.kitchen"],
            aliases_map={"light.kitchen": ["Cozinha"]},
        )
        # Act
        asyncio.get_event_loop().run_until_complete(service.update_entity_aliases())
        # Assert
        added: SmartHomeEntityAlias = alias_repo.add.call_args[1]["entity_alias"]
        assert uuid.UUID(added.id)

    def test_delete_all_called_before_adds(self):
        # Arrange
        call_order = []
        alias_repo = MagicMock()
        alias_repo.delete_all.side_effect = lambda: call_order.append("delete_all")
        alias_repo.add.side_effect = lambda **kwargs: call_order.append("add")

        config_repo = AsyncMock()
        config_repo.get_all_exposed_entities_ids.return_value = ["light.hall"]
        config_repo.get_aliases_by_entity_id.return_value = ["Corredor"]

        service = SmartHomeService(
            smart_home_light_repository=AsyncMock(),
            smart_home_configuration_repository=config_repo,
            smart_home_entity_alias_repository=alias_repo,
        )
        # Act
        asyncio.get_event_loop().run_until_complete(service.update_entity_aliases())
        # Assert
        assert call_order[0] == "delete_all"
        assert "add" in call_order


# ===========================================================================
# Bug 5 — update_entity_aliases never closes the WebSocket connection
# ===========================================================================

class TestSmartHomeServiceUpdateEntityAliasesClosesWebSocket:

    def test_update_entity_aliases__after_success__closes_websocket_connection(self):
        """
        Bug: update_entity_aliases() calls get_all_exposed_entities_ids() and
        get_aliases_by_entity_id() but never calls close() on the configuration
        repository. The WebSocket connection is left open indefinitely.
        After the fix, close() must be called exactly once after a successful run.
        """
        # Arrange
        service, _, config_repo, _ = _make_service(
            exposed_ids=["light.sala"],
            aliases_map={"light.sala": ["Sala"]},
        )
        # Act
        asyncio.get_event_loop().run_until_complete(service.update_entity_aliases())
        # Assert
        config_repo.close.assert_awaited_once()

    def test_update_entity_aliases__after_error_in_get_aliases__closes_websocket_connection(self):
        """
        Bug: when every get_aliases_by_entity_id() raises an exception the bare
        'except: continue' swallows the errors but close() is still never called.
        After the fix, close() must be called exactly once regardless of per-entity
        errors during the alias-fetching loop.
        """
        # Arrange
        light_repo = AsyncMock()
        config_repo = AsyncMock()
        alias_repo = MagicMock()

        config_repo.get_all_exposed_entities_ids.return_value = [
            "light.bad_one",
            "light.bad_two",
        ]

        async def _always_raise(entity_id):
            raise RuntimeError("WebSocket timeout")

        config_repo.get_aliases_by_entity_id.side_effect = _always_raise

        service = SmartHomeService(
            smart_home_light_repository=light_repo,
            smart_home_configuration_repository=config_repo,
            smart_home_entity_alias_repository=alias_repo,
        )
        # Act — must not propagate the exception
        asyncio.get_event_loop().run_until_complete(service.update_entity_aliases())
        # Assert
        config_repo.close.assert_awaited_once()


class TestSmartHomeServiceLightTurnOn:

    def test_light_turn_on_delegates_to_repository(self):
        # Arrange
        service, light_repo, _, _ = _make_service()
        cmd = LightTurnOn(entity_id="light.kitchen", brightness=200)
        # Act
        asyncio.get_event_loop().run_until_complete(service.light_turn_on(cmd))
        # Assert
        light_repo.turn_on.assert_awaited_once_with(turn_on_command=cmd)


class TestSmartHomeServiceLightTurnOff:

    def test_light_turn_off_delegates_to_repository(self):
        # Arrange
        service, light_repo, _, _ = _make_service()
        # Act
        asyncio.get_event_loop().run_until_complete(service.light_turn_off("light.bedroom"))
        # Assert
        light_repo.turn_off.assert_awaited_once_with(entity_id="light.bedroom")
