import asyncio
from infra import async_runner
import json
import logging
from typing import List, Optional, TypedDict

from application.graphs.graph import Graph
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph, START, END

from domain.entities import GraphInvokeRequest, SensorReading
from domain.interfaces.data_repository import SmartHomeEntityAliasRepository
from domain.services.clock import format_local
from domain.services.smart_home_service import SmartHomeService


logger = logging.getLogger(__name__)


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
        provider: str = "OLLAMA",
        strip_think_directive: bool = False,
    ):
        super().__init__(provider, strip_think_directive)
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
        logger.debug("classify_intent input=%r", data["input"])

        chain = self.classification_prompt | self.llm_chat
        response = chain.invoke({"input": data["input"]})
        extracted = self._extract_structured_output(response.content)

        logger.debug("classify_intent raw_output=%r", extracted)

        try:
            try:
                parsed = json.loads(extracted) if extracted else {}
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
            logger.warning("classify_intent failed: %s", exc)
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
        logger.debug("handle_query_current_state raw=%r", raw)

        if not raw:
            return {}

        available_entities = data.get("available_entities", {})
        entity_ids = self._find_entity_ids(raw, available_entities)

        async def _fetch_states(ids):
            results = await asyncio.gather(
                *[self.smart_home_service.sensor_get_state(eid) for eid in ids],
                return_exceptions=True,
            )
            fetched = []
            for eid, reading in zip(ids, results):
                if isinstance(reading, Exception):
                    logger.error(
                        "handle_query_current_state failed for %s: %s",
                        eid,
                        reading,
                        exc_info=reading,
                    )
                    fetched.append(f"{eid}: estado indisponível")
                else:
                    name = reading.friendly_name or reading.entity_id
                    value = (
                        f"{reading.state} {reading.unit}" if reading.unit else reading.state
                    )
                    fetched.append(f"{name}: {value}")
            return fetched

        lines = async_runner.run(_fetch_states(entity_ids))
        return {"output_query_current_state": "\n".join(lines) if lines else ""}

    def _handle_query_history(self, data):
        raw = data.get("output_query_history", "")
        logger.debug("handle_query_history raw=%r", raw)

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

        # `last_changed` is a real instant (Home Assistant hands it back in UTC),
        # not a civil date: it must be shown on the user's wall clock.
        user_timezone = data["input"].user_timezone

        async def _fetch_histories(ids, back):
            results = await asyncio.gather(
                *[self.smart_home_service.sensor_get_history(eid, back) for eid in ids],
                return_exceptions=True,
            )
            fetched = []
            for eid, history in zip(ids, results):
                if isinstance(history, Exception):
                    logger.error(
                        "handle_query_history failed for %s: %s",
                        eid,
                        history,
                        exc_info=history,
                    )
                    fetched.append(f"{eid}: histórico indisponível")
                elif history:
                    entries = []
                    for reading in history:
                        time_str = (
                            format_local(reading.last_changed, user_timezone, "%H:%M")
                            if reading.last_changed
                            else "?"
                        )
                        entries.append(f"{time_str}: {reading.state}")
                    name = history[0].friendly_name or eid
                    fetched.append(f"{name}: {' | '.join(entries)}")
                else:
                    fetched.append(f"{eid}: sem histórico")
            return fetched

        lines = async_runner.run(_fetch_histories(entity_ids, hours_back))
        return {"output_query_history": "\n".join(lines) if lines else ""}

    def _handle_not_recognized(self, data):
        logger.info("handle_not_recognized triggered")
        return {
            "output_not_recognized": "Não consegui identificar qual sensor você quer consultar."
        }

    def _handle_final_response(self, data):
        logger.info("handle_final_response: aggregating response")

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
                logger.warning("find_entity_ids timed out")
                return "None"

        entity_ids_str = async_runner.run(_invoke_with_timeout())

        entity_ids = entity_ids_str.split("|")
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
