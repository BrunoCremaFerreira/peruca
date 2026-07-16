"""
MaintenanceFlowService — persists a multi-turn maintenance operation between
turns and resolves the user's next reply deterministically (no LLM).

The pending state is stored as a JSON payload under ``maintenance_flow:{user_id}``
in a ContextRepository, with the TTL embedded in the payload (mirroring
DisambiguationService). ``parse_slot_reply`` is the §9.3 conservative parser:
the whole message must BE the slot answer, otherwise it falls through (kind
"none") so a legitimate command is never swallowed.
"""

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from domain.entities import DisambiguationCandidate, PendingFlow
from domain.interfaces.data_repository import ContextRepository
from domain.services.date_resolver import parse_explicit_date, resolve_date_token
from domain.services.flow_state_store import FlowStateStore
from domain.services.text_matching import (
    _CANCEL_WORDS,
    is_cancel,
    name_tokens,
    normalize,
    resolve_ordinal,
)
from domain.services.vehicle_service import find_vehicles_by_term


# km slot: filler words dropped before requiring a single numeric token.
_KM_FILLER = {
    "km", "quilometragem", "com", "a", "estava", "esta", "foi", "em",
    "uns", "cerca", "de", "mil", "o", "carro",
}
_KM_SKIP_PHRASES = {"nao sei", "nao lembro", "sei la"}
_MAX_KM_TOKENS = 6
_MAX_ODOMETER_KM = 2_000_000

# date slot: filler words dropped before matching a relative/explicit date.
_DATE_FILLER = {"foi", "em", "no", "dia", "na", "verdade"}
_RELATIVE_DATE = {
    "hoje": "today",
    "ontem": "yesterday",
    "anteontem": "day_before_yesterday",
}

# confirmation slot (delete_confirm).
_YES_TOKENS = {
    "sim", "pode", "apagar", "remover", "excluir", "confirmo", "confirmar",
    "ok", "claro", "isso", "mesmo", "s",
}
_STRONG_YES = {"sim", "pode", "confirmo", "ok", "claro", "s"}
_NO_TOKENS = {"nao"} | _CANCEL_WORDS

_MAX_VEHICLE_TOKENS = 5

# Connector tokens dropped from a "sim, mas a km é 101000" amendment before the
# remainder is re-parsed as a slot correction.
_AMENDMENT_CONNECTORS = {"mas", "porem", "que", "entao", "e", "na", "verdade"}
_TOKEN_PUNCTUATION = ".,!?;:"

# register_receipt_confirm accepts "confirma" on top of the delete_confirm
# vocabulary (a registration is confirmed, not "apagado").
_RECEIPT_YES_TOKENS = (_YES_TOKENS | {"confirma"}) - {"apagar", "remover", "excluir"}
_RECEIPT_STRONG_YES = _STRONG_YES | {"confirma"}


@dataclass
class SlotReplyResult:
    """Outcome of resolving a slot-filling reply. See §9.3."""

    kind: str  # "value" | "skip" | "cancel" | "invalid" | "correction" | "choose" | "none"
    value: object = None
    corrected_slot: str = ""
    error_message: str = ""


class MaintenanceFlowService:
    _KEY_PREFIX = "maintenance_flow:"
    _FOCUS_PREFIX = "maintenance_focus:"

    _FLOW_DOMAIN = "maintenance"

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
    # Persistence — the mechanical JSON/TTL storage is delegated to the
    # generic FlowStateStore; this service only owns the maintenance-specific
    # (de)serialization of the pending payload.
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

    # ------------------------------------------------------------------ #
    # Focused record (§2.7): the record a query last reported on, so a
    # follow-up "altere a km desse registro" / "remova este registro" knows
    # which one. Stored as a plain dict with an embedded TTL.
    # ------------------------------------------------------------------ #
    async def set_focus(self, user_id: str, focus: dict) -> None:
        await self._store.set_focus(user_id, focus)

    async def get_focus(self, user_id: str) -> Optional[dict]:
        return await self._store.get_focus(user_id)

    async def clear_focus(self, user_id: str) -> None:
        await self._store.clear_focus(user_id)

    # ------------------------------------------------------------------ #
    # Deterministic reply parsing (§9.3)
    # ------------------------------------------------------------------ #
    def parse_slot_reply(
        self,
        pending: PendingFlow,
        message: str,
        vehicles=None,
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

        if op == "register_receipt_confirm":
            return self._parse_receipt_confirmation(message, pending, reference)

        if op == "choose_vehicle":
            if is_cancel(message):
                return SlotReplyResult(kind="cancel")
            return self._parse_choice(message, pending.candidates)

        # register / edit — awaiting a data slot.
        if is_cancel(message):
            return SlotReplyResult(kind="cancel")

        expected = pending.missing_slots[0] if pending.missing_slots else None
        if expected == "km":
            result = self._parse_km(message)
        elif expected == "date":
            result = self._parse_date(message, reference)
        elif expected == "vehicle":
            result = self._parse_vehicle(message, vehicles or [])
        else:
            result = SlotReplyResult(kind="none")

        if result.kind != "none":
            return result

        correction = self._try_correction(message, pending, expected, reference)
        if correction is not None:
            return correction
        return SlotReplyResult(kind="none")

    def _parse_receipt_confirmation(
        self,
        message: str,
        pending: PendingFlow,
        reference: Optional[date],
    ) -> SlotReplyResult:
        """
        Mirror of delete_confirm, plus the "sim, mas a km é 101000" case (§3.5):
        an affirmative carrying an amendment is a CORRECTION — the confirmation
        stays armed with the corrected slot, nothing is confirmed on this turn.
        An unrelated command falls through (kind "none") so it is never
        swallowed as a confirmation.
        """
        tokens = [
            t.strip(_TOKEN_PUNCTUATION) for t in normalize(message).split()
        ]
        tokens = [t for t in tokens if t]
        token_set = set(tokens)

        if token_set and len(token_set) <= 3 and (token_set & _NO_TOKENS):
            return SlotReplyResult(kind="cancel")
        if (
            token_set
            and token_set <= _RECEIPT_YES_TOKENS
            and (token_set & _RECEIPT_STRONG_YES)
        ):
            return SlotReplyResult(kind="value", value=True)

        # "sim, mas a km é 101000": an affirmative opening followed by content
        # is an amendment — re-parse the remainder as a correction.
        if tokens and tokens[0] in _RECEIPT_STRONG_YES:
            remainder = " ".join(
                t for t in tokens[1:] if t not in _AMENDMENT_CONNECTORS
            )
            if remainder:
                correction = self._try_correction(
                    remainder, pending, None, reference
                )
                if correction is not None:
                    return correction

        correction = self._try_correction(message, pending, None, reference)
        if correction is not None:
            return correction
        return SlotReplyResult(kind="none")

    def _try_correction(
        self,
        message: str,
        pending: PendingFlow,
        expected: Optional[str],
        reference: Optional[date],
    ) -> Optional[SlotReplyResult]:
        if expected != "date" and "date" in pending.slots:
            parsed = self._parse_date(message, reference)
            if parsed.kind == "value":
                return SlotReplyResult(
                    kind="correction", corrected_slot="date", value=parsed.value
                )
        if expected != "km" and "odometer_km" in pending.slots:
            parsed = self._parse_km(message)
            if parsed.kind == "value":
                return SlotReplyResult(
                    kind="correction", corrected_slot="km", value=parsed.value
                )
        return None

    def _parse_km(self, message: str) -> SlotReplyResult:
        norm = normalize(message)
        if norm in _KM_SKIP_PHRASES:
            return SlotReplyResult(kind="skip")

        raw = norm.split()
        if not raw or len(raw) > _MAX_KM_TOKENS:
            return SlotReplyResult(kind="none")

        multiplier = 1000 if "mil" in raw else 1
        remaining = [t.replace(".", "") for t in raw if t not in _KM_FILLER]
        if len(remaining) != 1 or not remaining[0].isdigit():
            return SlotReplyResult(kind="none")

        km = int(remaining[0]) * multiplier
        if not 0 < km <= _MAX_ODOMETER_KM:
            return SlotReplyResult(kind="none")
        return SlotReplyResult(kind="value", value=km)

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
                error_message="Essa data está no futuro. Quando foi a manutenção?",
            )
        return SlotReplyResult(kind="value", value=resolved)

    def _parse_vehicle(self, message: str, vehicles: List) -> SlotReplyResult:
        if len(name_tokens(message)) > _MAX_VEHICLE_TOKENS:
            return SlotReplyResult(kind="none")
        matched = find_vehicles_by_term(message, vehicles)
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
        self, message: str, candidates: List[DisambiguationCandidate]
    ) -> SlotReplyResult:
        if not candidates:
            return SlotReplyResult(kind="none")

        index = resolve_ordinal(message, len(candidates))
        if index is not None:
            return SlotReplyResult(kind="value", value=candidates[index])

        tokens = name_tokens(message)
        if tokens and len(tokens) <= _MAX_VEHICLE_TOKENS:
            matched = [c for c in candidates if tokens <= name_tokens(c.name)]
            if len(matched) == 1:
                return SlotReplyResult(kind="value", value=matched[0])
        return SlotReplyResult(kind="none")
