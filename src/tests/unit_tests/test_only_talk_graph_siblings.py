"""
OnlyTalkGraph dynamic persona (§2.9): the hardcoded "Seus irmãos" section is
gone from the prompt; the pets registered by the user are injected as siblings
via context_hints["user_pets_persona"], sanitized. Absent/empty -> neutral text.
"""

import os
import uuid
from unittest.mock import MagicMock, patch

from application.graphs.only_talk_graph import OnlyTalkGraph
from domain.entities import GraphInvokeRequest, User


_TZ = "America/Sao_Paulo"


_TEMPLATE = "PERSONA|{user_name}|{user_memories}|{siblings}|{current_datetime}"


def _user():
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Bruno", summary="")


def _make_graph():
    with patch.object(OnlyTalkGraph, "load_prompt", return_value=_TEMPLATE):
        graph = OnlyTalkGraph(
            llm_chat=MagicMock(),
            get_session_history=lambda _uid: MagicMock(messages=[]),
        )
    return graph


def _req(persona=None):
    hints = {}
    if persona is not None:
        hints["user_pets_persona"] = persona
    return GraphInvokeRequest(message="oi", user=_user(), context_hints=hints, user_timezone=_TZ)


class TestSiblingsInjection:
    def test_persona_block_rendered(self):
        graph = _make_graph()
        persona = "- **Caçolin** (apelidos: Lilo): vira-lata caramelo, preguiçoso."
        system = graph._format_system(_req(persona))
        assert "Caçolin" in system
        assert "vira-lata caramelo" in system

    def test_no_pets__neutral_fallback(self):
        graph = _make_graph()
        system = graph._format_system(_req(persona=None))
        assert "nenhum pet" in system.lower()

    def test_empty_persona__neutral_fallback(self):
        graph = _make_graph()
        system = graph._format_system(_req(persona="   "))
        assert "nenhum pet" in system.lower()


class TestPromptFileNoHardcode:
    def test_hardcoded_siblings_removed_and_placeholder_present(self):
        path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "infra", "prompts", "only_talk_graph.md",
        )
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # The hardcoded pet names must no longer be baked into the persona.
        assert "Caçolin" not in content
        assert "Caçolão" not in content
        # The dynamic placeholder must be present.
        assert "{siblings}" in content
