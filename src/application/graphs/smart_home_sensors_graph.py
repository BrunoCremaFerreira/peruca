import asyncio
import json
from typing import List, Optional, TypedDict

from application.graphs.graph import Graph
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph, START, END

from domain.entities import GraphInvokeRequest, SensorReading
from domain.interfaces.data_repository import SmartHomeEntityAliasRepository
from domain.services.smart_home_service import SmartHomeService


class SmartHomeSensorsGraphState(TypedDict):
    input: str
    intent: Optional[list]
    output_query_current_state: Optional[str]
    output_query_history: Optional[str]
    output_not_recognized: Optional[str]
    available_entities: Optional[dict]
    output: Optional[str]


class SmartHomeSensorsGraph(Graph):
    """
    Smart Home Sensors Graph — handles sensor state queries and history queries.
    """

    def __init__(
        self,
        llm_chat: BaseChatModel,
        smart_home_service: SmartHomeService,
        smart_home_entity_alias_repository: SmartHomeEntityAliasRepository,
    ):
        self.llm_chat = llm_chat
        self.smart_home_service = smart_home_service
        self.smart_home_entity_alias_repository = smart_home_entity_alias_repository
        self.classification_prompt = ChatPromptTemplate.from_template(
            self.load_prompt("smart_home_sensors_graph.md")
        )

    # ===============================================
    # Graph Nodes
    # ===============================================

    def _classify_intent(self, data):
        print(f"[SmartHomeSensorsGraph._classify_intent]: input={data['input']}")

        chain = self.classification_prompt | self.llm_chat
        response = chain.invoke({"input": data["input"]})
        cleaned = self._remove_thinking_tag(response.content)

        print(f"[SmartHomeSensorsGraph._classify_intent]: raw_output={cleaned}")

        try:
            try:
                parsed = (
                    json.loads(cleaned) if isinstance(cleaned, str) and cleaned else {}
                )
            except (json.JSONDecodeError, ValueError):
                parsed = {}

            intents = parsed.get("intents", ["not_recognized"])
            if not intents:
                intents = ["not_recognized"]

            binary_sensor_entities = self.smart_home_entity_alias_repository.get_all(
                entity_id_starts_with="binary_sensor."
            )
            sensor_entities = self.smart_home_entity_alias_repository.get_all(
                entity_id_starts_with="sensor."
            )
            available_entities = {
                **{e.alias: e.entity_id for e in binary_sensor_entities},
                **{e.alias: e.entity_id for e in sensor_entities},
            }

        except Exception as exc:
            print(f"[SmartHomeSensorsGraph._classify_intent][ERROR]: {exc}")
            parsed = {}
            intents = ["not_recognized"]
            available_entities = {}

        return {
            "intent": intents,
            "input": data["input"],
            "output_query_current_state": parsed.get("query_current_state") or None,
            "output_query_history": parsed.get("query_history") or None,
            "output_not_recognized": parsed.get("not_recognized") or None,
            "available_entities": available_entities,
        }

    def _handle_query_current_state(self, data):
        raw = data.get("output_query_current_state", "")
        print(f"[SmartHomeSensorsGraph._handle_query_current_state]: {raw}")

        if not raw:
            return {}

        available_entities = data.get("available_entities", {})
        entity_ids = self._find_entity_ids(raw, available_entities)

        lines = []
        for entity_id in entity_ids:
            try:
                reading: SensorReading = asyncio.run(
                    self.smart_home_service.sensor_get_state(entity_id)
                )
                name = reading.friendly_name or reading.entity_id
                value = (
                    f"{reading.state} {reading.unit}" if reading.unit else reading.state
                )
                lines.append(f"{name}: {value}")
            except Exception as exc:
                print(
                    f"[SmartHomeSensorsGraph._handle_query_current_state][ERROR]: {exc}"
                )
                lines.append(f"{entity_id}: estado indisponível")

        return {"output_query_current_state": "\n".join(lines) if lines else ""}

    def _handle_query_history(self, data):
        raw = data.get("output_query_history", "")
        print(f"[SmartHomeSensorsGraph._handle_query_history]: {raw}")

        if not raw:
            return {}

        parts = raw.split("|")
        sensor_type = parts[0] if parts else ""
        location = parts[1] if len(parts) > 1 else ""
        hours_back = int(parts[2]) if len(parts) > 2 and parts[2] else 3

        available_entities = data.get("available_entities", {})
        entity_ids = self._find_entity_ids(
            f"{sensor_type}|{location}", available_entities
        )

        lines = []
        for entity_id in entity_ids:
            try:
                history: List[SensorReading] = asyncio.run(
                    self.smart_home_service.sensor_get_history(entity_id, hours_back)
                )
                if history:
                    entries = []
                    for reading in history:
                        time_str = (
                            reading.last_changed.strftime("%H:%M")
                            if reading.last_changed
                            else "?"
                        )
                        entries.append(f"{time_str}: {reading.state}")
                    name = history[0].friendly_name or entity_id
                    lines.append(f"{name}: {' | '.join(entries)}")
                else:
                    lines.append(f"{entity_id}: sem histórico")
            except Exception as exc:
                print(f"[SmartHomeSensorsGraph._handle_query_history][ERROR]: {exc}")
                lines.append(f"{entity_id}: histórico indisponível")

        return {"output_query_history": "\n".join(lines) if lines else ""}

    def _handle_not_recognized(self, data):
        print(f"[SmartHomeSensorsGraph._handle_not_recognized]: Triggered...")
        return {
            "output_not_recognized": "Não consegui identificar qual sensor você quer consultar."
        }

    def _handle_final_response(self, data):
        print(
            f"[SmartHomeSensorsGraph._handle_final_response]: Aggregating response..."
        )

        sensor_data_parts = []
        if data.get("output_query_current_state"):
            sensor_data_parts.append(data["output_query_current_state"])
        if data.get("output_query_history"):
            sensor_data_parts.append(data["output_query_history"])
        if data.get("output_not_recognized"):
            return {
                "output": "Não consegui identificar qual sensor você quer consultar."
            }

        sensor_data = "\n".join(sensor_data_parts)

        response_template = ChatPromptTemplate.from_template(
            self.load_prompt("smart_home_sensors_graph_response.md")
        )
        chain = response_template | self.llm_chat
        llm_response = chain.invoke(
            {
                "user_question": data["input"],
                "sensor_data": sensor_data,
            }
        )
        return {"output": self._remove_thinking_tag(llm_response.content)}

    # ===============================================
    # Private Methods
    # ===============================================

    def _compile(self):
        workflow = StateGraph(SmartHomeSensorsGraphState)

        workflow.add_node("classify", RunnableLambda(self._classify_intent))
        workflow.add_node(
            "query_current_state", RunnableLambda(self._handle_query_current_state)
        )
        workflow.add_node("query_history", RunnableLambda(self._handle_query_history))
        workflow.add_node("not_recognized", RunnableLambda(self._handle_not_recognized))
        workflow.add_node("final_response", RunnableLambda(self._handle_final_response))

        workflow.add_edge(START, "classify")

        def intent_router(state):
            return state.get("intent", [])

        workflow.add_conditional_edges("classify", intent_router)

        for node in ["query_current_state", "query_history", "not_recognized"]:
            workflow.add_edge(node, "final_response")

        workflow.add_edge("final_response", END)

        return workflow.compile()

    def _find_entity_ids(
        self, entity_alias_delimited_str: str, available_entities: dict
    ) -> List[str]:
        parser_template = ChatPromptTemplate.from_template(
            self.load_prompt("smart_home_sensors_graph_id_parser_by_alias.md")
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
                print("[SmartHomeSensorsGraph._find_entity_ids][ERROR]: Timeout")
                return "None"

        entity_ids_str = asyncio.run(_invoke_with_timeout())

        entity_ids = entity_ids_str.split("|")
        entity_ids = [e for e in entity_ids if e.upper() != "NONE" and e.strip() != ""]

        return entity_ids

    # ===============================================
    # Public Methods
    # ===============================================

    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        app = self._compile()
        return app.invoke({"input": invoke_request})
