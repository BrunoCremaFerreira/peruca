"""
OnlyTalkGraph "current datetime" timezone unit tests (TDD RED — plan §7 / §10.6).

Today `only_talk_graph.py` injects
``datetime.now().astimezone().strftime("%d/%m/%Y %H:%M")`` — the SERVER's timezone,
with no weekday. It must instead render the instant in the timezone carried by the
request, spelled out in pt-BR by
``application/appservices/datetime_presenter.format_current_datetime``:

    sexta-feira, 10/07/2026 11:32 (America/Sao_Paulo)

The graph reads `request.user_timezone` — it never resolves the timezone itself
(the single source of truth is LlmAppService.chat, §3.3) and never falls back to a
hardcoded default: an empty timezone must fail loudly through clock's
ValidationError.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from application.graphs.only_talk_graph import OnlyTalkGraph
from domain.entities import GraphInvokeRequest, User
from domain.exceptions import ValidationError

import pytest


_PROMPT_TEMPLATE = (
    "{user_name}|{user_summary}|{user_memories}|{siblings}|{current_datetime}"
)
_SP = "America/Sao_Paulo"
_TOKYO = "Asia/Tokyo"


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="resumo")


def _make_graph() -> OnlyTalkGraph:
    with patch.object(OnlyTalkGraph, "load_prompt", return_value=_PROMPT_TEMPLATE):
        return OnlyTalkGraph(
            llm_chat=MagicMock(),
            get_session_history=lambda _uid: MagicMock(messages=[]),
        )


def _req(user_timezone: str) -> GraphInvokeRequest:
    return GraphInvokeRequest(
        message="que horas são?",
        user=_sample_user(),
        memories=[],
        user_timezone=user_timezone,
    )


class TestCurrentDatetimeUsesTheUserTimezone:
    def test_current_datetime_is_built_from_the_request_timezone(self):
        # The presenter is the single formatting point; the graph must hand it the
        # timezone that travelled in the request.
        graph = _make_graph()
        with patch(
            "application.graphs.only_talk_graph.format_current_datetime",
            return_value="sexta-feira, 10/07/2026 11:32 (America/Sao_Paulo)",
        ) as presenter:
            system = graph._format_system(_req(_SP))
        presenter.assert_called_once()
        args, kwargs = presenter.call_args
        assert (args[0] if args else kwargs.get("tz")) == _SP
        assert "sexta-feira, 10/07/2026 11:32 (America/Sao_Paulo)" in system

    def test_server_timezone_is_never_used(self):
        # Discriminating, mock-free check: the same instant rendered for two very
        # distant timezones cannot produce the same wall clock. If the graph kept
        # using the server clock, both systems would be identical.
        graph = _make_graph()
        sao_paulo = graph._format_system(_req(_SP))
        tokyo = graph._format_system(_req(_TOKYO))
        assert sao_paulo != tokyo
        assert _SP in sao_paulo
        assert _TOKYO in tokyo

    def test_weekday_is_spelled_out_in_portuguese(self):
        graph = _make_graph()
        system = graph._format_system(_req(_SP))
        assert any(
            day in system
            for day in (
                "segunda-feira",
                "terça-feira",
                "quarta-feira",
                "quinta-feira",
                "sexta-feira",
                "sábado",
                "domingo",
            )
        )

    def test_empty_timezone__fails_loudly(self):
        # No policy literal in the graph: an unresolved timezone is a bug, not a
        # reason to pretend São Paulo.
        graph = _make_graph()
        with pytest.raises(ValidationError):
            graph._format_system(_req(""))


class TestPromptAntiHallucinationRule:
    def test_prompt_file_forbids_inventing_another_time(self):
        import os

        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "infra",
            "prompts",
            "only_talk_graph.md",
        )
        with open(path, encoding="utf-8") as handle:
            content = handle.read().lower()
        assert "{current_datetime}" in content
        # The rule of §7: answer with EXACTLY the injected value, never estimate
        # or convert to another timezone.
        assert "nunca" in content
        assert "fuso" in content


class TestDatetimeInjectionIsInstantaneous:
    def test_two_requests_share_the_same_second_bucket(self):
        # Guards against a module-level (import-time) datetime constant sneaking
        # back in: the rendered value must track the clock, not the import.
        graph = _make_graph()
        before = datetime.now(timezone.utc)
        system = graph._format_system(_req(_SP))
        after = datetime.now(timezone.utc)
        from domain.services.clock import now_for_timezone

        candidates = {
            now_for_timezone(_SP, now_utc=moment).strftime("%d/%m/%Y %H:%M")
            for moment in (before, after)
        }
        assert any(candidate in system for candidate in candidates)
