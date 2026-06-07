import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

try:
    import aiohttp
    from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_climate_repository import (
        HomeAssistantSmartHomeClimateRepository,
    )
    from domain.commands import (
        ClimateSetTemperature,
        ClimateSetHvacMode,
        ClimateTurnOn,
        ClimateTurnOff,
    )
    from domain.entities import SmartHomeClimate, SmartHomeHvacMode
except ImportError:
    pass


"""
HomeAssistantSmartHomeClimateRepository Unit Tests

Covers the complete contract of the climate repository adapter:
  - get_state: maps HA REST response fields to SmartHomeClimate entity
  - set_temperature: sends correct URL and payload
  - set_hvac_mode: sends hvac_mode as plain string, not enum
  - turn_on: sends correct URL and payload
  - turn_off: handles ContentTypeError and returns fallback dict
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo() -> "HomeAssistantSmartHomeClimateRepository":
    return HomeAssistantSmartHomeClimateRepository(
        base_url="http://localhost:8123",
        token="test-token",
    )


def _make_ha_climate_state_response(
    entity_id: str = "climate.sala",
    state: str = "cool",
    current_temperature: float = 24.5,
    target_temperature: float = 22.0,
    hvac_modes: list = None,
    fan_mode: str = "auto",
    swing_mode: str = "off",
) -> dict:
    """Simulate a typical Home Assistant /api/states response for a climate entity."""
    return {
        "entity_id": entity_id,
        "state": state,
        "attributes": {
            "current_temperature": current_temperature,
            "temperature": target_temperature,  # HA field is 'temperature', not 'target_temperature'
            "hvac_modes": hvac_modes
            if hvac_modes is not None
            else ["cool", "heat", "auto", "off"],
            "fan_mode": fan_mode,
            "swing_mode": swing_mode,
        },
    }


def _mock_aiohttp_session(json_response: dict):
    """
    Returns a mock aiohttp.ClientSession context-manager that yields
    a response whose .json() coroutine returns json_response.
    Matches the pattern used in test_home_assistant_light_repository.py.
    """
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=json_response)
    mock_resp.status = 200

    mock_cm_resp = AsyncMock()
    mock_cm_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_cm_resp)
    mock_session.post = MagicMock(return_value=mock_cm_resp)

    mock_cm_session = AsyncMock()
    mock_cm_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm_session.__aexit__ = AsyncMock(return_value=False)

    return mock_cm_session, mock_session


def _mock_aiohttp_session_content_type_error(status: int = 200):
    """
    Returns a mock aiohttp.ClientSession where resp.json() raises
    aiohttp.ContentTypeError, simulating a response with non-JSON body.
    """
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.status = status
    # ContentTypeError requires a RequestInfo and history; use MagicMock for both
    mock_resp.json = AsyncMock(
        side_effect=aiohttp.ContentTypeError(MagicMock(), MagicMock())
    )

    mock_cm_resp = AsyncMock()
    mock_cm_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_cm_resp)
    mock_session.post = MagicMock(return_value=mock_cm_resp)

    mock_cm_session = AsyncMock()
    mock_cm_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm_session.__aexit__ = AsyncMock(return_value=False)

    return mock_cm_session, mock_session


# ===========================================================================
# TestGetState
# ===========================================================================


class TestGetState:
    def test_get_state__entity_id__is_populated_in_result(self):
        """entity_id passed to get_state must be reflected on the returned entity."""
        entity_id = "climate.quarto"
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session(
            _make_ha_climate_state_response(entity_id=entity_id)
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state(entity_id=entity_id)
            )

        assert result.entity_id == entity_id, (
            f"Expected entity_id={entity_id!r}, got {result.entity_id!r}"
        )

    def test_get_state__state_field_cool__maps_to_hvac_mode_cool(self):
        """HA state 'cool' must map to SmartHomeHvacMode.COOL."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session(
            _make_ha_climate_state_response(state="cool")
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state(entity_id="climate.sala")
            )

        assert result.hvac_mode == SmartHomeHvacMode.COOL, (
            f"Expected SmartHomeHvacMode.COOL for state='cool', got {result.hvac_mode!r}"
        )

    def test_get_state__state_field_heat__maps_to_hvac_mode_heat(self):
        """HA state 'heat' must map to SmartHomeHvacMode.HEAT."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session(
            _make_ha_climate_state_response(state="heat")
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state(entity_id="climate.sala")
            )

        assert result.hvac_mode == SmartHomeHvacMode.HEAT, (
            f"Expected SmartHomeHvacMode.HEAT for state='heat', got {result.hvac_mode!r}"
        )

    def test_get_state__state_is_not_off__is_on_is_true(self):
        """When HA state is not 'off', is_on must be True."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session(
            _make_ha_climate_state_response(state="cool")
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state(entity_id="climate.sala")
            )

        assert result.is_on is True, (
            f"Expected is_on=True when state is not 'off', got {result.is_on!r}"
        )

    def test_get_state__state_is_off__is_on_is_false(self):
        """When HA state is 'off', is_on must be False."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session(
            _make_ha_climate_state_response(state="off")
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state(entity_id="climate.sala")
            )

        assert result.is_on is False, (
            f"Expected is_on=False when state='off', got {result.is_on!r}"
        )

    def test_get_state__current_temperature__read_from_attributes(self):
        """current_temperature must be read from attributes.current_temperature."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session(
            _make_ha_climate_state_response(current_temperature=26.3)
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state(entity_id="climate.sala")
            )

        assert result.current_temperature == 26.3, (
            f"Expected current_temperature=26.3, got {result.current_temperature!r}"
        )

    def test_get_state__target_temperature__read_from_attributes_temperature_field(
        self,
    ):
        """
        target_temperature must be read from attributes['temperature'].
        The HA API field is named 'temperature', not 'target_temperature'.
        """
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session(
            _make_ha_climate_state_response(target_temperature=21.0)
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state(entity_id="climate.sala")
            )

        assert result.target_temperature == 21.0, (
            f"Expected target_temperature=21.0 from HA 'temperature' attribute, "
            f"got {result.target_temperature!r}"
        )

    def test_get_state__hvac_modes__read_from_attributes(self):
        """hvac_modes must be read from attributes.hvac_modes."""
        expected_modes = ["cool", "heat", "dry", "off"]
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session(
            _make_ha_climate_state_response(hvac_modes=expected_modes)
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state(entity_id="climate.sala")
            )

        assert result.hvac_modes == expected_modes, (
            f"Expected hvac_modes={expected_modes!r}, got {result.hvac_modes!r}"
        )

    def test_get_state__fan_mode__read_from_attributes(self):
        """fan_mode must be read from attributes.fan_mode."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session(
            _make_ha_climate_state_response(fan_mode="high")
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state(entity_id="climate.sala")
            )

        assert result.fan_mode == "high", (
            f"Expected fan_mode='high', got {result.fan_mode!r}"
        )

    def test_get_state__url__does_not_duplicate_base_url(self):
        """
        The URL sent to session.get must start with the base_url exactly once.
        Protect against the common bug of prepending the scheme when base_url
        already contains it (e.g. 'http://http://localhost:8123/...').
        """
        repo = _make_repo()
        entity_id = "climate.sala"
        _, mock_session = _mock_aiohttp_session(
            _make_ha_climate_state_response(entity_id=entity_id)
        )

        with patch.object(repo, "_get_session", return_value=mock_session):
            asyncio.get_event_loop().run_until_complete(
                repo.get_state(entity_id=entity_id)
            )

        called_url = mock_session.get.call_args[0][0]
        assert not called_url.startswith("http://http://"), (
            f"URL duplicates scheme: {called_url!r}"
        )
        assert called_url.startswith("http://localhost:8123"), (
            f"Expected URL to start with 'http://localhost:8123', got: {called_url!r}"
        )
        assert entity_id in called_url, (
            f"Expected entity_id={entity_id!r} in URL, got: {called_url!r}"
        )

    def test_get_state__ha_returns_404__propagates_client_response_error(self):
        """A 4xx/5xx response from HA must propagate as aiohttp.ClientResponseError."""
        repo = _make_repo()

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(
                MagicMock(), MagicMock(), status=404
            )
        )
        mock_resp.status = 404

        mock_cm_resp = AsyncMock()
        mock_cm_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_cm_resp)

        with patch.object(repo, "_get_session", return_value=mock_session):
            with pytest.raises(aiohttp.ClientResponseError):
                asyncio.get_event_loop().run_until_complete(
                    repo.get_state(entity_id="climate.nonexistent")
                )


# ===========================================================================
# TestSetTemperature
# ===========================================================================


class TestSetTemperature:
    def test_set_temperature__sends_correct_url(self):
        """POST must be sent to /api/services/climate/set_temperature."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session([])

        with patch.object(repo, "_get_session", return_value=mock_session):
            cmd = ClimateSetTemperature(entity_id="climate.sala", temperature=22.0)
            asyncio.get_event_loop().run_until_complete(repo.set_temperature(cmd))

        called_url = mock_session.post.call_args[0][0]
        assert "climate/set_temperature" in called_url, (
            f"Expected URL to contain 'climate/set_temperature', got: {called_url!r}"
        )
        assert called_url.startswith("http://localhost:8123"), (
            f"Expected URL to start with base_url, got: {called_url!r}"
        )

    def test_set_temperature__payload_contains_entity_id(self):
        """The POST body must include the entity_id field."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session([])

        with patch.object(repo, "_get_session", return_value=mock_session):
            cmd = ClimateSetTemperature(entity_id="climate.quarto", temperature=20.0)
            asyncio.get_event_loop().run_until_complete(repo.set_temperature(cmd))

        call_kwargs = mock_session.post.call_args[1]
        payload = call_kwargs.get("json", {})
        assert payload.get("entity_id") == "climate.quarto", (
            f"Expected entity_id='climate.quarto' in payload, got: {payload!r}"
        )

    def test_set_temperature__payload_contains_temperature(self):
        """The POST body must include the temperature field with the correct value."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session([])

        with patch.object(repo, "_get_session", return_value=mock_session):
            cmd = ClimateSetTemperature(entity_id="climate.sala", temperature=18.5)
            asyncio.get_event_loop().run_until_complete(repo.set_temperature(cmd))

        call_kwargs = mock_session.post.call_args[1]
        payload = call_kwargs.get("json", {})
        assert payload.get("temperature") == 18.5, (
            f"Expected temperature=18.5 in payload, got: {payload!r}"
        )

    def test_set_temperature__returns_response_dict(self):
        """set_temperature must return the response body as a dict."""
        repo = _make_repo()
        expected_response = {"result": "ok"}
        _, mock_session = _mock_aiohttp_session(expected_response)

        with patch.object(repo, "_get_session", return_value=mock_session):
            cmd = ClimateSetTemperature(entity_id="climate.sala", temperature=22.0)
            result = asyncio.get_event_loop().run_until_complete(
                repo.set_temperature(cmd)
            )

        assert result == expected_response, (
            f"Expected {expected_response!r}, got {result!r}"
        )


# ===========================================================================
# TestSetHvacMode
# ===========================================================================


class TestSetHvacMode:
    def test_set_hvac_mode__sends_correct_url(self):
        """POST must be sent to /api/services/climate/set_hvac_mode."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session([])

        with patch.object(repo, "_get_session", return_value=mock_session):
            cmd = ClimateSetHvacMode(entity_id="climate.sala", hvac_mode="cool")
            asyncio.get_event_loop().run_until_complete(repo.set_hvac_mode(cmd))

        called_url = mock_session.post.call_args[0][0]
        assert "climate/set_hvac_mode" in called_url, (
            f"Expected URL to contain 'climate/set_hvac_mode', got: {called_url!r}"
        )
        assert called_url.startswith("http://localhost:8123"), (
            f"Expected URL to start with base_url, got: {called_url!r}"
        )

    def test_set_hvac_mode__payload_contains_entity_id(self):
        """The POST body must include the entity_id field."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session([])

        with patch.object(repo, "_get_session", return_value=mock_session):
            cmd = ClimateSetHvacMode(entity_id="climate.quarto", hvac_mode="heat")
            asyncio.get_event_loop().run_until_complete(repo.set_hvac_mode(cmd))

        call_kwargs = mock_session.post.call_args[1]
        payload = call_kwargs.get("json", {})
        assert payload.get("entity_id") == "climate.quarto", (
            f"Expected entity_id='climate.quarto' in payload, got: {payload!r}"
        )

    def test_set_hvac_mode__hvac_mode_sent_as_string_not_enum(self):
        """
        The hvac_mode field in the POST payload must be a plain string, not a
        SmartHomeHvacMode enum instance. HA REST API does not accept Python objects.
        """
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session([])

        with patch.object(repo, "_get_session", return_value=mock_session):
            cmd = ClimateSetHvacMode(entity_id="climate.sala", hvac_mode="cool")
            asyncio.get_event_loop().run_until_complete(repo.set_hvac_mode(cmd))

        call_kwargs = mock_session.post.call_args[1]
        payload = call_kwargs.get("json", {})
        hvac_mode_value = payload.get("hvac_mode")
        assert isinstance(hvac_mode_value, str), (
            f"Expected hvac_mode to be a str, got {type(hvac_mode_value)}: {hvac_mode_value!r}"
        )
        assert hvac_mode_value == "cool", (
            f"Expected hvac_mode='cool', got {hvac_mode_value!r}"
        )


# ===========================================================================
# TestTurnOn
# ===========================================================================


class TestTurnOn:
    def test_turn_on__sends_correct_url(self):
        """POST must be sent to /api/services/climate/turn_on."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session([])

        with patch.object(repo, "_get_session", return_value=mock_session):
            cmd = ClimateTurnOn(entity_id="climate.sala")
            asyncio.get_event_loop().run_until_complete(repo.turn_on(cmd))

        called_url = mock_session.post.call_args[0][0]
        assert "climate/turn_on" in called_url, (
            f"Expected URL to contain 'climate/turn_on', got: {called_url!r}"
        )
        assert called_url.startswith("http://localhost:8123"), (
            f"Expected URL to start with base_url, got: {called_url!r}"
        )

    def test_turn_on__payload_contains_entity_id(self):
        """The POST body must include the entity_id field."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session([])

        with patch.object(repo, "_get_session", return_value=mock_session):
            cmd = ClimateTurnOn(entity_id="climate.quarto")
            asyncio.get_event_loop().run_until_complete(repo.turn_on(cmd))

        call_kwargs = mock_session.post.call_args[1]
        payload = call_kwargs.get("json", {})
        assert payload.get("entity_id") == "climate.quarto", (
            f"Expected entity_id='climate.quarto' in payload, got: {payload!r}"
        )

    def test_turn_on__returns_response_dict(self):
        """turn_on must return the response body as a dict."""
        repo = _make_repo()
        expected_response = {"result": "ok"}
        _, mock_session = _mock_aiohttp_session(expected_response)

        with patch.object(repo, "_get_session", return_value=mock_session):
            cmd = ClimateTurnOn(entity_id="climate.sala")
            result = asyncio.get_event_loop().run_until_complete(repo.turn_on(cmd))

        assert result == expected_response, (
            f"Expected {expected_response!r}, got {result!r}"
        )


# ===========================================================================
# TestTurnOff
# ===========================================================================


class TestTurnOff:
    def test_turn_off__sends_correct_url(self):
        """POST must be sent to /api/services/climate/turn_off."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session([])

        with patch.object(repo, "_get_session", return_value=mock_session):
            cmd = ClimateTurnOff(entity_id="climate.sala")
            asyncio.get_event_loop().run_until_complete(repo.turn_off(cmd))

        called_url = mock_session.post.call_args[0][0]
        assert "climate/turn_off" in called_url, (
            f"Expected URL to contain 'climate/turn_off', got: {called_url!r}"
        )
        assert called_url.startswith("http://localhost:8123"), (
            f"Expected URL to start with base_url, got: {called_url!r}"
        )

    def test_turn_off__payload_contains_entity_id(self):
        """The POST body must include the entity_id field."""
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session([])

        with patch.object(repo, "_get_session", return_value=mock_session):
            cmd = ClimateTurnOff(entity_id="climate.quarto")
            asyncio.get_event_loop().run_until_complete(repo.turn_off(cmd))

        call_kwargs = mock_session.post.call_args[1]
        payload = call_kwargs.get("json", {})
        assert payload.get("entity_id") == "climate.quarto", (
            f"Expected entity_id='climate.quarto' in payload, got: {payload!r}"
        )

    def test_turn_off__returns_response_dict_when_json_available(self):
        """turn_off must return the response body as a dict when JSON is available."""
        repo = _make_repo()
        expected_response = [{"result": "ok"}]
        _, mock_session = _mock_aiohttp_session(expected_response)

        with patch.object(repo, "_get_session", return_value=mock_session):
            cmd = ClimateTurnOff(entity_id="climate.sala")
            result = asyncio.get_event_loop().run_until_complete(repo.turn_off(cmd))

        assert result == expected_response, (
            f"Expected {expected_response!r}, got {result!r}"
        )

    def test_turn_off__content_type_error__returns_fallback_dict(self):
        """
        When HA responds with a non-JSON body (ContentTypeError),
        turn_off must catch the error and return a fallback dict with
        the HTTP status and a generic message instead of propagating the exception.
        """
        repo = _make_repo()
        _, mock_session = _mock_aiohttp_session_content_type_error(status=200)

        with patch.object(repo, "_get_session", return_value=mock_session):
            cmd = ClimateTurnOff(entity_id="climate.sala")
            result = asyncio.get_event_loop().run_until_complete(repo.turn_off(cmd))

        assert isinstance(result, dict), (
            f"Expected a dict fallback, got {type(result)}: {result!r}"
        )
        assert result.get("status") == 200, (
            f"Expected status=200 in fallback dict, got: {result!r}"
        )
        assert "message" in result, (
            f"Expected 'message' key in fallback dict, got: {result!r}"
        )


# ===========================================================================
# TestSessionReuse — aiohttp.ClientSession must be created at most once
# ===========================================================================
#
# Contract (Milestone 2B-2): the adapter reuses a single aiohttp.ClientSession
# across calls via _get_session(). Calling a method twice must instantiate
# aiohttp.ClientSession AT MOST ONCE.
#
# RED today: every method opens `async with aiohttp.ClientSession() as session`,
# so two calls instantiate the session twice (call_count == 2).


def _make_reusable_session(json_response):
    """
    Build a single session mock that works regardless of whether production
    uses it as a context manager (`async with aiohttp.ClientSession() as s`)
    or directly via _get_session() (`s = self._get_session()`).

    The session enters itself (`__aenter__` returns the same object), so the
    `.get`/`.post` calls — which return the response context manager — are
    always reachable. Only the instantiation count is asserted by the caller.
    """
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=json_response)
    mock_resp.status = 200

    mock_cm_resp = AsyncMock()
    mock_cm_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_cm_resp)
    mock_session.post = MagicMock(return_value=mock_cm_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


class TestSessionReuse:
    def test_get_state__called_twice__client_session_instantiated_once(self):
        repo = _make_repo()
        mock_session = _make_reusable_session(_make_ha_climate_state_response())

        with patch(
            "aiohttp.ClientSession", return_value=mock_session
        ) as client_session_cls:
            asyncio.get_event_loop().run_until_complete(
                repo.get_state(entity_id="climate.sala")
            )
            asyncio.get_event_loop().run_until_complete(
                repo.get_state(entity_id="climate.sala")
            )

        assert client_session_cls.call_count == 1, (
            f"Expected aiohttp.ClientSession to be instantiated once across two "
            f"calls (session reuse), got {client_session_cls.call_count}"
        )
