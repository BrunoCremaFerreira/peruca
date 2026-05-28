import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest

from application.appservices.smart_home_app_service import SmartHomeAppService
from domain.entities import SmartHomeEntityAlias


"""
SmartHomeAppService Unit Tests
"""


def _sample_alias(entity_id="light.kitchen", alias="Cozinha") -> SmartHomeEntityAlias:
    return SmartHomeEntityAlias(id=str(uuid.uuid4()), entity_id=entity_id, alias=alias)


def _make_app_service(light_repo=None, alias_repo=None, svc=None):
    if light_repo is None:
        light_repo = AsyncMock()
    if alias_repo is None:
        alias_repo = MagicMock()
        alias_repo.get_all.return_value = []
    if svc is None:
        svc = AsyncMock()
    return SmartHomeAppService(
        smart_home_light_repository=light_repo,
        smart_home_entity_alias_repository=alias_repo,
        smart_home_service=svc,
    )


class TestSmartHomeAppServiceGetAllEntityAliases:
    def test_get_all_entity_aliases_returns_list(self):
        # Arrange
        aliases = [
            _sample_alias("light.living_room", "Sala"),
            _sample_alias("light.bedroom", "Quarto"),
        ]
        alias_repo = MagicMock()
        alias_repo.get_all.return_value = aliases
        app_service = _make_app_service(alias_repo=alias_repo)
        # Act
        result = app_service.get_all_entity_aliases()
        # Assert
        assert result == aliases
        alias_repo.get_all.assert_called_once()

    def test_get_all_entity_aliases_returns_empty_list_when_none(self):
        # Arrange
        alias_repo = MagicMock()
        alias_repo.get_all.return_value = []
        app_service = _make_app_service(alias_repo=alias_repo)
        # Act
        result = app_service.get_all_entity_aliases()
        # Assert
        assert result == []


class TestSmartHomeAppServiceUpdateEntityAliases:
    def test_update_entity_aliases_delegates_to_domain_service(self):
        # Arrange
        svc = AsyncMock()
        app_service = _make_app_service(svc=svc)
        # Act
        asyncio.get_event_loop().run_until_complete(app_service.update_entity_aliases())
        # Assert
        svc.update_entity_aliases.assert_awaited_once()

    def test_update_entity_aliases_propagates_exception(self):
        # Arrange
        svc = AsyncMock()
        svc.update_entity_aliases.side_effect = RuntimeError("HA unreachable")
        app_service = _make_app_service(svc=svc)
        # Act / Assert
        with pytest.raises(RuntimeError, match="HA unreachable"):
            asyncio.get_event_loop().run_until_complete(
                app_service.update_entity_aliases()
            )
