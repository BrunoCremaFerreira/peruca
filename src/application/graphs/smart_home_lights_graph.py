import asyncio
from infra import async_runner
import json
import logging
from typing import List, Optional, TypedDict
from application.graphs.graph import Graph
from application.graphs.markers import DEVICE_NOT_RECOGNIZED, NO_ACTION_PERFORMED
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableLambda
from domain.commands import LightTurnOn
from domain.entities import GraphInvokeRequest, SmartHomeEntityAlias, SmartHomeLight
from domain.exceptions import ValidationError
from domain.interfaces.data_repository import (
    SmartHomeAreaRepository,
    SmartHomeEntityAliasRepository,
)
from domain.services.smart_home_service import SmartHomeService


logger = logging.getLogger(__name__)

_STATUS_LABEL_ON = "Ligada"
_STATUS_LABEL_OFF = "Desligada"
_STATUS_LABEL_OFFLINE = "Offline"


class SmartHomeLightsGraphState(TypedDict):
    input: str
    intent: Optional[list[str]]
    output_turn_on: Optional[str]
    output_turn_off: Optional[str]
    output_turn_on_by_area: Optional[str]
    output_turn_off_by_area: Optional[str]
    output_turn_on_all: Optional[str]
    output_turn_off_all: Optional[str]
    output_list_lights_status: Optional[str]
    output_check_status: Optional[str]
    output_change_color: Optional[str]
    output_change_bright: Optional[str]
    output_change_mode: Optional[str]
    output_not_recognized: Optional[str]
    available_entities: Optional[dict]
    output: Optional[str]


class SmartHomeLightsGraph(Graph):
    """
    Smart Home Lights Graph
    """

    def __init__(
        self,
        llm_chat: BaseChatModel,
        smart_home_service: SmartHomeService,
        smart_home_entity_alias_repository: SmartHomeEntityAliasRepository,
        smart_home_area_repository: Optional[SmartHomeAreaRepository] = None,
        provider: str = "OLLAMA",
        strip_think_directive: bool = False,
    ):
        super().__init__(provider, strip_think_directive)
        self.llm_chat = llm_chat
        self.smart_home_service = smart_home_service
        self.smart_home_entity_alias_repository = smart_home_entity_alias_repository
        self.smart_home_area_repository = smart_home_area_repository
        self.classification_prompt = ChatPromptTemplate.from_template(
            self.load_prompt("smart_home_lights_graph.md")
        )

    # ===============================================
    # Graph Nodes
    # ===============================================

    def _classify_intent(self, data):
        """
        Classify the user's intent based on the input text.
        """
        logger.debug("classify_intent input=%r", data["input"])

        try:
            entity_alias_list: List[SmartHomeEntityAlias] = (
                self.smart_home_entity_alias_repository.get_all(
                    entity_id_starts_with="light."
                )
            )
            entity_alias_dict = {
                item.alias: item.entity_id for item in entity_alias_list
            }
        except Exception as error:
            logger.warning("classify_intent alias lookup failed: %s", error)
            entity_alias_dict = {}

        available_areas_csv = self._load_available_areas_csv()

        chain = self.classification_prompt | self.llm_chat
        invoke_payload = {
            "input": data["input"],
            "available_entities": str(entity_alias_dict),
            "available_areas": available_areas_csv,
        }
        try:
            response = chain.invoke(invoke_payload)
        except KeyError:
            # Test stubs may use a template with only {input}; retry minimal.
            response = chain.invoke({"input": data["input"]})
        extracted = self._extract_structured_output(response.content)

        logger.debug("classify_intent raw_output=%r", extracted)

        try:
            parsed = json.loads(extracted) if extracted else {}
            if not isinstance(parsed, dict):
                parsed = {}
        except (json.JSONDecodeError, ValueError):
            parsed = {}

        intents = parsed.get("intents", ["not_recognized"]) or ["not_recognized"]

        return {
            "intent": intents,
            "input": data["input"],
            "output_turn_on": parsed.get("turn_on") or None,
            "output_turn_off": parsed.get("turn_off") or None,
            "output_turn_on_by_area": self._coerce_area_payload(
                parsed.get("turn_on_by_area")
            ),
            "output_turn_off_by_area": self._coerce_area_payload(
                parsed.get("turn_off_by_area")
            ),
            "output_turn_on_all": parsed.get("turn_on_all") or None,
            "output_turn_off_all": parsed.get("turn_off_all") or None,
            "output_list_lights_status": parsed.get("list_lights_status") or None,
            "output_check_status": parsed.get("check_status") or None,
            "output_change_color": parsed.get("change_color") or None,
            "output_change_bright": parsed.get("change_bright") or None,
            "output_change_mode": parsed.get("change_mode") or None,
            "output_not_recognized": parsed.get("not_recognized") or None,
            "available_entities": entity_alias_dict,
        }

    def _handle_turn_on(self, data):
        devices = data.get("output_turn_on", "")
        logger.debug("handle_turn_on devices=%r", devices)

        if not devices:
            return {}

        entity_ids: List[str] = self._find_entity_ids(
            entity_alias_delimited_str=devices,
            available_entities=data.get("available_entities", {}),
        )

        if not entity_ids:
            return {"output_turn_on": "Dispositivo nao encontrado"}

        async def _run():
            await asyncio.gather(*[
                self.smart_home_service.light_turn_on(turn_on_command=LightTurnOn(entity_id=eid))
                for eid in entity_ids
            ])

        try:
            async_runner.run(_run())
        except Exception as error:
            logger.error("handle_turn_on failed: %s", error, exc_info=True)
            return {"output_turn_on": "Falha ao ligar as luzes"}

        return {"output_turn_on": devices}

    def _handle_turn_off(self, data):
        devices = data.get("output_turn_off", "")
        logger.debug("handle_turn_off devices=%r", devices)

        if not devices:
            return {}

        entity_ids: List[str] = self._find_entity_ids(
            entity_alias_delimited_str=devices,
            available_entities=data.get("available_entities", {}),
        )

        if not entity_ids:
            return {"output_turn_off": "Dispositivo nao encontrado"}

        async def _run():
            await asyncio.gather(*[
                self.smart_home_service.light_turn_off(entity_id=eid)
                for eid in entity_ids
            ])

        try:
            async_runner.run(_run())
        except Exception as error:
            logger.error("handle_turn_off failed: %s", error, exc_info=True)
            return {"output_turn_off": "Falha ao desligar as luzes"}

        return {"output_turn_off": devices}

    def _handle_turn_on_by_area(self, data):
        payload = data.get("output_turn_on_by_area")
        logger.debug("handle_turn_on_by_area payload=%r", payload)

        areas = self._split_area_payload(payload)
        if not areas:
            return {}

        async def _run_all():
            for area in areas:
                await self.smart_home_service.turn_on_by_area(area_alias=area)

        try:
            async_runner.run(_run_all())
        except ValidationError as error:
            logger.warning("handle_turn_on_by_area area not found: %s", error)
            return {
                "output_turn_on_by_area": (
                    f"Cômodo não encontrado: {', '.join(areas)}"
                )
            }
        except Exception as error:
            logger.error("handle_turn_on_by_area failed: %s", error, exc_info=True)
            return {
                "output_turn_on_by_area": (
                    f"Falha ao ligar as luzes: {', '.join(areas)}"
                )
            }

        return {"output_turn_on_by_area": f"Luzes ligadas: {', '.join(areas)}"}

    def _handle_turn_off_by_area(self, data):
        payload = data.get("output_turn_off_by_area")
        logger.debug("handle_turn_off_by_area payload=%r", payload)

        areas = self._split_area_payload(payload)
        if not areas:
            return {}

        async def _run_all():
            for area in areas:
                await self.smart_home_service.turn_off_by_area(area_alias=area)

        try:
            async_runner.run(_run_all())
        except ValidationError as error:
            logger.warning("handle_turn_off_by_area area not found: %s", error)
            return {
                "output_turn_off_by_area": (
                    f"Cômodo não encontrado: {', '.join(areas)}"
                )
            }
        except Exception as error:
            logger.error("handle_turn_off_by_area failed: %s", error, exc_info=True)
            return {
                "output_turn_off_by_area": (
                    f"Falha ao desligar as luzes: {', '.join(areas)}"
                )
            }

        return {"output_turn_off_by_area": f"Luzes desligadas: {', '.join(areas)}"}

    def _handle_turn_on_all(self, data):
        payload = data.get("output_turn_on_all")
        logger.debug("handle_turn_on_all payload=%r", payload)

        if not payload:
            return {}

        try:
            async_runner.run(self.smart_home_service.turn_on_all_house())
        except Exception as error:
            logger.error("handle_turn_on_all failed: %s", error, exc_info=True)
            return {"output_turn_on_all": "Falha ao ligar todas as luzes"}

        return {"output_turn_on_all": "Todas as luzes da casa foram ligadas"}

    def _handle_turn_off_all(self, data):
        payload = data.get("output_turn_off_all")
        logger.debug("handle_turn_off_all payload=%r", payload)

        if not payload:
            return {}

        try:
            async_runner.run(self.smart_home_service.turn_off_all_house())
        except Exception as error:
            logger.error("handle_turn_off_all failed: %s", error, exc_info=True)
            return {"output_turn_off_all": "Falha ao desligar todas as luzes"}

        return {"output_turn_off_all": "Todas as luzes da casa foram desligadas"}

    def _handle_list_lights_status(self, data):
        payload = data.get("output_list_lights_status")
        logger.debug("handle_list_lights_status payload=%r", payload)

        if not payload:
            return {}

        try:
            grouped = async_runner.run(
                self.smart_home_service.list_lights_grouped_by_area()
            )
        except Exception as error:
            logger.error("handle_list_lights_status failed: %s", error, exc_info=True)
            return {
                "output_list_lights_status": (
                    "Não consegui consultar o estado das luzes agora."
                )
            }

        if not grouped:
            return {
                "output_list_lights_status": (
                    "Não há luzes registradas para consultar."
                )
            }

        formatted = self._format_lights_grouped(grouped)
        return {"output_list_lights_status": formatted}

    def _handle_check_status(self, data):
        payload = data.get("output_check_status")
        logger.debug("handle_check_status payload=%r", payload)

        if not payload:
            return {}

        light = async_runner.run(
            self.smart_home_service.get_light_status_by_alias(payload)
        )

        if light is None:
            return {
                "output_check_status": f"Não encontrei o dispositivo '{payload}'."
            }

        name = light.friendly_name or payload

        if light.is_available is False:
            phrase = f"A luz {name} parece estar offline."
        elif light.is_on:
            phrase = f"Sim, a luz {name} está ligada."
        else:
            phrase = f"A luz {name} está desligada."

        return {"output_check_status": phrase}

    def _handle_change_color(self, data):
        devices = data.get("output_change_color", "")
        if devices:
            logger.debug("handle_change_color devices=%r", devices)
            return {"output_change_color": devices}
        return {}

    def _handle_change_bright(self, data):
        devices = data.get("output_change_bright", "")
        if not devices:
            return {}

        logger.debug("handle_change_bright devices=%r", devices)

        available_entities = data.get("available_entities", {})
        segments = devices.split("|")
        found_aliases: list[str] = []
        not_found: list[str] = []

        for segment in segments:
            segment = segment.strip()
            if "," not in segment:
                not_found.append(segment)
                continue

            alias_str, pct_str = segment.rsplit(",", 1)
            alias_str = alias_str.strip()

            try:
                brightness_pct = int(pct_str.strip())
                brightness_pct = max(0, min(100, brightness_pct))
            except ValueError:
                brightness_pct = 50

            entity_ids: List[str] = self._find_entity_ids(
                entity_alias_delimited_str=alias_str,
                available_entities=available_entities,
            )

            if not entity_ids:
                not_found.append(alias_str)
                continue

            async def _run():
                await asyncio.gather(*[
                    self.smart_home_service.light_turn_on(
                        turn_on_command=LightTurnOn(entity_id=eid, brightness_pct=brightness_pct)
                    )
                    for eid in entity_ids
                ])
            async_runner.run(_run())

            found_aliases.append(alias_str)

        output_parts: list[str] = []
        if found_aliases:
            output_parts.append(f"Brilho alterado: {', '.join(found_aliases)}")
        if not_found:
            output_parts.append("Dispositivo nao encontrado")

        return {"output_change_bright": ". ".join(output_parts)}

    def _handle_change_mode(self, data):
        devices = data.get("output_change_mode", "")
        if devices:
            logger.debug("handle_change_mode devices=%r", devices)
            return {"output_change_mode": devices}
        return {}

    def _handle_final_response(self, data):
        logger.info("handle_final_response: aggregating response")
        parts = []
        if data.get("output_turn_on"):
            parts.append(f"Ligado: {data['output_turn_on']}")
        if data.get("output_turn_off"):
            parts.append(f"Desligado: {data['output_turn_off']}")
        if data.get("output_turn_on_by_area"):
            parts.append(str(data["output_turn_on_by_area"]))
        if data.get("output_turn_off_by_area"):
            parts.append(str(data["output_turn_off_by_area"]))
        if data.get("output_turn_on_all"):
            parts.append(str(data["output_turn_on_all"]))
        if data.get("output_turn_off_all"):
            parts.append(str(data["output_turn_off_all"]))
        if data.get("output_list_lights_status"):
            parts.append(str(data["output_list_lights_status"]))
        if data.get("output_check_status"):
            parts.append(str(data["output_check_status"]))
        if data.get("output_change_color"):
            parts.append(f"Cor alterada: {data['output_change_color']}")
        if data.get("output_change_bright"):
            parts.append(f"Brilho alterado: {data['output_change_bright']}")
        if data.get("output_change_mode"):
            parts.append(f"Modo alterado: {data['output_change_mode']}")
        if data.get("output_not_recognized"):
            parts.append(DEVICE_NOT_RECOGNIZED)
        if not parts:
            return {"output": NO_ACTION_PERFORMED}
        return {"output": "\n".join(parts)}

    def _handle_not_recognized(self, data):
        logger.info("handle_not_recognized triggered")
        return {"output_not_recognized": DEVICE_NOT_RECOGNIZED}

    # ===============================================
    # Private Methods
    # ===============================================

    def _compile(self):
        workflow = StateGraph(SmartHomeLightsGraphState)

        workflow.add_node("classify", RunnableLambda(self._classify_intent))
        workflow.add_node("turn_on", RunnableLambda(self._handle_turn_on))
        workflow.add_node("turn_off", RunnableLambda(self._handle_turn_off))
        workflow.add_node(
            "turn_on_by_area", RunnableLambda(self._handle_turn_on_by_area)
        )
        workflow.add_node(
            "turn_off_by_area", RunnableLambda(self._handle_turn_off_by_area)
        )
        workflow.add_node("turn_on_all", RunnableLambda(self._handle_turn_on_all))
        workflow.add_node("turn_off_all", RunnableLambda(self._handle_turn_off_all))
        workflow.add_node(
            "list_lights_status", RunnableLambda(self._handle_list_lights_status)
        )
        workflow.add_node("check_status", RunnableLambda(self._handle_check_status))
        workflow.add_node("change_color", RunnableLambda(self._handle_change_color))
        workflow.add_node("change_bright", RunnableLambda(self._handle_change_bright))
        workflow.add_node("change_mode", RunnableLambda(self._handle_change_mode))
        workflow.add_node("not_recognized", RunnableLambda(self._handle_not_recognized))
        workflow.add_node("final_response", RunnableLambda(self._handle_final_response))
        workflow.add_edge(START, "classify")

        def intent_router(state):
            return state.get("intent", [])

        workflow.add_conditional_edges("classify", intent_router)

        nodes = [
            "turn_on",
            "turn_off",
            "turn_on_by_area",
            "turn_off_by_area",
            "turn_on_all",
            "turn_off_all",
            "list_lights_status",
            "check_status",
            "change_color",
            "change_bright",
            "change_mode",
            "not_recognized",
        ]

        for node in nodes:
            workflow.add_edge(node, "final_response")

        workflow.add_edge("final_response", END)

        return workflow.compile()

    def _load_available_areas_csv(self) -> str:
        """
        Build a comma-separated list of area names so the prompt can render
        the catalog inline ({available_areas}). Falls back to "" when no
        repository is wired (test stubs and legacy deployments).
        """
        if self.smart_home_area_repository is None:
            return ""
        try:
            areas = self.smart_home_area_repository.get_all()
        except Exception as error:
            logger.warning("load_available_areas_csv failed: %s", error)
            return ""
        return ", ".join(area.name for area in areas if area.name)

    def _coerce_area_payload(self, value):
        """
        Normalize the LLM area payload to a value the area handlers can
        consume directly: list -> list, non-empty string -> string, anything
        else -> None.
        """
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            return cleaned or None
        if isinstance(value, str):
            return value if value.strip() else None
        return None

    def _split_area_payload(self, payload) -> List[str]:
        """
        Accept either a list or a pipe-delimited string. Returns an ordered,
        de-duplicated list of trimmed area names. Empty payloads return [].
        """
        if payload is None:
            return []
        if isinstance(payload, list):
            candidates = [str(item).strip() for item in payload]
        else:
            candidates = [chunk.strip() for chunk in str(payload).split("|")]
        result: List[str] = []
        seen: set = set()
        for area in candidates:
            if not area or area in seen:
                continue
            seen.add(area)
            result.append(area)
        return result

    def _format_lights_grouped(self, grouped) -> str:
        """
        Format the grouped lights payload as canonical text used by the
        response prompt (and also returned as-is when no LLM polishing is
        required by the tests).
        """
        lines: List[str] = []
        for area_name, lights in grouped.items():
            lines.append(f"**{area_name}**")
            for light in lights:
                label = self._light_status_label(light)
                name = light.friendly_name or light.entity_id
                lines.append(f"- {name}: {label}")
            lines.append("")
        return "\n".join(lines).strip()

    def _light_status_label(self, light: SmartHomeLight) -> str:
        if light.is_available is False:
            return _STATUS_LABEL_OFFLINE
        return _STATUS_LABEL_ON if light.is_on else _STATUS_LABEL_OFF

    def _find_entity_ids(
        self, entity_alias_delimited_str: str, available_entities
    ) -> List[str]:
        deterministic = self.smart_home_service.find_entity_ids_by_alias(
            query_alias=entity_alias_delimited_str,
            available_entities=available_entities or {},
        )
        if deterministic:
            return deterministic

        parser_template = ChatPromptTemplate.from_template(
            self.load_prompt("smart_home_lights_graph_id_parser_by_alias.md")
        )

        prompt = parser_template.format(
            input=entity_alias_delimited_str, available_entities=str(available_entities)
        )

        async def _invoke_with_timeout():
            try:
                response = await asyncio.wait_for(
                    self.llm_chat.ainvoke(prompt), timeout=15
                )
                return self._remove_thinking_tag(response.content).strip()
            except asyncio.TimeoutError:
                logger.warning("find_entity_ids timed out")
                return "None"

        entity_ids_delimited_str = async_runner.run(_invoke_with_timeout())

        entity_ids = entity_ids_delimited_str.split("|")
        entity_ids = [e for e in entity_ids if e.upper() != "NONE" and e.strip() != ""]

        return entity_ids

    # ===============================================
    # Public Methods
    # ===============================================

    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        if self._compiled_graph is None:
            self._compiled_graph = self._compile()
        app = self._compiled_graph
        return app.invoke({"input": invoke_request})
