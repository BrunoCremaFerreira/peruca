"""
SmartHomeService.get_light_status_by_alias Unit Tests (TDD — RED).

Specification for a NEW method that resolves a single light by a spoken alias
and returns its current state, WITHOUT any LLM call.

Contract under test:
  - Builds an {alias: entity_id} catalog from
    smart_home_entity_alias_repository.get_all(entity_id_starts_with="light.")
    (each item exposes .alias and .entity_id).
  - Resolves deterministically via self.find_entity_ids_by_alias(...), which
    returns [] for 0 or multiple matches.
  - When exactly one entity_id is resolved -> awaits
    smart_home_light_repository.get_state(entity_id) and returns the
    SmartHomeLight.
  - When nothing is resolved -> returns None (NOT a phrase) and MUST NOT call
    get_state.

The method does NOT exist yet — these tests fail with AttributeError until it
is implemented. That is the expected TDD red state (absence, not import error).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from domain.entities import SmartHomeEntityAlias, SmartHomeLight
from domain.services.smart_home_service import SmartHomeService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _alias(entity_id: str, alias: str) -> SmartHomeEntityAlias:
    """Build a SmartHomeEntityAlias catalog row."""
    return SmartHomeEntityAlias(entity_id=entity_id, alias=alias)


def _light(
    entity_id: str = "light.garagem",
    is_on: bool = True,
    is_available: bool = True,
    friendly_name: str = "Garagem",
) -> SmartHomeLight:
    """Build a SmartHomeLight entity for use in mocked repository responses."""
    return SmartHomeLight(
        entity_id=entity_id,
        is_on=is_on,
        is_available=is_available,
        friendly_name=friendly_name,
    )


def _make_service(aliases, light=None):
    """
    Build a SmartHomeService with mocked repositories.

    aliases: list[SmartHomeEntityAlias] returned by alias_repo.get_all(...)
    light:   SmartHomeLight returned by light_repo.get_state(...)

    Returns: (service, light_repo, alias_repo)
    """
    light_repo = AsyncMock()
    light_repo.get_state.return_value = light
    alias_repo = MagicMock()
    alias_repo.get_all.return_value = aliases

    service = SmartHomeService(
        smart_home_light_repository=light_repo,
        smart_home_configuration_repository=AsyncMock(),
        smart_home_entity_alias_repository=alias_repo,
        smart_home_climate_repository=AsyncMock(),
    )
    return service, light_repo, alias_repo


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ===========================================================================
# TestGetLightStatusByAlias — resolved hits
# ===========================================================================


class TestGetLightStatusByAlias:
    def test_get_status__resolved_light_on__returns_light(self):
        """Alias resolves to a single light that is on -> returns that light."""
        light = _light(is_on=True, is_available=True)
        service, light_repo, _ = _make_service(
            aliases=[_alias("light.garagem", "luz da garagem")],
            light=light,
        )

        result = _run(service.get_light_status_by_alias(query_alias="garagem"))

        assert result is light, f"Expected the exact light from the repo, got {result!r}"
        light_repo.get_state.assert_awaited_once()

    def test_get_status__resolved_light_off__returns_light(self):
        """Alias resolves to a single light that is off -> returns that light."""
        light = _light(is_on=False, is_available=True)
        service, light_repo, _ = _make_service(
            aliases=[_alias("light.garagem", "luz da garagem")],
            light=light,
        )

        result = _run(service.get_light_status_by_alias(query_alias="garagem"))

        assert result is light
        assert result.is_on is False
        light_repo.get_state.assert_awaited_once()

    def test_get_status__resolved_light_offline__returns_light(self):
        """Alias resolves to a single light that is offline -> returns that light."""
        light = _light(is_on=None, is_available=False)
        service, light_repo, _ = _make_service(
            aliases=[_alias("light.garagem", "luz da garagem")],
            light=light,
        )

        result = _run(service.get_light_status_by_alias(query_alias="garagem"))

        assert result is light
        assert result.is_available is False
        light_repo.get_state.assert_awaited_once()

    def test_get_status__resolved__queries_state_with_matched_entity_id(self):
        """get_state must be called with the deterministically resolved entity_id."""
        service, light_repo, _ = _make_service(
            aliases=[_alias("light.garagem", "luz da garagem")],
            light=_light(),
        )

        _run(service.get_light_status_by_alias(query_alias="garagem"))

        call = light_repo.get_state.call_args
        passed_entity_id = (
            call.kwargs.get("entity_id") if call.kwargs else call.args[0]
        )
        assert passed_entity_id == "light.garagem", (
            f"Expected get_state('light.garagem'), got {passed_entity_id!r}"
        )

    def test_get_status__builds_catalog_only_from_light_entities(self):
        """
        The alias catalog must be pulled with entity_id_starts_with='light.'
        so that only lights are considered.
        """
        service, _, alias_repo = _make_service(
            aliases=[_alias("light.garagem", "luz da garagem")],
            light=_light(),
        )

        _run(service.get_light_status_by_alias(query_alias="garagem"))

        alias_repo.get_all.assert_called_once_with(entity_id_starts_with="light.")


# ===========================================================================
# TestGetLightStatusByAliasNotFound — 0 or multiple matches
# ===========================================================================


class TestGetLightStatusByAliasNotFound:
    def test_get_status__unresolved_alias__returns_none(self):
        """When find_entity_ids_by_alias yields [] the method returns None."""
        service, _, _ = _make_service(
            aliases=[_alias("light.garagem", "luz da garagem")],
            light=_light(),
        )

        result = _run(service.get_light_status_by_alias(query_alias="escritorio"))

        assert result is None, f"Expected None for an unresolved alias, got {result!r}"

    def test_get_status__unresolved_alias__does_not_call_get_state(self):
        """A non-resolving alias must never reach the light repository."""
        service, light_repo, _ = _make_service(
            aliases=[_alias("light.garagem", "luz da garagem")],
            light=_light(),
        )

        _run(service.get_light_status_by_alias(query_alias="escritorio"))

        light_repo.get_state.assert_not_called()

    def test_get_status__empty_catalog__returns_none_without_calling_get_state(self):
        """With no known light aliases nothing resolves; get_state is not called."""
        service, light_repo, _ = _make_service(aliases=[], light=_light())

        result = _run(service.get_light_status_by_alias(query_alias="garagem"))

        assert result is None
        light_repo.get_state.assert_not_called()
