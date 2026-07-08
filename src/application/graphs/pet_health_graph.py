import json
import logging
from datetime import date
from typing import List, Optional, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph

from application.appservices.prompt_sanitizer import sanitize_for_prompt
from application.graphs.graph import Graph
from domain.commands import PetHealthEventAdd, PetHealthEventUpdate
from domain.entities import (
    DisambiguationCandidate,
    GraphInvokeRequest,
    Pet,
    PendingFlow,
)
from domain.exceptions import ValidationError
from domain.services.date_resolver import (
    parse_explicit_date,
    resolve_date_token,
    resolve_period,
)
from domain.services.pet_service import find_pets_by_term
from infra import async_runner


logger = logging.getLogger(__name__)

_FORBIDDEN_MESSAGE = "Não tenho permissão para realizar esta operação"
_QUERY_RECORD_LIMIT = 20
_MAX_RECORD_DESCRIPTION_CHARS = 200


class PetHealthGraphState(TypedDict, total=False):
    input: GraphInvokeRequest
    intent: Optional[List[str]]
    pet_term: Optional[str]
    event_type: Optional[str]
    event_name: Optional[str]
    resolved_occurred_at: Optional[date]
    resolved_period: Optional[tuple]
    query: Optional[str]
    query_kind: Optional[str]
    query_limit: Optional[int]
    edit_field: Optional[str]
    new_value: Optional[str]
    matched_pets: Optional[List[Pet]]
    output_list: Optional[str]
    output_register: Optional[str]
    output_query: Optional[str]
    output_edit: Optional[str]
    output_delete: Optional[str]
    output_forbidden: Optional[str]
    output_not_recognized: Optional[str]
    output: Optional[str]


class PetHealthGraph(Graph):
    """
    Pet health graph: lists pets, registers/queries/edits/removes health events
    (vaccines, dewormers, vet visits...), and refuses pet writes over chat. Pet
    resolution and date arithmetic are deterministic (Python); the LLM only
    classifies + extracts and, for open queries, phrases the answer.

    It receives ONLY a PetReadRepository — no code path here can write a pet
    (§2.4).
    """

    def __init__(
        self,
        llm_chat: BaseChatModel,
        pet_read_repository,
        pet_health_service,
        pet_health_flow_service,
        get_session_history=None,
        provider: str = "OLLAMA",
        strip_think_directive: bool = False,
    ):
        super().__init__(provider, strip_think_directive)
        self.llm_chat = llm_chat
        self.pet_read_repository = pet_read_repository
        self.pet_health_service = pet_health_service
        self.pet_health_flow_service = pet_health_flow_service
        self.get_session_history = get_session_history
        self.classification_prompt = ChatPromptTemplate.from_template(
            self.load_prompt("pet_health_graph.md")
        )
        self.query_response_prompt = ChatPromptTemplate.from_template(
            self.load_prompt("pet_health_graph_query_response.md")
        )

    # ===============================================
    # Graph Nodes
    # ===============================================
    def _classify_intent(self, data):
        request: GraphInvokeRequest = data["input"]
        user = request.user
        pets = self._pets(user.id)
        available = self._render_available_pets(pets)

        payload = {
            "input": request.message,
            "current_date": date.today().isoformat(),
            "available_pets": available,
            "history": self._recent_history(user.id),
        }
        chain = self.classification_prompt | self.llm_chat
        try:
            response = chain.invoke(payload)
        except KeyError:
            response = chain.invoke({"input": request.message})

        extracted = self._extract_structured_output(response.content)
        parsed = {}
        if extracted:
            try:
                loaded = json.loads(extracted)
                if isinstance(loaded, dict):
                    parsed = loaded
            except (json.JSONDecodeError, ValueError):
                parsed = {}

        intents = parsed.get("intents") or ["not_recognized"]
        if isinstance(intents, str):
            intents = [intents]

        pet_term = (parsed.get("pet_term") or "").strip()
        occurred_at = self._resolve_date(
            parsed.get("date_token") or "", parsed.get("date_value") or ""
        )
        period = resolve_period(parsed.get("period") or "", date.today())

        return {
            "intent": intents,
            "input": request,
            "pet_term": pet_term,
            "event_type": (parsed.get("event_type") or "").strip(),
            "event_name": (parsed.get("event_name") or "").strip(),
            "resolved_occurred_at": occurred_at,
            "resolved_period": period,
            "query": (parsed.get("query") or "").strip(),
            "query_kind": (parsed.get("query_kind") or "").strip(),
            "query_limit": self._coerce_int(parsed.get("query_limit")),
            "edit_field": (parsed.get("edit_field") or "").strip(),
            "new_value": (parsed.get("new_value") or "").strip(),
            "matched_pets": find_pets_by_term(pet_term, pets) if pet_term else [],
        }

    def _handle_list_pets(self, data):
        user = data["input"].user
        pets = self._pets(user.id)
        if not pets:
            return {"output_list": "Você ainda não tem nenhum pet cadastrado."}
        names = ", ".join(p.name for p in pets)
        return {
            "output_list": (
                f"Os seus pets são: {names}. Quer registrar alguma vacina ou "
                "consultar o histórico de algum deles?"
            )
        }

    def _handle_pet_write_forbidden(self, data):
        return {"output_forbidden": _FORBIDDEN_MESSAGE}

    def _handle_register_health_event(self, data):
        user = data["input"].user
        term = data.get("pet_term") or ""
        pets = self._pets(user.id)
        matched = data.get("matched_pets")
        if matched is None:
            matched = find_pets_by_term(term, pets) if term else []

        event_type = data.get("event_type") or "other"
        event_name = data.get("event_name") or ""
        occurred_at = data.get("resolved_occurred_at")

        pet = None
        if len(matched) == 1:
            pet = matched[0]
        elif len(matched) > 1:
            names = " ou ".join(p.name for p in matched)
            self._store_flow(
                user,
                PendingFlow(
                    operation="choose_pet",
                    slots=self._register_slots(None, event_type, event_name, occurred_at),
                    candidates=[
                        DisambiguationCandidate(id=p.id, name=p.name) for p in matched
                    ],
                ),
            )
            return {"output_register": f"De qual deles? {names}?"}
        elif term:
            # A non-empty term with no match: the pet is not registered. Never
            # offer to create it (§2.4).
            return {
                "output_register": f"Você não tem nenhum pet chamado {term}."
            }

        slots = self._register_slots(pet, event_type, event_name, occurred_at)
        missing = []
        if not pet:
            missing.append("pet")
        if not event_name:
            missing.append("event_name")
        if not occurred_at:
            missing.append("date")

        if missing:
            self._store_flow(
                user,
                PendingFlow(
                    operation="register", slots=slots, missing_slots=missing
                ),
            )
            return {"output_register": self._ask_for_slot(missing[0], event_type)}

        return {"output_register": self._do_register(user, pet, event_type, event_name, occurred_at)}

    def _handle_query_health_event(self, data):
        user = data["input"].user
        term = data.get("pet_term") or ""
        pets = self._pets(user.id)
        matched = find_pets_by_term(term, pets) if term else []

        if not matched:
            if term:
                return {"output_query": f"Você não tem nenhum pet chamado {term}."}
            return {"output_query": "De qual pet você quer saber?"}
        if len(matched) > 1:
            names = " ou ".join(p.name for p in matched)
            return {"output_query": f"De qual deles? {names}?"}
        pet = matched[0]

        # Hard ceiling: never fetch or render more than _QUERY_RECORD_LIMIT records
        # regardless of the query_limit the LLM emits (§9.4).
        requested = data.get("query_limit") or 0
        records = self.pet_health_service.get_by_pet(
            pet.id, user.id, limit=_QUERY_RECORD_LIMIT
        )

        period = data.get("resolved_period")
        if period:
            start, end = period
            records = [
                r for r in records if r.occurred_at and start <= r.occurred_at <= end
            ]

        if requested:
            records = records[: min(requested, _QUERY_RECORD_LIMIT)]

        if not records:
            return {
                "output_query": (
                    f"Não encontrei nenhum registro de saúde para o {pet.name}."
                )
            }

        # Remember the most recent record reported for a follow-up edit/delete (§2.7).
        self._set_focus(user, pet, records[0])

        if (data.get("query_kind") or "") == "open":
            return {"output_query": self._render_open(user, pet, data, records)}
        return {"output_query": self._render_records(pet, records)}

    def _handle_edit_health_event(self, data):
        user = data["input"].user
        focus = self._get_focus(user)
        if not focus:
            return {
                "output_edit": (
                    "Não sei a qual registro você se refere. Consulte o histórico "
                    "primeiro e depois peça a alteração."
                )
            }
        update, human = self._build_edit(
            focus, (data.get("edit_field") or ""), (data.get("new_value") or "")
        )
        if update is None:
            return {
                "output_edit": "Não entendi o que você quer alterar nesse registro."
            }
        try:
            self.pet_health_service.update(update, user.id)
        except ValidationError as error:
            return {"output_edit": f"Não consegui alterar: {error.errors}"}
        except Exception as error:  # noqa: BLE001
            logger.error("edit_health_event failed: %s", error, exc_info=True)
            return {"output_edit": "Tive um problema ao alterar, tente de novo."}
        return {"output_edit": human}

    def _handle_delete_health_event(self, data):
        user = data["input"].user
        focus = self._get_focus(user)
        if not focus:
            return {
                "output_delete": (
                    "Não sei qual registro remover. Consulte o histórico primeiro "
                    "para eu confirmar a remoção."
                )
            }
        self._store_flow(
            user,
            PendingFlow(
                operation="delete_confirm",
                slots={
                    "record_id": focus.get("record_id"),
                    "pet_name": focus.get("pet_name"),
                    "description": focus.get("description"),
                },
            ),
        )
        when = self._format_iso(focus.get("occurred_at"))
        return {
            "output_delete": (
                f"Devo remover o registro de {focus.get('description')} do "
                f"{focus.get('pet_name')}, de {when}?"
            )
        }

    def _handle_not_recognized(self, data):
        return {
            "output_not_recognized": (
                "Não entendi o que você quer fazer com a saúde do pet."
            )
        }

    def _handle_final_response(self, data):
        outputs = [
            e
            for e in [
                data.get("output_list"),
                data.get("output_register"),
                data.get("output_query"),
                data.get("output_edit"),
                data.get("output_delete"),
                data.get("output_forbidden"),
                data.get("output_not_recognized"),
            ]
            if isinstance(e, str) and e.strip()
        ]
        response = (
            "\n\n".join(outputs) if len(outputs) > 1 else (outputs[0] if outputs else "")
        )
        return {"output": response}

    # ===============================================
    # Private helpers
    # ===============================================
    def _pets(self, user_id) -> List[Pet]:
        try:
            return self.pet_read_repository.get_all_by_user_id(user_id) or []
        except Exception as error:  # noqa: BLE001
            logger.warning("pets load failed: %s", error)
            return []

    def _render_available_pets(self, pets: List[Pet]) -> str:
        if not pets:
            return "nenhum"
        lines = []
        for p in pets[:_QUERY_RECORD_LIMIT]:
            name = sanitize_for_prompt(p.name, 40)
            aliases = ", ".join(
                sanitize_for_prompt(n, 40) for n in (p.nicknames or [])
            )
            if aliases:
                lines.append(f"- {name} (apelidos: {aliases})")
            else:
                lines.append(f"- {name}")
        return "\n".join(lines)

    def _recent_history(self, user_id, max_messages: int = 6) -> str:
        if self.get_session_history is None:
            return ""
        try:
            messages = self.get_session_history(user_id).messages[-max_messages:]
        except Exception as error:  # noqa: BLE001
            logger.warning("history load failed: %s", error)
            return ""
        rendered = []
        for m in messages:
            role = "Usuário" if m.__class__.__name__ == "HumanMessage" else "Peruca"
            rendered.append(f"{role}: {sanitize_for_prompt(m.content, 200)}")
        return "\n".join(rendered)

    @staticmethod
    def _register_slots(pet, event_type, event_name, occurred_at) -> dict:
        return {
            "pet_id": pet.id if pet else None,
            "pet_name": pet.name if pet else None,
            "event_type": event_type,
            "event_name": event_name,
            "date": occurred_at.isoformat() if occurred_at else None,
        }

    def _do_register(self, user, pet, event_type, event_name, occurred_at) -> str:
        try:
            self.pet_health_service.register(
                PetHealthEventAdd(
                    pet_id=pet.id,
                    event_type=event_type,
                    description=event_name,
                    occurred_at=occurred_at,
                ),
                user.id,
            )
        except ValidationError as error:
            return f"Não consegui registrar: {error.errors}"
        except Exception as error:  # noqa: BLE001
            logger.error("register_health_event failed: %s", error, exc_info=True)
            return "Tive um problema ao registrar, tente de novo."
        when = occurred_at.strftime("%d/%m/%Y")
        return f"Registrei {event_name} para o {pet.name}, no dia {when}."

    def _ask_for_slot(self, slot: str, event_type: str = "") -> str:
        if slot == "pet":
            return "De qual pet estamos falando?"
        if slot == "event_name":
            if event_type == "vaccine":
                return "Qual vacina ele tomou?"
            return "O que foi aplicado exatamente?"
        if slot == "date":
            return "Quando foi?"
        return "Pode me dar esse dado?"

    def _render_records(self, pet, records) -> str:
        lines = [f"O histórico de saúde do {pet.name} que eu tenho:"]
        for r in records:
            when = r.occurred_at.strftime("%d/%m/%Y") if r.occurred_at else "?"
            desc = sanitize_for_prompt(r.description, _MAX_RECORD_DESCRIPTION_CHARS)
            lines.append(f"{when} - {desc}")
        return "\n".join(lines)

    def _render_open(self, user, pet, data, records) -> str:
        block_lines = []
        for r in records:
            when = r.occurred_at.strftime("%d/%m/%Y") if r.occurred_at else "?"
            desc = sanitize_for_prompt(r.description, _MAX_RECORD_DESCRIPTION_CHARS)
            block_lines.append(f"- {when} | {r.event_type} | {desc}")
        records_block = "\n".join(block_lines)
        chain = self.query_response_prompt | self.llm_chat
        try:
            response = chain.invoke(
                {
                    "input": data.get("query") or "",
                    "user_name": user.name,
                    "current_date": date.today().isoformat(),
                    "pet_name": pet.name,
                    "records": records_block,
                }
            )
            text = self._remove_thinking_tag(response.content)
            if text and text.strip():
                return text
        except Exception as error:  # noqa: BLE001
            logger.error("open query render failed: %s", error, exc_info=True)
        return self._render_records(pet, records)

    def _store_flow(self, user, pending: PendingFlow) -> None:
        if self.pet_health_flow_service is None:
            return
        try:
            async_runner.run(
                self.pet_health_flow_service.set_pending(user.id, pending)
            )
        except Exception as error:  # noqa: BLE001
            logger.error("failed to store pet health flow: %s", error, exc_info=True)

    def _set_focus(self, user, pet, record) -> None:
        if self.pet_health_flow_service is None:
            return
        focus = {
            "record_id": record.id,
            "pet_id": pet.id,
            "pet_name": pet.name,
            "event_type": record.event_type,
            "description": record.description,
            "occurred_at": record.occurred_at.isoformat()
            if record.occurred_at
            else None,
        }
        try:
            async_runner.run(self.pet_health_flow_service.set_focus(user.id, focus))
        except Exception as error:  # noqa: BLE001
            logger.error("failed to store focus: %s", error, exc_info=True)

    def _get_focus(self, user) -> Optional[dict]:
        if self.pet_health_flow_service is None:
            return None
        try:
            return async_runner.run(self.pet_health_flow_service.get_focus(user.id))
        except Exception as error:  # noqa: BLE001
            logger.warning("failed to load focus: %s", error)
            return None

    def _build_edit(self, focus: dict, edit_field: str, new_value: str):
        field = (edit_field or "").lower()
        record_id = focus.get("record_id")
        if not record_id:
            return None, None

        if "data" in field or "dia" in field:
            parsed = parse_explicit_date(new_value, date.today())
            if parsed is None:
                return None, None
            human = (
                f"Alterei a data de {focus.get('description')} do "
                f"{focus.get('pet_name')} para {parsed.strftime('%d/%m/%Y')}."
            )
            return PetHealthEventUpdate(id=record_id, occurred_at=parsed), human

        if new_value.strip():
            human = f"Atualizei a descrição para: {new_value.strip()}."
            return (
                PetHealthEventUpdate(id=record_id, description=new_value.strip()),
                human,
            )
        return None, None

    @staticmethod
    def _format_iso(iso: Optional[str]) -> str:
        if not iso:
            return "?"
        try:
            return date.fromisoformat(iso).strftime("%d/%m/%Y")
        except ValueError:
            return iso

    @staticmethod
    def _resolve_date(token: str, value: str) -> Optional[date]:
        if token:
            resolved = resolve_date_token(token, date.today())
            if resolved is not None:
                return resolved
        if value:
            return parse_explicit_date(value, date.today())
        return None

    @staticmethod
    def _coerce_int(value) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _compile(self):
        workflow = StateGraph(PetHealthGraphState)
        workflow.add_node("classify", RunnableLambda(self._classify_intent))
        workflow.add_node("list_pets", RunnableLambda(self._handle_list_pets))
        workflow.add_node(
            "register_health_event",
            RunnableLambda(self._handle_register_health_event),
        )
        workflow.add_node(
            "query_health_event", RunnableLambda(self._handle_query_health_event)
        )
        workflow.add_node(
            "edit_health_event", RunnableLambda(self._handle_edit_health_event)
        )
        workflow.add_node(
            "delete_health_event", RunnableLambda(self._handle_delete_health_event)
        )
        workflow.add_node(
            "pet_write_forbidden", RunnableLambda(self._handle_pet_write_forbidden)
        )
        workflow.add_node("not_recognized", RunnableLambda(self._handle_not_recognized))
        workflow.add_node("final_response", RunnableLambda(self._handle_final_response))
        workflow.add_edge(START, "classify")

        def intent_router(state):
            return state.get("intent", [])

        workflow.add_conditional_edges("classify", intent_router)

        for node in [
            "list_pets",
            "register_health_event",
            "query_health_event",
            "edit_health_event",
            "delete_health_event",
            "pet_write_forbidden",
            "not_recognized",
        ]:
            workflow.add_edge(node, "final_response")
        workflow.add_edge("final_response", END)
        return workflow.compile()

    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        if self._compiled_graph is None:
            self._compiled_graph = self._compile()
        return self._compiled_graph.invoke({"input": invoke_request})
