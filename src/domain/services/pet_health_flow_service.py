"""
PetHealthFlowService — persists a multi-turn pet-health operation between turns
and resolves the user's next reply deterministically (no LLM).

The pending state is stored as a JSON payload under ``pet_health_flow:{user_id}``
via the generic FlowStateStore (embedded TTL). ``parse_slot_reply`` is the §9.3
conservative parser (the whole message must BE the slot answer, otherwise it
falls through with kind "none" so a legitimate command is never swallowed) plus
the "tomou mais alguma?" loop (``register_more``, §2.6).
"""

import string
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from domain.entities import DisambiguationCandidate, PendingFlow
from domain.interfaces.data_repository import ContextRepository
from domain.services.date_resolver import parse_explicit_date, resolve_date_token
from domain.services.flow_state_store import FlowStateStore
from domain.services.pet_service import find_pets_by_term
from domain.services.text_matching import (
    is_cancel,
    name_tokens,
    normalize,
    resolve_ordinal,
)


# event_name slot: filler words dropped before requiring 1..6 content tokens.
_EVENT_NAME_FILLER = {
    "a", "o", "de", "da", "do", "vacina", "foi", "ele", "ela", "tomou",
}
_MAX_EVENT_NAME_TOKENS = 6

# date slot: filler words dropped before matching a relative/explicit date.
_DATE_FILLER = {"foi", "em", "no", "dia", "na", "verdade"}
_RELATIVE_DATE = {
    "hoje": "today",
    "ontem": "yesterday",
    "anteontem": "day_before_yesterday",
}

_MAX_PET_TOKENS = 5

# confirmation slot (delete_confirm).
_YES_TOKENS = {
    "sim", "pode", "apagar", "remover", "excluir", "confirmo", "confirmar",
    "ok", "claro", "isso", "mesmo", "s",
}
_STRONG_YES = {"sim", "pode", "confirmo", "ok", "claro", "s"}
_NO_TOKENS = {
    "nao", "cancelar", "cancela", "cancele", "deixa", "nenhum", "nenhuma",
    "esquece", "esqueci", "para",
}

# register_more ("tomou mais alguma?") loop tokens.
_MORE_NEGATIVE_ALLOWED = {
    "nao", "so", "esta", "essa", "apenas", "somente", "isso", "nada",
    "obrigado", "por", "enquanto",
}
_MORE_NEGATIVE_TRIGGER = {"nao", "so", "apenas", "somente"}
_MORE_YES = {"sim", "tomou", "aham", "uhum", "aha"}
_MORE_STRONG_YES = {"sim", "tomou", "aham", "uhum", "aha"}
_MORE_STRIP = _MORE_YES | {"a", "o", "de", "da", "do", "vacina", "e", "tambem"}


@dataclass
class SlotReplyResult:
    """Outcome of resolving a pet-health slot-filling reply."""

    kind: str  # "value" | "cancel" | "invalid" | "choose" | "affirm" | "none"
    value: object = None
    error_message: str = ""


def _clean_tokens(message: str) -> List[str]:
    """Split on whitespace and strip surrounding punctuation, keeping casing."""
    return [t.strip(string.punctuation) for t in message.split() if t.strip(string.punctuation)]


class PetHealthFlowService:
    _KEY_PREFIX = "pet_health_flow:"
    _FOCUS_PREFIX = "pet_health_focus:"
    _FLOW_DOMAIN = "pet_health"

    def __init__(self, context_repository: ContextRepository, ttl_seconds: int = 600):
        self.context_repository = context_repository
        self.ttl_seconds = ttl_seconds
        self._store = FlowStateStore(
            context_repository,
            key_prefix=self._KEY_PREFIX,
            focus_prefix=self._FOCUS_PREFIX,
            ttl_seconds=ttl_seconds,
        )

    # ------------------------------------------------------------------ #
    # Persistence — delegated to the generic FlowStateStore; this service
    # only owns the pet-health-specific (de)serialization of the payload.
    # ------------------------------------------------------------------ #
    async def set_pending(self, user_id: str, pending: PendingFlow) -> None:
        await self._store.set_pending(
            user_id,
            {
                "flow_domain": self._FLOW_DOMAIN,
                "operation": pending.operation,
                "slots": pending.slots,
                "missing_slots": pending.missing_slots,
                "candidates": [
                    {"id": c.id, "name": c.name} for c in pending.candidates
                ],
            },
        )

    async def get_pending(self, user_id: str) -> Optional[PendingFlow]:
        data = await self._store.get_pending_raw(user_id)
        if data is None:
            return None
        return PendingFlow(
            flow_domain=data.get("flow_domain", self._FLOW_DOMAIN),
            operation=data.get("operation", ""),
            slots=data.get("slots", {}) or {},
            missing_slots=data.get("missing_slots", []) or [],
            candidates=[
                DisambiguationCandidate(id=c.get("id", ""), name=c.get("name", ""))
                for c in data.get("candidates", [])
            ],
            expires_at=data.get("expires_at", 0.0),
        )

    async def clear_pending(self, user_id: str) -> None:
        await self._store.clear_pending(user_id)

    async def set_focus(self, user_id: str, focus: dict) -> None:
        await self._store.set_focus(user_id, focus)

    async def get_focus(self, user_id: str) -> Optional[dict]:
        return await self._store.get_focus(user_id)

    async def clear_focus(self, user_id: str) -> None:
        await self._store.clear_focus(user_id)

    # ------------------------------------------------------------------ #
    # Deterministic reply parsing (§9.3 + §2.6)
    # ------------------------------------------------------------------ #
    def parse_slot_reply(
        self,
        pending: PendingFlow,
        message: str,
        pets=None,
        *,
        reference: Optional[date] = None,
    ) -> SlotReplyResult:
        """
        ``reference`` is the civil date "hoje"/"ontem" are resolved against — the
        caller (LlmAppService) passes the USER's local date. None keeps the
        server's date, for callers that have no timezone to offer.
        """
        op = pending.operation

        if op == "delete_confirm":
            return self._parse_confirmation(message)

        if op == "register_more":
            return self._parse_register_more(message)

        if op == "choose_pet":
            if is_cancel(message):
                return SlotReplyResult(kind="cancel")
            return self._parse_choice(message, pending.candidates, pets or [])

        # register / edit — awaiting a data slot.
        if is_cancel(message):
            return SlotReplyResult(kind="cancel")

        expected = pending.missing_slots[0] if pending.missing_slots else None
        if expected == "event_name":
            return self._parse_event_name(message)
        if expected == "date":
            return self._parse_date(message, reference)
        if expected == "pet":
            return self._parse_pet(message, pets or [])
        return SlotReplyResult(kind="none")

    def _parse_event_name(self, message: str) -> SlotReplyResult:
        tokens = _clean_tokens(message)
        kept = [t for t in tokens if normalize(t) not in _EVENT_NAME_FILLER]
        if not kept or len(kept) > _MAX_EVENT_NAME_TOKENS:
            return SlotReplyResult(kind="none")
        return SlotReplyResult(kind="value", value=" ".join(kept))

    def _parse_date(
        self, message: str, reference: Optional[date] = None
    ) -> SlotReplyResult:
        reference = reference or date.today()
        content = [t for t in normalize(message).split() if t not in _DATE_FILLER]
        joined = " ".join(content)

        resolved: Optional[date] = None
        if joined in _RELATIVE_DATE:
            resolved = resolve_date_token(_RELATIVE_DATE[joined], reference)
        elif len(content) == 1:
            resolved = parse_explicit_date(content[0], reference)

        if resolved is None:
            return SlotReplyResult(kind="none")
        if resolved > reference:
            return SlotReplyResult(
                kind="invalid",
                error_message="Essa data está no futuro. Quando foi?",
            )
        return SlotReplyResult(kind="value", value=resolved)

    def _parse_pet(self, message: str, pets: List) -> SlotReplyResult:
        if len(name_tokens(message)) > _MAX_PET_TOKENS:
            return SlotReplyResult(kind="none")
        matched = find_pets_by_term(message, pets)
        if len(matched) == 1:
            return SlotReplyResult(kind="value", value=matched[0])
        if len(matched) > 1:
            return SlotReplyResult(kind="choose", value=matched)
        return SlotReplyResult(kind="none")

    def _parse_confirmation(self, message: str) -> SlotReplyResult:
        tokens = set(normalize(message).split())
        if len(tokens) <= 3 and (tokens & _NO_TOKENS):
            return SlotReplyResult(kind="cancel")
        if tokens and tokens <= _YES_TOKENS and (tokens & _STRONG_YES):
            return SlotReplyResult(kind="value", value=True)
        return SlotReplyResult(kind="none")

    def _parse_choice(
        self, message: str, candidates: List[DisambiguationCandidate], pets: List
    ) -> SlotReplyResult:
        if not candidates:
            return SlotReplyResult(kind="none")

        index = resolve_ordinal(message, len(candidates))
        if index is not None:
            return SlotReplyResult(kind="value", value=candidates[index])

        tokens = name_tokens(message)
        if tokens and len(tokens) <= _MAX_PET_TOKENS:
            matched = [c for c in candidates if tokens <= name_tokens(c.name)]
            if len(matched) == 1:
                return SlotReplyResult(kind="value", value=matched[0])

        # Resolve by nickname: map the term to a pet, then to its candidate.
        if pets:
            matched_pets = find_pets_by_term(message, pets)
            if len(matched_pets) == 1:
                pet_id = matched_pets[0].id
                by_id = [c for c in candidates if c.id == pet_id]
                if len(by_id) == 1:
                    return SlotReplyResult(kind="value", value=by_id[0])
        return SlotReplyResult(kind="none")

    def _parse_register_more(self, message: str) -> SlotReplyResult:
        if is_cancel(message):
            return SlotReplyResult(kind="cancel")

        tokens = _clean_tokens(message)
        norm_set = {normalize(t) for t in tokens}

        # Negative/limiter ("só esta", "não", "por enquanto não").
        if (
            norm_set
            and norm_set <= _MORE_NEGATIVE_ALLOWED
            and (norm_set & _MORE_NEGATIVE_TRIGGER)
        ):
            return SlotReplyResult(kind="cancel")

        # Bare affirmative ("sim", "tomou").
        if norm_set and norm_set <= _MORE_YES and (norm_set & _MORE_STRONG_YES):
            return SlotReplyResult(kind="affirm")

        # Affirmative with content ("sim, a raiva") -> the rest is the next name.
        if norm_set & _MORE_YES:
            kept = [t for t in tokens if normalize(t) not in _MORE_STRIP]
            if 1 <= len(kept) <= _MAX_EVENT_NAME_TOKENS:
                return SlotReplyResult(kind="value", value=" ".join(kept))

        return SlotReplyResult(kind="none")
