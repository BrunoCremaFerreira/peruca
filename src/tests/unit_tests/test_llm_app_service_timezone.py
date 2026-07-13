"""
LlmAppService timezone resolution (TDD RED — plan §3.3 / §8.5 / §10.6).

LlmAppService.chat() is the SINGLE source of truth for the user's timezone: it
resolves it ONCE per request through UserSettingsService (whose own fallback is the
DEFAULT_TIMEZONE injected by the IoC) and injects it into the GraphInvokeRequest.
No graph ever reaches for the settings repository, and no layer below ever hardcodes
a default timezone.

Contract fixed by these tests:

    LlmAppService(..., user_settings_service=None)   # new keyword parameter

    chat():
        user_timezone = user_settings_service.get_timezone(user.id)   # once
        GraphInvokeRequest(..., user_timezone=user_timezone)

    the pending-flow short-circuits hand the flow services the user's LOCAL date as
    the parsing reference:

        maintenance_flow_service.parse_slot_reply(pending, message, vehicles=...,
                                                  reference=<local date>)
        pet_health_flow_service.parse_slot_reply(pending, message, pets=...,
                                                 reference=<local date>)
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from application.appservices.llm_app_service import LlmAppService
from application.appservices.view_models import ChatRequest
from domain.entities import GraphInvokeRequest, PendingFlow, User
from domain.services.clock import local_date_for_user
from domain.services.pet_health_flow_service import SlotReplyResult


_SP = "America/Sao_Paulo"
_TOKYO = "Asia/Tokyo"


def _user():
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Bruno")


def _make_settings_service(user_timezone=_SP):
    service = MagicMock()
    service.get_timezone.return_value = user_timezone
    return service


def _make(user, user_settings_service, pet_pending=None, slot_result=None):
    main_graph = MagicMock()
    main_graph.invoke.return_value = {"output": "roteado", "intent": ["only_talking"]}

    user_repository = MagicMock()
    user_repository.get_by_external_id.return_value = user

    user_memory_service = MagicMock()
    user_memory_service.get_all_by_user.return_value = []

    pet_flow = None
    if pet_pending is not None:
        pet_flow = MagicMock()
        pet_flow.get_pending = AsyncMock(return_value=pet_pending)
        pet_flow.set_pending = AsyncMock()
        pet_flow.clear_pending = AsyncMock()
        pet_flow.clear_focus = AsyncMock()
        pet_flow.parse_slot_reply = MagicMock(
            return_value=slot_result or SlotReplyResult(kind="none")
        )

    pet_read_repository = MagicMock()
    pet_read_repository.get_all_by_user_id.return_value = []

    service = LlmAppService(
        main_graph=main_graph,
        context_repository=MagicMock(),
        user_repository=user_repository,
        user_memory_service=user_memory_service,
        disambiguation_service=None,
        maintenance_flow_service=None,
        pet_health_flow_service=pet_flow,
        pet_health_service=MagicMock(),
        pet_read_repository=pet_read_repository,
        user_settings_service=user_settings_service,
    )
    return service, main_graph, pet_flow


def _req(user, message="oi"):
    return ChatRequest(message=message, external_user_id=user.external_id, chat_id="c1")


class TestGraphInvokeRequestUserTimezoneField:
    def test_default_is_empty__no_policy_literal_in_the_domain(self):
        # The default must NOT be "America/Sao_Paulo": policy lives in the IoC
        # (DEFAULT_TIMEZONE) and reaches the graphs through LlmAppService only.
        request = GraphInvokeRequest(message="oi", user=_user())
        assert request.user_timezone == ""


class TestChatResolvesTheTimezoneOnce:
    def test_chat__injects_the_user_timezone_into_the_graph_request(self):
        user = _user()
        settings = _make_settings_service(_TOKYO)
        service, main_graph, _ = _make(user, settings)

        service.chat(_req(user))

        _, kwargs = main_graph.invoke.call_args
        invoke_request = kwargs.get("invoke_request")
        assert invoke_request.user_timezone == _TOKYO

    def test_chat__reads_the_settings_service_exactly_once(self):
        user = _user()
        settings = _make_settings_service()
        service, _, _ = _make(user, settings)

        service.chat(_req(user))

        settings.get_timezone.assert_called_once_with(user.id)

    def test_chat__timezone_comes_from_settings_not_from_a_constant(self):
        user = _user()
        settings = _make_settings_service("Europe/Lisbon")
        service, main_graph, _ = _make(user, settings)

        service.chat(_req(user))

        _, kwargs = main_graph.invoke.call_args
        assert kwargs["invoke_request"].user_timezone == "Europe/Lisbon"

    def test_chat__no_settings_service__still_answers(self):
        # Not wired (unit-test composition): the request carries no timezone and
        # the app service must not crash — the graphs are the ones that fail loudly
        # if they actually need it.
        user = _user()
        service, main_graph, _ = _make(user, None)

        result = service.chat(_req(user))

        assert result["output"] == "roteado"


class TestFlowShortCircuitUsesTheUserLocalDate:
    def test_pet_flow__parse_slot_reply_receives_the_user_local_date(self):
        user = _user()
        settings = _make_settings_service(_TOKYO)
        pending = PendingFlow(
            operation="register",
            slots={"pet_id": "p1", "pet_name": "Caçolin", "event_type": "vaccine"},
            missing_slots=["date"],
            flow_domain="pet_health",
        )
        service, _, pet_flow = _make(
            user,
            settings,
            pet_pending=pending,
            slot_result=SlotReplyResult(kind="value", value=date(2026, 7, 9)),
        )

        service.chat(_req(user, "ontem"))

        _, kwargs = pet_flow.parse_slot_reply.call_args
        assert kwargs.get("reference") == local_date_for_user(_TOKYO)

    def test_pet_flow__reference_is_not_the_server_date_for_a_distant_timezone(self):
        # Kiritimati (UTC+14) and Midway (UTC-11) are 25h apart: their civil dates
        # never coincide, so one of them necessarily differs from date.today().
        user = _user()
        references = []
        for user_timezone in ("Pacific/Kiritimati", "Pacific/Midway"):
            pending = PendingFlow(
                operation="register",
                slots={"pet_id": "p1", "pet_name": "Caçolin"},
                missing_slots=["date"],
                flow_domain="pet_health",
            )
            service, _, pet_flow = _make(
                user,
                _make_settings_service(user_timezone),
                pet_pending=pending,
                slot_result=SlotReplyResult(kind="value", value=date(2026, 7, 9)),
            )
            service.chat(_req(user, "ontem"))
            references.append(pet_flow.parse_slot_reply.call_args[1].get("reference"))

        assert references[0] != references[1]
