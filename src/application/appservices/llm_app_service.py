import asyncio
import logging
from infra import async_runner
from typing import Callable, Optional

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage

from application.appservices.prompt_sanitizer import sanitize_for_prompt
from application.appservices.view_models import ChatRequest
from application.graphs.main_graph import MainGraph
from domain.entities import GraphInvokeRequest, User
from domain.exceptions import EmptyParamValidationError, NofFoundValidationError
from domain.interfaces.data_repository import (
    ContextRepository,
    ConversationContextStore,
    UserRepository,
)
from domain.services.clock import local_date_for_user
from domain.services.user_memory_service import UserMemoryService
from domain.validations.image_validation import ImageValidator
from infra.utils import is_null_or_whitespace


logger = logging.getLogger(__name__)

_MUSIC_PROBE_TIMEOUT = 2.0

# The image description is model-generated from an attacker-controllable image
# (e.g. OCR of injected text). Before persisting it into the history we collapse
# newlines (so it cannot forge extra turns) and cap its length.
_MAX_IMAGE_DESCRIPTION_CHARS = 500


class LlmAppService:
    """
    LLM Application Service
    """

    def __init__(
        self,
        main_graph: MainGraph,
        context_repository: Optional[ContextRepository],
        user_repository: UserRepository,
        user_memory_service: UserMemoryService,
        music_service=None,
        get_session_history: Optional[
            Callable[[str], BaseChatMessageHistory]
        ] = None,
        shopping_list_service=None,
        disambiguation_service=None,
        image_store=None,
        maintenance_flow_service=None,
        maintenance_service=None,
        vehicle_read_repository=None,
        pet_health_flow_service=None,
        pet_health_service=None,
        pet_read_repository=None,
        user_settings_service=None,
        chat_image_max_bytes: int = 5_242_880,
        chat_image_max_count: int = 4,
        chat_image_allowed_mimes: Optional[list[str]] = None,
        conversation_context_store: Optional[ConversationContextStore] = None,
    ) -> None:
        self.main_graph = main_graph
        self.conversation_context_store = conversation_context_store
        self.context_repository = context_repository
        self.user_repository = user_repository
        self.user_memory_service = user_memory_service
        self.music_service = music_service
        self.get_session_history = get_session_history
        self.shopping_list_service = shopping_list_service
        self.disambiguation_service = disambiguation_service
        self.image_store = image_store
        self.maintenance_flow_service = maintenance_flow_service
        self.maintenance_service = maintenance_service
        self.vehicle_read_repository = vehicle_read_repository
        self.pet_health_flow_service = pet_health_flow_service
        self.pet_health_service = pet_health_service
        self.pet_read_repository = pet_read_repository
        self.user_settings_service = user_settings_service
        self.chat_image_max_bytes = chat_image_max_bytes
        self.chat_image_max_count = chat_image_max_count
        self.chat_image_allowed_mimes = chat_image_allowed_mimes or [
            "image/jpeg",
            "image/png",
            "image/webp",
        ]

    # ===============================================
    # Public Methods
    # ===============================================

    def chat(self, chat_request: ChatRequest) -> dict:
        # Never log the base64 image payloads (heavy + sensitive) — only their
        # count is recorded.
        logger.debug(
            "chat request: message=%r external_user_id=%r chat_id=%r images=%d",
            chat_request.message,
            chat_request.external_user_id,
            chat_request.chat_id,
            len(chat_request.images),
        )

        if is_null_or_whitespace(chat_request.external_user_id):
            raise EmptyParamValidationError(param_name="external_user_id")

        # Fail-fast image validation before any LLM cost (DoS guard). Only the
        # OnlyTalkGraph consumes images; here we just gatekeep the payload.
        if chat_request.images:
            ImageValidator(
                allowed_mimes=self.chat_image_allowed_mimes,
                max_bytes=self.chat_image_max_bytes,
                max_count=self.chat_image_max_count,
            ).validate_all(chat_request.images).validate()

        user = self.user_repository.get_by_external_id(
            external_id=chat_request.external_user_id
        )

        if not user:
            raise NofFoundValidationError(
                entity_name="user",
                key_name="external_id",
                value=chat_request.external_user_id,
            )

        # The user's timezone is resolved ONCE per request, here — this is the
        # single source of truth. Everything downstream (the graphs, the flow
        # services) receives it; nothing below reaches for the settings repository
        # or invents a default of its own.
        user_timezone = self._user_timezone(user)
        local_reference = (
            local_date_for_user(user_timezone) if user_timezone else None
        )

        # A pending disambiguation short-circuits normal routing: the user's
        # reply ("a primeira" / "carne de panela" / "cancelar") is resolved
        # deterministically without invoking the MainGraph (no extra LLM cost).
        if self.disambiguation_service is not None:
            pending = async_runner.run(
                self.disambiguation_service.get_pending(user.id)
            )
            if pending is not None:
                consumed = self._consume_disambiguation(
                    user, pending, chat_request.message
                )
                if consumed is not None:
                    return consumed

        # A pending multi-turn maintenance flow (register/edit/delete/
        # choose_vehicle) is consumed deterministically before the MainGraph
        # too. A reply that does not parse as the awaited slot clears the pending
        # and falls through to normal routing (§9.3).
        if self.maintenance_flow_service is not None:
            m_pending = async_runner.run(
                self.maintenance_flow_service.get_pending(user.id)
            )
            if m_pending is not None:
                consumed = self._consume_maintenance_flow(
                    user, m_pending, chat_request.message, local_reference
                )
                if consumed is not None:
                    return consumed

        # A pending pet-health flow (register slot-filling / choose_pet /
        # delete_confirm / register_more) is consumed the same way, dispatched by
        # its own key. A reply that does not parse clears it and falls through.
        if self.pet_health_flow_service is not None:
            p_pending = async_runner.run(
                self.pet_health_flow_service.get_pending(user.id)
            )
            if p_pending is not None:
                consumed = self._consume_pet_health_flow(
                    user, p_pending, chat_request.message, local_reference
                )
                if consumed is not None:
                    return consumed

        memories = self.user_memory_service.get_all_by_user(user.id)
        memory_contents = [memory.content for memory in memories]

        context_hints: dict = {}
        # Cheap query so the MainGraph classifier knows which vehicles exist
        # (resolves EX3/EX4: an unregistered vehicle mentioned in passing is
        # only_talking, §2.5).
        context_hints["user_vehicles"] = self._user_vehicles_hint(user.id)
        pets_hint, pets_persona = self._user_pets_hints(user.id)
        context_hints["user_pets"] = pets_hint
        context_hints["user_pets_persona"] = pets_persona
        if self.music_service is not None:
            try:
                players = async_runner.run(
                    asyncio.wait_for(
                        self.music_service.get_players(),
                        timeout=_MUSIC_PROBE_TIMEOUT,
                    )
                )
                music_is_playing = any(p.state == "playing" for p in players)
            except Exception:
                music_is_playing = False
            context_hints["music_is_playing"] = music_is_playing

        invoke_request = GraphInvokeRequest(
            message=chat_request.message,
            user=user,
            memories=memory_contents,
            context_hints=context_hints,
            images=chat_request.images,
            user_timezone=user_timezone,
        )
        result = self.main_graph.invoke(invoke_request=invoke_request)
        output = result.get("output")
        intents = result.get("intent")
        image_description = result.get("image_description")
        revised_image_index = result.get("revised_image_index")

        # Persist the base64 blobs (out of history) BEFORE writing the history
        # reference, so a #N handle never dangles. Returns the per-image handle
        # (N) or None when the blob was not stored (no store / save failure).
        image_handles = self._store_images(
            user, chat_request.images, image_description
        )

        # Re-vision enrichment (Fase C): a text-only follow-up (no new images)
        # that re-inspected image #N produces a refreshed description. Persist it
        # under that handle so repeated follow-ups on the same detail stay cheap.
        if (
            not chat_request.images
            and revised_image_index is not None
            and not is_null_or_whitespace(image_description)
        ):
            image_handles = [revised_image_index]

        self._persist_turn(
            user=user,
            message=chat_request.message,
            output=output,
            image_description=image_description,
            image_handles=image_handles,
        )

        logger.debug("chat response: %s", result)
        return {"intents": intents, "output": output}

    def reset_context(self, user_id: str) -> None:
        """
        Reset a user's conversation history (the same chat_history OnlyTalkGraph
        reads and _persist_turn writes). REST-only action, not reachable via
        chat. Unlike the best-effort _persist_turn, any exception from clear()
        propagates so the caller can surface a real failure.

        Store-first: the conversation context store owns the history AND the
        compaction summary, so a single clear() wipes both — clearing only the
        history would leave Peruca "remembering" a conversation the user asked to
        erase. A failing store never falls back to a partial reset.
        """
        if self.conversation_context_store is not None:
            self.conversation_context_store.clear(user_id)
            return
        if self.get_session_history is None:
            return
        self.get_session_history(user_id).clear()

    # ===============================================
    # Private Methods
    # ===============================================

    _OPERATION_LABELS = {
        "delete": "Removido",
        "check": "Marcado como comprado",
        "uncheck": "Desmarcado",
    }

    def _user_timezone(self, user: User) -> str:
        """
        The user's IANA timezone (the service falls back to the default injected
        by the composition root). Empty when no settings service is wired — the
        graphs that need a timezone then fail loudly instead of silently using a
        made-up one.
        """
        if self.user_settings_service is None:
            return ""
        return self.user_settings_service.get_timezone(user.id)

    def _consume_disambiguation(self, user: User, pending, message: str):
        """
        Resolve a follow-up reply against a pending disambiguation.

        Returns the final chat response dict for "match"/"cancel", or None for
        "none" (the caller then falls through to the MainGraph with the original
        message).
        """
        result = self.disambiguation_service.resolve_choice(
            message, pending.candidates
        )

        if result.kind == "cancel":
            async_runner.run(self.disambiguation_service.clear_pending(user.id))
            output = "Ok, cancelei."
            self._persist_turn(user=user, message=message, output=output)
            return {"intents": ["shopping_list"], "output": output}

        if result.kind == "match":
            candidate = result.candidate
            self._apply_operation(pending.operation, candidate.id)
            async_runner.run(self.disambiguation_service.clear_pending(user.id))
            label = self._OPERATION_LABELS.get(pending.operation, "Feito")
            output = f"{label}: {candidate.name}"
            self._persist_turn(user=user, message=message, output=output)
            return {"intents": ["shopping_list"], "output": output}

        # kind == "none": the user ignored the question — drop the pending state
        # and let the original message route normally.
        async_runner.run(self.disambiguation_service.clear_pending(user.id))
        return None

    def _user_vehicles_hint(self, user_id: str) -> str:
        if self.vehicle_read_repository is None:
            return "nenhum"
        try:
            vehicles = self.vehicle_read_repository.get_all_by_user_id(user_id)
        except Exception as error:  # noqa: BLE001
            logger.warning("user_vehicles hint failed: %s", error)
            return "nenhum"
        names = ", ".join(v.name for v in vehicles if v.name)
        return names or "nenhum"

    def _user_pets_hints(self, user_id: str):
        """
        Return (classifier_hint, persona_block) from a single repository read.
        The classifier hint is a compact "Name (alias, alias)" list so the
        MainGraph can route pet mentions; the persona block is the multi-line
        "sibling" description injected into the OnlyTalkGraph (§2.9).
        """
        if self.pet_read_repository is None:
            return "nenhum", ""
        try:
            pets = self.pet_read_repository.get_all_by_user_id(user_id) or []
        except Exception as error:  # noqa: BLE001
            logger.warning("user_pets hint failed: %s", error)
            return "nenhum", ""

        hint_parts = []
        persona_lines = []
        for pet in pets:
            if not pet.name:
                continue
            name = sanitize_for_prompt(pet.name, 40)
            aliases = ", ".join(
                sanitize_for_prompt(n, 40) for n in (pet.nicknames or []) if n
            )
            hint_parts.append(f"{name} ({aliases})" if aliases else name)
            alias_part = f" (apelidos: {aliases})" if aliases else ""
            desc = sanitize_for_prompt(pet.description or "", 200)
            desc_part = f": {desc}" if desc else ""
            persona_lines.append(f"- **{name}**{alias_part}{desc_part}")

        hint = ", ".join(hint_parts) or "nenhum"
        persona = "\n".join(persona_lines)
        return hint, persona

    def _consume_maintenance_flow(
        self, user: User, pending, message: str, reference=None
    ):
        """
        Resolve a reply against a pending maintenance flow. Returns a final chat
        response dict, or None to fall through to the MainGraph (§9.3).

        ``reference`` is the user's local civil date: "ontem" in a multi-turn flow
        must mean the same day it means inside the graphs.
        """
        fleet = (
            self.vehicle_read_repository.get_all_by_user_id(user.id)
            if self.vehicle_read_repository is not None
            else []
        )
        result = self.maintenance_flow_service.parse_slot_reply(
            pending, message, vehicles=fleet, reference=reference
        )

        if result.kind == "none":
            async_runner.run(self.maintenance_flow_service.clear_pending(user.id))
            return None

        if result.kind == "cancel":
            async_runner.run(self.maintenance_flow_service.clear_pending(user.id))
            return self._flow_reply(user, message, "Ok, cancelei.")

        if result.kind == "invalid":
            # Keep the pending state and re-ask deterministically.
            return self._flow_reply(
                user, message, result.error_message or "Não entendi, pode repetir?"
            )

        if pending.operation == "delete_confirm":
            async_runner.run(self.maintenance_flow_service.clear_pending(user.id))
            if result.kind == "value" and result.value is True:
                output = self._delete_focused_record(user, pending)
            else:
                output = "Ok."
            return self._flow_reply(user, message, output)

        if pending.operation == "register_receipt_confirm":
            from domain.entities import PendingFlow

            if result.kind == "correction":
                # "Sim, mas a km é 101000": keep the confirmation armed with
                # the corrected slot — nothing is persisted on this turn.
                slots = dict(pending.slots)
                if result.corrected_slot == "date":
                    slots["date"] = result.value.isoformat()
                elif result.corrected_slot == "km":
                    slots["odometer_km"] = result.value
                async_runner.run(
                    self.maintenance_flow_service.set_pending(
                        user.id,
                        PendingFlow(
                            operation="register_receipt_confirm", slots=slots
                        ),
                    )
                )
                return self._flow_reply(
                    user, message, self._receipt_confirm_question(slots)
                )
            async_runner.run(self.maintenance_flow_service.clear_pending(user.id))
            if result.kind == "value" and result.value is True:
                output = self._register_maintenance_from_slots(user, pending.slots)
            else:
                output = "Ok."
            return self._flow_reply(user, message, output)

        if pending.operation == "choose_vehicle":
            if result.kind == "value":
                slots = dict(pending.slots)
                slots["vehicle_id"] = result.value.id
                slots["vehicle_name"] = result.value.name
                # A receipt-born disambiguation stays on the receipt path: it
                # must end in register_receipt_confirm, never persist directly.
                operation = (
                    "register_receipt" if slots.get("from_receipt") else "register"
                )
                return self._advance_register(
                    user, slots, ["date", "km"], message, operation=operation
                )
            async_runner.run(self.maintenance_flow_service.clear_pending(user.id))
            return None

        # register / register_receipt / edit slot filling.
        slots = dict(pending.slots)
        missing = list(pending.missing_slots)
        operation = (
            "register_receipt"
            if pending.operation == "register_receipt"
            else "register"
        )

        if result.kind == "correction":
            if result.corrected_slot == "date":
                slots["date"] = result.value.isoformat()
            elif result.corrected_slot == "km":
                slots["odometer_km"] = result.value
            return self._advance_register(
                user, slots, missing, message, operation=operation
            )

        current = missing[0] if missing else None
        if current == "date":
            slots["date"] = result.value.isoformat() if result.kind == "value" else None
        elif current == "km":
            slots["odometer_km"] = result.value if result.kind == "value" else None
        elif current == "vehicle":
            if result.kind == "choose":
                # Still ambiguous: keep asking, store a choose_vehicle flow.
                from domain.entities import (
                    DisambiguationCandidate,
                    PendingFlow,
                )

                names = " ou ".join(v.name for v in result.value)
                async_runner.run(
                    self.maintenance_flow_service.set_pending(
                        user.id,
                        PendingFlow(
                            operation="choose_vehicle",
                            slots=slots,
                            candidates=[
                                DisambiguationCandidate(id=v.id, name=v.name)
                                for v in result.value
                            ],
                        ),
                    )
                )
                return self._flow_reply(user, message, f"Qual deles? {names}?")
            slots["vehicle_id"] = result.value.id
            slots["vehicle_name"] = result.value.name

        return self._advance_register(
            user, slots, missing[1:], message, operation=operation
        )

    def _advance_register(
        self,
        user: User,
        slots: dict,
        remaining: list,
        message: str,
        operation: str = "register",
    ):
        """
        Ask for the next missing slot, or finish the flow when the slot queue is
        empty: a "register" flow persists right away; a "register_receipt" flow
        arms the mandatory confirmation turn instead (§3.5) — there is no code
        path from a receipt to persistence without the user's "sim".
        """
        from domain.entities import PendingFlow

        # Recompute what is still missing so a slot filled by a correction is not
        # asked again.
        pending_missing = [
            s
            for s in remaining
            if (s == "date" and not slots.get("date"))
            or (s == "km" and slots.get("odometer_km") is None)
            or (s == "vehicle" and not slots.get("vehicle_id"))
        ]

        if pending_missing:
            async_runner.run(
                self.maintenance_flow_service.set_pending(
                    user.id,
                    PendingFlow(
                        operation=operation,
                        slots=slots,
                        missing_slots=pending_missing,
                    ),
                )
            )
            questions = {
                "vehicle": "De qual veículo?",
                "date": "Quando foi?",
                "km": "Qual a quilometragem no momento?",
            }
            return self._flow_reply(
                user, message, questions.get(pending_missing[0], "Pode me dar esse dado?")
            )

        if operation == "register_receipt":
            async_runner.run(
                self.maintenance_flow_service.set_pending(
                    user.id,
                    PendingFlow(operation="register_receipt_confirm", slots=slots),
                )
            )
            return self._flow_reply(
                user, message, self._receipt_confirm_question(slots)
            )

        async_runner.run(self.maintenance_flow_service.clear_pending(user.id))
        return self._flow_reply(
            user, message, self._register_maintenance_from_slots(user, slots)
        )

    def _register_maintenance_from_slots(self, user: User, slots: dict) -> str:
        from datetime import date as _date

        from domain.commands import MaintenanceRecordAdd

        performed_at = (
            _date.fromisoformat(slots["date"]) if slots.get("date") else None
        )
        try:
            self.maintenance_service.register(
                MaintenanceRecordAdd(
                    vehicle_id=slots.get("vehicle_id"),
                    description=slots.get("description") or "",
                    performed_at=performed_at,
                    odometer_km=slots.get("odometer_km"),
                ),
                user.id,
            )
        except Exception as error:  # noqa: BLE001
            logger.error("flow register failed: %s", error, exc_info=True)
            return "Não consegui registrar essa manutenção."

        name = slots.get("vehicle_name") or "veículo"
        return f"Registrei {slots.get('description')} para o {name}."

    @staticmethod
    def _receipt_confirm_question(slots: dict) -> str:
        from datetime import date as _date

        name = slots.get("vehicle_name") or "veículo"
        description = slots.get("description") or "a manutenção"
        date_part = ""
        if slots.get("date"):
            when = _date.fromisoformat(slots["date"]).strftime("%d/%m/%Y")
            date_part = f", em {when}"
        km = slots.get("odometer_km")
        km_part = f", com km {km}" if km is not None else ""
        return f"Registro então {description} para o {name}{date_part}{km_part}?"

    def _delete_focused_record(self, user: User, pending) -> str:
        record_id = pending.slots.get("record_id")
        if not record_id or self.maintenance_service is None:
            return "Não encontrei o registro para remover."
        try:
            self.maintenance_service.delete(record_id, user.id)
        except Exception as error:  # noqa: BLE001
            logger.error("flow delete failed: %s", error, exc_info=True)
            return "Não consegui remover o registro."
        # The record is gone — drop the stale focus so a later "esse registro"
        # does not point at a deleted row.
        try:
            async_runner.run(self.maintenance_flow_service.clear_focus(user.id))
        except Exception:  # noqa: BLE001
            pass
        return "Removido."

    def _flow_reply(self, user: User, message: str, output: str) -> dict:
        self._persist_turn(user=user, message=message, output=output)
        return {"intents": ["vehicle_maintenance"], "output": output}

    # ===============================================
    # Pet health flow (§2.5 / §2.6)
    # ===============================================
    def _consume_pet_health_flow(
        self, user: User, pending, message: str, reference=None
    ):
        """
        Resolve a reply against a pending pet-health flow. Returns a final chat
        response dict, or None to fall through to the MainGraph (§9.3).

        ``reference`` is the user's local civil date, as in the maintenance flow.
        """
        pets = (
            self.pet_read_repository.get_all_by_user_id(user.id)
            if self.pet_read_repository is not None
            else []
        )
        result = self.pet_health_flow_service.parse_slot_reply(
            pending, message, pets=pets, reference=reference
        )
        op = pending.operation

        if result.kind == "none":
            async_runner.run(self.pet_health_flow_service.clear_pending(user.id))
            return None

        if result.kind == "cancel":
            async_runner.run(self.pet_health_flow_service.clear_pending(user.id))
            closing = "Perfeito então." if op == "register_more" else "Ok, cancelei."
            return self._pet_reply(user, message, closing)

        if result.kind == "invalid":
            return self._pet_reply(
                user, message, result.error_message or "Não entendi, pode repetir?"
            )

        if op == "delete_confirm":
            async_runner.run(self.pet_health_flow_service.clear_pending(user.id))
            if result.kind == "value" and result.value is True:
                output = self._delete_focused_pet_record(user, pending)
            else:
                output = "Ok."
            return self._pet_reply(user, message, output)

        if op == "choose_pet":
            if result.kind == "value":
                slots = dict(pending.slots)
                slots["pet_id"] = result.value.id
                slots["pet_name"] = result.value.name
                return self._advance_pet_register(user, slots, message)
            async_runner.run(self.pet_health_flow_service.clear_pending(user.id))
            return None

        if op == "register_more":
            from domain.entities import PendingFlow

            if result.kind == "affirm":
                slots = {
                    "pet_id": pending.slots.get("pet_id"),
                    "pet_name": pending.slots.get("pet_name"),
                    "event_type": pending.slots.get("event_type") or "vaccine",
                    "event_name": None,
                    "date": pending.slots.get("date"),
                }
                async_runner.run(
                    self.pet_health_flow_service.set_pending(
                        user.id,
                        PendingFlow(
                            operation="register",
                            slots=slots,
                            missing_slots=["event_name"],
                            flow_domain="pet_health",
                        ),
                    )
                )
                return self._pet_reply(user, message, "Qual outra vacina?")
            if result.kind == "value":
                slots = dict(pending.slots)
                slots["event_name"] = result.value
                return self._advance_pet_register(user, slots, message)
            async_runner.run(self.pet_health_flow_service.clear_pending(user.id))
            return None

        # register slot filling.
        from domain.entities import DisambiguationCandidate, PendingFlow

        slots = dict(pending.slots)
        missing = list(pending.missing_slots)
        current = missing[0] if missing else None

        if current == "pet":
            if result.kind == "choose":
                names = " ou ".join(p.name for p in result.value)
                async_runner.run(
                    self.pet_health_flow_service.set_pending(
                        user.id,
                        PendingFlow(
                            operation="choose_pet",
                            slots=slots,
                            candidates=[
                                DisambiguationCandidate(id=p.id, name=p.name)
                                for p in result.value
                            ],
                            flow_domain="pet_health",
                        ),
                    )
                )
                return self._pet_reply(user, message, f"De qual deles? {names}?")
            slots["pet_id"] = result.value.id
            slots["pet_name"] = result.value.name
        elif current == "event_name":
            slots["event_name"] = result.value if result.kind == "value" else None
        elif current == "date":
            slots["date"] = (
                result.value.isoformat() if result.kind == "value" else None
            )

        return self._advance_pet_register(user, slots, message)

    def _advance_pet_register(self, user: User, slots: dict, message: str):
        """
        Ask for the next missing slot, or register the event when the slot queue
        is empty. After a vaccine registers, arm the "tomou mais alguma?" loop
        (§2.6).
        """
        from datetime import date as _date

        from domain.commands import PetHealthEventAdd
        from domain.entities import PendingFlow

        missing = []
        if not slots.get("pet_id"):
            missing.append("pet")
        if not slots.get("event_name"):
            missing.append("event_name")
        if not slots.get("date"):
            missing.append("date")

        if missing:
            async_runner.run(
                self.pet_health_flow_service.set_pending(
                    user.id,
                    PendingFlow(
                        operation="register",
                        slots=slots,
                        missing_slots=missing,
                        flow_domain="pet_health",
                    ),
                )
            )
            event_type = slots.get("event_type") or ""
            questions = {
                "pet": "De qual pet estamos falando?",
                "event_name": "Qual vacina ele tomou?"
                if event_type == "vaccine"
                else "O que foi aplicado exatamente?",
                "date": "Quando foi?",
            }
            return self._pet_reply(
                user, message, questions.get(missing[0], "Pode me dar esse dado?")
            )

        async_runner.run(self.pet_health_flow_service.clear_pending(user.id))
        occurred_at = (
            _date.fromisoformat(slots["date"]) if slots.get("date") else None
        )
        event_type = slots.get("event_type") or "other"
        try:
            self.pet_health_service.register(
                PetHealthEventAdd(
                    pet_id=slots.get("pet_id"),
                    event_type=event_type,
                    description=slots.get("event_name") or "",
                    occurred_at=occurred_at,
                ),
                user.id,
            )
        except Exception as error:  # noqa: BLE001
            logger.error("pet flow register failed: %s", error, exc_info=True)
            return self._pet_reply(
                user, message, "Não consegui registrar esse evento de saúde."
            )

        name = slots.get("pet_name") or "pet"
        when = occurred_at.strftime("%d/%m/%Y") if occurred_at else "?"
        confirm = f"Registrei {slots.get('event_name')} para o {name}, no dia {when}."

        # Vaccines come in batches — offer to register another (§2.6). Other
        # event types confirm and end.
        if event_type == "vaccine":
            async_runner.run(
                self.pet_health_flow_service.set_pending(
                    user.id,
                    PendingFlow(
                        operation="register_more",
                        slots={
                            "pet_id": slots.get("pet_id"),
                            "pet_name": name,
                            "event_type": "vaccine",
                            "date": slots.get("date"),
                        },
                        flow_domain="pet_health",
                    ),
                )
            )
            return self._pet_reply(user, message, f"{confirm} Tomou mais alguma?")
        return self._pet_reply(user, message, confirm)

    def _delete_focused_pet_record(self, user: User, pending) -> str:
        record_id = pending.slots.get("record_id")
        if not record_id or self.pet_health_service is None:
            return "Não encontrei o registro para remover."
        try:
            self.pet_health_service.delete(record_id, user.id)
        except Exception as error:  # noqa: BLE001
            logger.error("pet flow delete failed: %s", error, exc_info=True)
            return "Não consegui remover o registro."
        try:
            async_runner.run(self.pet_health_flow_service.clear_focus(user.id))
        except Exception:  # noqa: BLE001
            pass
        return "Removido."

    def _pet_reply(self, user: User, message: str, output: str) -> dict:
        self._persist_turn(user=user, message=message, output=output)
        return {"intents": ["pet_health"], "output": output}

    def _apply_operation(self, operation: str, item_id: str) -> None:
        operations = {
            "delete": self.shopping_list_service.delete,
            "check": self.shopping_list_service.check,
            "uncheck": self.shopping_list_service.uncheck,
        }
        apply = operations.get(operation)
        if apply is not None:
            apply(item_id)

    def _store_images(
        self, user: User, images: list[str], image_description: Optional[str]
    ) -> list:
        """
        Save each inbound image blob to the image store and return its stable
        per-user handle N (or None when it was not stored). Nothing is stored
        when there is no store, no images, or no description (a plain text turn).
        """
        if (
            self.image_store is None
            or not images
            or is_null_or_whitespace(image_description)
        ):
            return [None] * len(images or [])

        handles = []
        for data_uri in images:
            handle = None
            try:
                index = self.image_store.next_index(user.id)
                self.image_store.save(user.id, str(index), data_uri)
                handle = index
            except Exception as error:
                logger.error("Failed to store image: %s", error, exc_info=True)
                handle = None
            handles.append(handle)
        return handles

    def _persist_turn(
        self,
        user: User,
        message: str,
        output: Optional[str],
        image_description: Optional[str] = None,
        image_handles: Optional[list] = None,
    ) -> None:
        if self.get_session_history is None:
            return

        if is_null_or_whitespace(output):
            return

        # The base64 image never enters the history — only a factual textual
        # description, so later turns keep visual context without exploding the
        # context window.
        human_content = self._build_human_history_content(
            message, image_description, image_handles
        )

        try:
            history = self.get_session_history(user.id)
            history.add_messages(
                [HumanMessage(content=human_content), AIMessage(content=output)]
            )
        except Exception as error:
            logger.error("Failed to persist turn: %s", error, exc_info=True)

    @staticmethod
    def _build_human_history_content(
        message: str,
        image_description: Optional[str],
        image_handles: Optional[list] = None,
    ) -> str:
        if not image_description:
            return message
        safe_description = LlmAppService._sanitize_description(image_description)
        # One bracket line per image. A stored image carries its #N handle (so a
        # later turn can re-inspect its pixels); an unstored one degrades to a
        # handle-less line.
        handles = image_handles if image_handles else [None]
        lines = []
        for handle in handles:
            if handle is not None:
                lines.append(
                    f"[Imagem #{handle} enviada pelo usuário: {safe_description}]"
                )
            else:
                lines.append(
                    f"[Imagem enviada pelo usuário: {safe_description}]"
                )
        bracket = "\n".join(lines)
        if is_null_or_whitespace(message):
            return bracket
        return f"{message}\n{bracket}"

    @staticmethod
    def _sanitize_description(description: str) -> str:
        # Delegates to the shared prompt sanitizer: collapse ALL whitespace so an
        # image-derived description cannot forge extra history lines/turns, then
        # cap the length to bound context growth and injection surface.
        return sanitize_for_prompt(description, _MAX_IMAGE_DESCRIPTION_CHARS)
