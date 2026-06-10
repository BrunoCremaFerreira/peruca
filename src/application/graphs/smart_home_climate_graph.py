import asyncio
from infra import async_runner
import json
from typing import List, Optional, TypedDict
from application.graphs.graph import Graph
from application.graphs.markers import DEVICE_NOT_RECOGNIZED, NO_ACTION_PERFORMED
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableLambda
from domain.commands import (
    ClimateSetTemperature,
    ClimateSetHvacMode,
    ClimateTurnOn,
    ClimateTurnOff,
)
from domain.entities import GraphInvokeRequest, SmartHomeClimate, SmartHomeEntityAlias
from domain.interfaces.data_repository import SmartHomeEntityAliasRepository
from domain.services.smart_home_service import SmartHomeService

HVAC_MODE_MAP = {
    "frio": "cool",
    "calor": "heat",
    "automatico": "auto",
    "ventilacao": "fan_only",
    "dry": "dry",
}


class SmartHomeClimateGraphState(TypedDict):
    input: str
    intent: Optional[list[str]]
    output_turn_on: Optional[str]
    output_turn_off: Optional[str]
    output_set_temperature: Optional[str]
    output_set_hvac_mode: Optional[str]
    output_query_state: Optional[str]
    output_not_recognized: Optional[str]
    available_entities: Optional[dict]
    output: Optional[str]


class SmartHomeClimateGraph(Graph):
    """
    Smart Home Climate Graph
    """

    def __init__(
        self,
        llm_chat: BaseChatModel,
        smart_home_service: SmartHomeService,
        smart_home_entity_alias_repository: SmartHomeEntityAliasRepository,
        provider: str = "OLLAMA",
        strip_think_directive: bool = False,
    ):
        super().__init__(provider, strip_think_directive)
        self.llm_chat = llm_chat
        self.smart_home_service = smart_home_service
        self.smart_home_entity_alias_repository = smart_home_entity_alias_repository
        self.classification_prompt = ChatPromptTemplate.from_template(
            self.load_prompt("smart_home_climate_graph.md")
        )

    # ===============================================
    # Graph Nodes
    # ===============================================

    def _classify_intent(self, data):
        print(f"[SmartHomeClimateGraph._classify_intent]: input={data['input']}")

        chain = self.classification_prompt | self.llm_chat
        response = chain.invoke({"input": data["input"]})
        extracted = self._extract_structured_output(response.content)

        print(f"[SmartHomeClimateGraph._classify_intent]: raw_output={extracted}")

        try:
            try:
                parsed = json.loads(extracted) if extracted else {}
            except (json.JSONDecodeError, ValueError):
                parsed = {}
            intents = parsed.get("intents", ["not_recognized"])

            entity_alias_list: List[SmartHomeEntityAlias] = (
                self.smart_home_entity_alias_repository.get_all(
                    entity_id_starts_with="climate."
                )
            )
            entity_alias_dict = {
                item.alias: item.entity_id for item in entity_alias_list
            }

        except Exception as e:
            print(f"[SmartHomeClimateGraph._classify_intent][ERROR]: {e}")
            parsed = {}
            intents = ["not_recognized"]
            entity_alias_dict = {}

        return {
            "intent": intents,
            "input": data["input"],
            "output_turn_on": parsed.get("turn_on"),
            "output_turn_off": parsed.get("turn_off"),
            "output_set_temperature": parsed.get("set_temperature"),
            "output_set_hvac_mode": parsed.get("set_hvac_mode"),
            "output_query_state": parsed.get("query_state"),
            "output_not_recognized": parsed.get("not_recognized"),
            "available_entities": entity_alias_dict,
        }

    def _handle_turn_on(self, data):
        devices = data.get("output_turn_on", "")
        print(f"[SmartHomeClimateGraph._handle_turn_on]: {devices}")

        if not devices:
            return {}

        entity_ids: List[str] = self._find_entity_ids(
            entity_alias_delimited_str=devices,
            available_entities=data.get("available_entities", {}),
        )

        if not entity_ids:
            return {"output_turn_on": DEVICE_NOT_RECOGNIZED}

        async def _run():
            await asyncio.gather(*[
                self.smart_home_service.climate_turn_on(command=ClimateTurnOn(entity_id=eid))
                for eid in entity_ids
            ])
        async_runner.run(_run())

        return {"output_turn_on": devices}

    def _handle_turn_off(self, data):
        devices = data.get("output_turn_off", "")
        print(f"[SmartHomeClimateGraph._handle_turn_off]: {devices}")

        if not devices:
            return {}

        entity_ids: List[str] = self._find_entity_ids(
            entity_alias_delimited_str=devices,
            available_entities=data.get("available_entities", {}),
        )

        if not entity_ids:
            return {"output_turn_off": DEVICE_NOT_RECOGNIZED}

        async def _run():
            await asyncio.gather(*[
                self.smart_home_service.climate_turn_off(command=ClimateTurnOff(entity_id=eid))
                for eid in entity_ids
            ])
        async_runner.run(_run())

        return {"output_turn_off": devices}

    def _handle_set_temperature(self, data):
        raw = data.get("output_set_temperature", "")
        print(f"[SmartHomeClimateGraph._handle_set_temperature]: {raw}")

        if not raw:
            return {}

        available_entities = data.get("available_entities", {})
        entries = raw.split("|")

        resolved_any = False
        for entry in entries:
            parts = entry.split(", ", 1)
            if len(parts) != 2:
                continue
            device_str, temp_str = parts[0].strip(), parts[1].strip()

            entity_ids = self._find_entity_ids(
                entity_alias_delimited_str=device_str,
                available_entities=available_entities,
            )

            try:
                temperature = float(temp_str)
            except ValueError:
                continue

            if not entity_ids:
                continue

            resolved_any = True

            async def _run():
                await asyncio.gather(*[
                    self.smart_home_service.climate_set_temperature(
                        command=ClimateSetTemperature(entity_id=eid, temperature=temperature)
                    )
                    for eid in entity_ids
                ])
            async_runner.run(_run())

        if not resolved_any:
            return {"output_set_temperature": DEVICE_NOT_RECOGNIZED}

        return {"output_set_temperature": raw}

    def _handle_set_hvac_mode(self, data):
        raw = data.get("output_set_hvac_mode", "")
        print(f"[SmartHomeClimateGraph._handle_set_hvac_mode]: {raw}")

        if not raw:
            return {}

        available_entities = data.get("available_entities", {})
        entries = raw.split("|")

        resolved_any = False
        for entry in entries:
            parts = entry.split(", ", 1)
            if len(parts) != 2:
                continue
            device_str, mode_str = parts[0].strip(), parts[1].strip().lower()

            ha_mode = HVAC_MODE_MAP.get(mode_str, mode_str)

            entity_ids = self._find_entity_ids(
                entity_alias_delimited_str=device_str,
                available_entities=available_entities,
            )

            if not entity_ids:
                continue

            resolved_any = True

            async def _run():
                await asyncio.gather(*[
                    self.smart_home_service.climate_set_hvac_mode(
                        command=ClimateSetHvacMode(entity_id=eid, hvac_mode=ha_mode)
                    )
                    for eid in entity_ids
                ])
            async_runner.run(_run())

        if not resolved_any:
            return {"output_set_hvac_mode": DEVICE_NOT_RECOGNIZED}

        return {"output_set_hvac_mode": raw}

    def _handle_query_state(self, data):
        raw = data.get("output_query_state", "")
        print(f"[SmartHomeClimateGraph._handle_query_state]: {raw}")

        if not raw:
            return {}

        available_entities = data.get("available_entities", {})
        device_strings = raw.split("|")
        lines = []

        for device_str in device_strings:
            device_str = device_str.strip()
            entity_ids = self._find_entity_ids(
                entity_alias_delimited_str=device_str,
                available_entities=available_entities,
            )

            if not entity_ids:
                lines.append(f"{device_str}: {DEVICE_NOT_RECOGNIZED}")
                continue

            async def _fetch_states(ids, label):
                results = await asyncio.gather(
                    *[self.smart_home_service.climate_get_state(entity_id=eid) for eid in ids],
                    return_exceptions=True,
                )
                fetched = []
                for state in results:
                    if isinstance(state, Exception):
                        print(f"[SmartHomeClimateGraph._handle_query_state][ERROR]: {state}")
                        fetched.append(f"{label}: estado indisponível")
                    else:
                        status = "ligado" if state.is_on else "desligado"
                        state_parts = [status]
                        if state.current_temperature is not None:
                            state_parts.append(f"temperatura atual {state.current_temperature}°C")
                        if state.target_temperature is not None:
                            state_parts.append(f"temperatura alvo {state.target_temperature}°C")
                        if state.hvac_mode is not None:
                            state_parts.append(
                                f"modo {state.hvac_mode.value if hasattr(state.hvac_mode, 'value') else state.hvac_mode}"
                            )
                        fetched.append(f"{label}: {', '.join(state_parts)}")
                return fetched

            lines.extend(async_runner.run(_fetch_states(entity_ids, device_str)))

        return {"output_query_state": "\n".join(lines) if lines else ""}

    def _handle_not_recognized(self, data):
        print(f"[SmartHomeClimateGraph._handle_not_recognized]: Triggered...")
        return {"output_not_recognized": "Not Recognized Triggered"}

    def _handle_final_response(self, data):
        print(
            f"[SmartHomeClimateGraph._handle_final_response]: Aggregating response..."
        )
        parts = []
        if data.get("output_turn_on"):
            parts.append(f"Ligado: {data['output_turn_on']}")
        if data.get("output_turn_off"):
            parts.append(f"Desligado: {data['output_turn_off']}")
        if data.get("output_set_temperature"):
            parts.append(f"Temperatura ajustada: {data['output_set_temperature']}")
        if data.get("output_set_hvac_mode"):
            parts.append(f"Modo alterado: {data['output_set_hvac_mode']}")
        if data.get("output_query_state"):
            parts.append(data["output_query_state"])
        if data.get("output_not_recognized"):
            parts.append("Comando de climatização não reconhecido.")
        return {"output": "\n".join(parts) if parts else NO_ACTION_PERFORMED}

    # ===============================================
    # Private Methods
    # ===============================================

    def _compile(self):
        workflow = StateGraph(SmartHomeClimateGraphState)

        workflow.add_node("classify", RunnableLambda(self._classify_intent))
        workflow.add_node("turn_on", RunnableLambda(self._handle_turn_on))
        workflow.add_node("turn_off", RunnableLambda(self._handle_turn_off))
        workflow.add_node(
            "set_temperature", RunnableLambda(self._handle_set_temperature)
        )
        workflow.add_node("set_hvac_mode", RunnableLambda(self._handle_set_hvac_mode))
        workflow.add_node("query_state", RunnableLambda(self._handle_query_state))
        workflow.add_node("not_recognized", RunnableLambda(self._handle_not_recognized))
        workflow.add_node("final_response", RunnableLambda(self._handle_final_response))
        workflow.add_edge(START, "classify")

        def intent_router(state):
            return state.get("intent", [])

        workflow.add_conditional_edges("classify", intent_router)

        nodes = [
            "turn_on",
            "turn_off",
            "set_temperature",
            "set_hvac_mode",
            "query_state",
            "not_recognized",
        ]
        for node in nodes:
            workflow.add_edge(node, "final_response")

        workflow.add_edge("final_response", END)

        return workflow.compile()

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
            self.load_prompt("smart_home_climate_graph_id_parser_by_alias.md")
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
                print("[_find_entity_ids][ERROR]: Timeout")
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
