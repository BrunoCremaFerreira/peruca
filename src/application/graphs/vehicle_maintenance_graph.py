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
from domain.commands import MaintenanceRecordAdd, MaintenanceRecordUpdate
from domain.entities import (
    DisambiguationCandidate,
    GraphInvokeRequest,
    PendingFlow,
    Vehicle,
)
from domain.exceptions import ValidationError
from domain.services.clock import local_date_for_user
from domain.services.date_resolver import (
    parse_explicit_date,
    resolve_date_token,
    resolve_period,
)
from domain.services.vehicle_service import find_vehicles_by_term
from infra import async_runner


logger = logging.getLogger(__name__)

_FORBIDDEN_MESSAGE = "Não tenho permissão para realizar esta operação"
_QUERY_RECORD_LIMIT = 20
_MAX_RECORD_DESCRIPTION_CHARS = 200


class VehicleMaintenanceGraphState(TypedDict, total=False):
    input: GraphInvokeRequest
    intent: Optional[List[str]]
    vehicle_term: Optional[str]
    description: Optional[str]
    resolved_performed_at: Optional[date]
    resolved_period: Optional[tuple]
    odometer_km: Optional[int]
    query: Optional[str]
    query_kind: Optional[str]
    query_limit: Optional[int]
    edit_field: Optional[str]
    new_value: Optional[str]
    matched_vehicles: Optional[List[Vehicle]]
    output_list: Optional[str]
    output_register: Optional[str]
    output_query: Optional[str]
    output_edit: Optional[str]
    output_delete: Optional[str]
    output_forbidden: Optional[str]
    output_not_recognized: Optional[str]
    output: Optional[str]


class VehicleMaintenanceGraph(Graph):
    """
    Vehicle maintenance graph: lists vehicles, registers/queries/edits/removes
    maintenance records, and refuses vehicle writes over chat. Vehicle
    resolution and date arithmetic are deterministic (Python); the LLM only
    classifies + extracts and, for open queries, phrases the answer.

    It receives ONLY a VehicleReadRepository — no code path here can write a
    vehicle (§2.4).
    """

    def __init__(
        self,
        llm_chat: BaseChatModel,
        vehicle_read_repository,
        maintenance_service,
        maintenance_flow_service,
        get_session_history=None,
        provider: str = "OLLAMA",
        strip_think_directive: bool = False,
    ):
        super().__init__(provider, strip_think_directive)
        self.llm_chat = llm_chat
        self.vehicle_read_repository = vehicle_read_repository
        self.maintenance_service = maintenance_service
        self.maintenance_flow_service = maintenance_flow_service
        self.get_session_history = get_session_history
        self.classification_prompt = ChatPromptTemplate.from_template(
            self.load_prompt("vehicle_maintenance_graph.md")
        )
        self.query_response_prompt = ChatPromptTemplate.from_template(
            self.load_prompt("vehicle_maintenance_graph_query_response.md")
        )

    # ===============================================
    # Graph Nodes
    # ===============================================
    def _classify_intent(self, data):
        request: GraphInvokeRequest = data["input"]
        user = request.user
        fleet = self._fleet(user.id)
        available = ", ".join(v.name for v in fleet) or "nenhum"

        # "Today" is the user's civil date, never the server's: a request at
        # 02:30Z is still the previous day in São Paulo.
        reference = local_date_for_user(request.user_timezone)

        payload = {
            "input": request.message,
            "current_date": reference.isoformat(),
            "available_vehicles": available,
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

        vehicle_term = (parsed.get("vehicle_term") or "").strip()
        performed_at = self._resolve_date(
            parsed.get("date_token") or "", parsed.get("date_value") or "", reference
        )
        period = resolve_period(parsed.get("period") or "", reference)
        odometer_km = self._coerce_km(parsed.get("odometer_km"))

        return {
            "intent": intents,
            "input": request,
            "vehicle_term": vehicle_term,
            "description": (parsed.get("description") or "").strip(),
            "resolved_performed_at": performed_at,
            "resolved_period": period,
            "odometer_km": odometer_km,
            "query": (parsed.get("query") or "").strip(),
            "query_kind": (parsed.get("query_kind") or "").strip(),
            "query_limit": self._coerce_int(parsed.get("query_limit")),
            "edit_field": (parsed.get("edit_field") or "").strip(),
            "new_value": (parsed.get("new_value") or "").strip(),
            "matched_vehicles": find_vehicles_by_term(vehicle_term, fleet)
            if vehicle_term
            else [],
        }

    def _handle_list_vehicles(self, data):
        user = data["input"].user
        fleet = self._fleet(user.id)
        if not fleet:
            return {"output_list": "Você ainda não tem nenhum veículo cadastrado."}
        names = ", ".join(v.name for v in fleet)
        return {
            "output_list": (
                f"Os seus veículos são: {names}. Gostaria de registrar alguma "
                "manutenção ou saber quando será a próxima?"
            )
        }

    def _handle_vehicle_write_forbidden(self, data):
        return {"output_forbidden": _FORBIDDEN_MESSAGE}

    def _handle_register_maintenance(self, data):
        user = data["input"].user
        term = data.get("vehicle_term") or ""
        matched, ask = self._resolve_or_ask(user, term)
        if ask is not None:
            return {"output_register": ask}
        vehicle = matched[0]

        description = data.get("description") or ""
        performed_at = data.get("resolved_performed_at")
        odometer_km = data.get("odometer_km")

        missing = []
        if not performed_at:
            missing.append("date")
        if odometer_km is None:
            missing.append("km")

        if missing:
            self._store_flow(
                user,
                PendingFlow(
                    operation="register",
                    slots={
                        "description": description,
                        "vehicle_id": vehicle.id,
                        "vehicle_name": vehicle.name,
                        "date": performed_at.isoformat() if performed_at else None,
                        "odometer_km": odometer_km,
                    },
                    missing_slots=missing,
                ),
            )
            return {"output_register": self._ask_for_slot(missing[0])}

        try:
            self.maintenance_service.register(
                MaintenanceRecordAdd(
                    vehicle_id=vehicle.id,
                    description=description,
                    performed_at=performed_at,
                    odometer_km=odometer_km,
                ),
                user.id,
            )
        except ValidationError as error:
            return {"output_register": f"Não consegui registrar: {error.errors}"}
        except Exception as error:  # noqa: BLE001
            logger.error("register_maintenance failed: %s", error, exc_info=True)
            return {"output_register": "Tive um problema ao registrar, tente de novo."}

        return {
            "output_register": (
                f"Registrei {description} para o {vehicle.name}, com data "
                f"{performed_at.strftime('%d/%m/%Y')} e quilometragem {odometer_km}."
            )
        }

    def _handle_query_maintenance(self, data):
        user = data["input"].user
        term = data.get("vehicle_term") or ""
        matched, ask = self._resolve_or_ask(user, term)
        if ask is not None:
            return {"output_query": ask}
        vehicle = matched[0]

        # Hard ceiling: never fetch or render more than _QUERY_RECORD_LIMIT records,
        # regardless of the query_limit the LLM emits — an inflated value (e.g. from
        # "as últimas 100000 manutenções", or a hallucination) must not blow up the
        # prompt/response (§9.5).
        requested = data.get("query_limit") or 0
        records = self.maintenance_service.get_by_vehicle(
            vehicle.id, user.id, limit=_QUERY_RECORD_LIMIT
        )

        period = data.get("resolved_period")
        if period:
            start, end = period
            records = [
                r for r in records if r.performed_at and start <= r.performed_at <= end
            ]

        if requested:
            records = records[: min(requested, _QUERY_RECORD_LIMIT)]

        if not records:
            return {
                "output_query": (
                    f"Não encontrei nenhuma manutenção registrada para o {vehicle.name}."
                )
            }

        # Remember the most recent record reported, so a follow-up
        # ("altere a km desse registro" / "remova este registro") knows which
        # one it refers to (§2.7).
        self._set_focus(user, vehicle, records[0])

        if (data.get("query_kind") or "") == "open":
            return {"output_query": self._render_open(user, vehicle, data, records)}

        return {"output_query": self._render_records(vehicle, records)}

    def _handle_edit_maintenance(self, data):
        user = data["input"].user
        focus = self._get_focus(user)
        if not focus:
            return {
                "output_edit": (
                    "Não sei a qual manutenção você se refere. Consulte o registro "
                    "primeiro (por exemplo, a última troca) e depois peça a alteração."
                )
            }

        update, human = self._build_edit(
            focus,
            (data.get("edit_field") or ""),
            (data.get("new_value") or ""),
            local_date_for_user(data["input"].user_timezone),
        )
        if update is None:
            return {
                "output_edit": "Não entendi o que você quer alterar nesse registro."
            }
        try:
            self.maintenance_service.update(update, user.id)
        except ValidationError as error:
            return {"output_edit": f"Não consegui alterar: {error.errors}"}
        except Exception as error:  # noqa: BLE001
            logger.error("edit_maintenance failed: %s", error, exc_info=True)
            return {"output_edit": "Tive um problema ao alterar, tente de novo."}
        return {"output_edit": human}

    def _handle_delete_maintenance(self, data):
        user = data["input"].user
        focus = self._get_focus(user)
        if not focus:
            return {
                "output_delete": (
                    "Não sei qual registro remover. Consulte a manutenção primeiro "
                    "para eu confirmar a remoção."
                )
            }
        self._store_flow(
            user,
            PendingFlow(
                operation="delete_confirm",
                slots={
                    "record_id": focus.get("record_id"),
                    "vehicle_name": focus.get("vehicle_name"),
                    "description": focus.get("description"),
                },
            ),
        )
        when = self._format_iso(focus.get("performed_at"))
        km = focus.get("odometer_km")
        km_part = f", km {km}" if km else ""
        return {
            "output_delete": (
                f"Devo remover o registro de {focus.get('description')} do "
                f"{focus.get('vehicle_name')}, realizado em {when}{km_part}?"
            )
        }

    def _handle_not_recognized(self, data):
        return {
            "output_not_recognized": (
                "Não entendi o que você quer fazer com as manutenções do veículo."
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
        response = "\n\n".join(outputs) if len(outputs) > 1 else (outputs[0] if outputs else "")
        return {"output": response}

    # ===============================================
    # Private helpers
    # ===============================================
    def _fleet(self, user_id) -> List[Vehicle]:
        try:
            return self.vehicle_read_repository.get_all_by_user_id(user_id) or []
        except Exception as error:  # noqa: BLE001
            logger.warning("fleet load failed: %s", error)
            return []

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

    def _resolve_or_ask(self, user, term):
        """
        Resolve a vehicle term against the user's fleet. Returns (matched, ask):
        - ([vehicle], None) when unambiguous;
        - ([], question) when unregistered;
        - ([], question) when ambiguous (a choose_vehicle flow is stored).
        """
        fleet = self._fleet(user.id)
        matched = find_vehicles_by_term(term, fleet) if term else []
        if not matched:
            return [], f"Você não tem nenhum veículo {term} cadastrado."
        if len(matched) > 1:
            names = " ou ".join(v.name for v in matched)
            self._store_flow(
                user,
                PendingFlow(
                    operation="choose_vehicle",
                    candidates=[
                        DisambiguationCandidate(id=v.id, name=v.name) for v in matched
                    ],
                ),
            )
            return [], f"Qual deles? {names}?"
        return matched, None

    def _render_records(self, vehicle, records) -> str:
        lines = [f"As últimas manutenções do {vehicle.name} que me lembro:"]
        for r in records:
            when = r.performed_at.strftime("%d/%m/%Y") if r.performed_at else "?"
            km = f"km {r.odometer_km}" if r.odometer_km else "km não informada"
            desc = sanitize_for_prompt(r.description, _MAX_RECORD_DESCRIPTION_CHARS)
            lines.append(f"{when} - {km} - {desc}")
        return "\n".join(lines)

    def _render_open(self, user, vehicle, data, records) -> str:
        block_lines = []
        for r in records:
            when = r.performed_at.strftime("%d/%m/%Y") if r.performed_at else "?"
            km = r.odometer_km if r.odometer_km else "?"
            desc = sanitize_for_prompt(r.description, _MAX_RECORD_DESCRIPTION_CHARS)
            block_lines.append(f"- {when} | km {km} | {desc}")
        records_block = "\n".join(block_lines)
        chain = self.query_response_prompt | self.llm_chat
        try:
            response = chain.invoke(
                {
                    "input": data.get("query") or "",
                    "user_name": user.name,
                    "current_date": local_date_for_user(
                        data["input"].user_timezone
                    ).isoformat(),
                    "vehicle_name": vehicle.name,
                    "records": records_block,
                }
            )
            text = self._remove_thinking_tag(response.content)
            if text and text.strip():
                return text
        except Exception as error:  # noqa: BLE001
            logger.error("open query render failed: %s", error, exc_info=True)
        # Fallback to the deterministic listing.
        return self._render_records(vehicle, records)

    def _ask_for_slot(self, slot: str) -> str:
        if slot == "vehicle":
            return "De qual veículo?"
        if slot == "date":
            return "Quando foi?"
        if slot == "km":
            return "Qual a quilometragem no momento?"
        return "Pode me dar esse dado?"

    def _store_flow(self, user, pending: PendingFlow) -> None:
        if self.maintenance_flow_service is None:
            return
        try:
            async_runner.run(
                self.maintenance_flow_service.set_pending(user.id, pending)
            )
        except Exception as error:  # noqa: BLE001
            logger.error("failed to store maintenance flow: %s", error, exc_info=True)

    def _set_focus(self, user, vehicle, record) -> None:
        if self.maintenance_flow_service is None:
            return
        focus = {
            "record_id": record.id,
            "vehicle_id": vehicle.id,
            "vehicle_name": vehicle.name,
            "description": record.description,
            "performed_at": record.performed_at.isoformat()
            if record.performed_at
            else None,
            "odometer_km": record.odometer_km,
        }
        try:
            async_runner.run(self.maintenance_flow_service.set_focus(user.id, focus))
        except Exception as error:  # noqa: BLE001
            logger.error("failed to store focus: %s", error, exc_info=True)

    def _get_focus(self, user) -> Optional[dict]:
        if self.maintenance_flow_service is None:
            return None
        try:
            return async_runner.run(self.maintenance_flow_service.get_focus(user.id))
        except Exception as error:  # noqa: BLE001
            logger.warning("failed to load focus: %s", error)
            return None

    def _build_edit(
        self, focus: dict, edit_field: str, new_value: str, reference: date
    ):
        """
        Build a MaintenanceRecordUpdate for the focused record plus a human
        confirmation, or (None, None) when the field/value is not understood.
        """
        field = (edit_field or "").lower()
        record_id = focus.get("record_id")
        if not record_id:
            return None, None

        if "km" in field or "quilometr" in field or "hodometr" in field:
            digits = "".join(ch for ch in (new_value or "") if ch.isdigit())
            if not digits:
                return None, None
            km = int(digits)
            old = focus.get("odometer_km")
            human = (
                f"Alterei a quilometragem da {focus.get('description')} do "
                f"{focus.get('vehicle_name')}"
                + (f", de {old} para {km}." if old else f" para {km}.")
            )
            return MaintenanceRecordUpdate(id=record_id, odometer_km=km), human

        if "data" in field or "dia" in field:
            parsed = parse_explicit_date(new_value, reference)
            if parsed is None:
                return None, None
            human = (
                f"Alterei a data da {focus.get('description')} do "
                f"{focus.get('vehicle_name')} para {parsed.strftime('%d/%m/%Y')}."
            )
            return MaintenanceRecordUpdate(id=record_id, performed_at=parsed), human

        if new_value.strip():
            human = f"Atualizei a descrição para: {new_value.strip()}."
            return MaintenanceRecordUpdate(id=record_id, description=new_value.strip()), human

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
    def _resolve_date(token: str, value: str, reference: date) -> Optional[date]:
        if token:
            resolved = resolve_date_token(token, reference)
            if resolved is not None:
                return resolved
        if value:
            return parse_explicit_date(value, reference)
        return None

    @staticmethod
    def _coerce_km(value) -> Optional[int]:
        try:
            km = int(value)
        except (TypeError, ValueError):
            return None
        return km if km > 0 else None

    @staticmethod
    def _coerce_int(value) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _compile(self):
        workflow = StateGraph(VehicleMaintenanceGraphState)
        workflow.add_node("classify", RunnableLambda(self._classify_intent))
        workflow.add_node("list_vehicles", RunnableLambda(self._handle_list_vehicles))
        workflow.add_node(
            "register_maintenance", RunnableLambda(self._handle_register_maintenance)
        )
        workflow.add_node(
            "query_maintenance", RunnableLambda(self._handle_query_maintenance)
        )
        workflow.add_node(
            "edit_maintenance", RunnableLambda(self._handle_edit_maintenance)
        )
        workflow.add_node(
            "delete_maintenance", RunnableLambda(self._handle_delete_maintenance)
        )
        workflow.add_node(
            "vehicle_write_forbidden",
            RunnableLambda(self._handle_vehicle_write_forbidden),
        )
        workflow.add_node("not_recognized", RunnableLambda(self._handle_not_recognized))
        workflow.add_node("final_response", RunnableLambda(self._handle_final_response))
        workflow.add_edge(START, "classify")

        def intent_router(state):
            return state.get("intent", [])

        workflow.add_conditional_edges("classify", intent_router)

        for node in [
            "list_vehicles",
            "register_maintenance",
            "query_maintenance",
            "edit_maintenance",
            "delete_maintenance",
            "vehicle_write_forbidden",
            "not_recognized",
        ]:
            workflow.add_edge(node, "final_response")
        workflow.add_edge("final_response", END)
        return workflow.compile()

    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        if self._compiled_graph is None:
            self._compiled_graph = self._compile()
        return self._compiled_graph.invoke({"input": invoke_request})
