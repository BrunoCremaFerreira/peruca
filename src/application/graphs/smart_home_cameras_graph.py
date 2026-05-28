import asyncio
import base64
import json
from typing import List, Optional, TypedDict

from application.graphs.graph import Graph
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph, START, END

from domain.entities import GraphInvokeRequest, SmartHomeCamera, SmartHomeCameraSnapshot
from domain.interfaces.data_repository import SmartHomeEntityAliasRepository
from domain.services.smart_home_service import SmartHomeService


class SmartHomeCamerasGraphState(TypedDict):
    input: str
    intent: Optional[list]
    output_show_snapshot: Optional[str]
    output_check_status: Optional[str]
    output_not_recognized: Optional[str]
    available_entities: Optional[dict]
    output: Optional[str]


class SmartHomeCamerasGraph(Graph):
    """
    Smart Home Cameras Graph — handles camera snapshot requests and status checks.
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
            self.load_prompt("smart_home_cameras_graph.md")
        )

    # ===============================================
    # Graph Nodes
    # ===============================================

    def _classify_intent(self, data):
        print(f"[SmartHomeCamerasGraph._classify_intent]: input={data['input']}")

        chain = self.classification_prompt | self.llm_chat
        response = chain.invoke({"input": data["input"]})
        cleaned = self._remove_thinking_tag(response.content)

        print(f"[SmartHomeCamerasGraph._classify_intent]: raw_output={cleaned}")

        try:
            try:
                parsed = (
                    json.loads(cleaned) if isinstance(cleaned, str) and cleaned else {}
                )
            except (json.JSONDecodeError, ValueError):
                parsed = {}

            intents = parsed.get("intents", ["not_recognized"])
            if not isinstance(intents, list) or not intents:
                intents = ["not_recognized"]

            camera_entities = self.smart_home_entity_alias_repository.get_all(
                entity_id_starts_with="camera."
            )
            available_entities = {e.alias: e.entity_id for e in camera_entities}

        except Exception as exc:
            print(f"[SmartHomeCamerasGraph._classify_intent][ERROR]: {exc}")
            parsed = {}
            intents = ["not_recognized"]
            available_entities = {}

        return {
            "intent": intents,
            "input": data["input"],
            "output_show_snapshot": parsed.get("show_snapshot") or None,
            "output_check_status": parsed.get("check_status") or None,
            "output_not_recognized": parsed.get("not_recognized") or None,
            "available_entities": available_entities,
        }

    def _handle_show_snapshot(self, data):
        raw = data.get("output_show_snapshot", "")
        print(f"[SmartHomeCamerasGraph._handle_show_snapshot]: {raw}")

        if not raw:
            return {}

        available_entities = data.get("available_entities", {})
        entity_ids = self._find_entity_ids(raw, available_entities)

        if not entity_ids:
            return {"output_show_snapshot": "Dispositivo não encontrado."}

        entity_id = entity_ids[0]
        try:
            snapshot: SmartHomeCameraSnapshot = asyncio.run(
                self.smart_home_service.camera_get_snapshot(entity_id)
            )
            encoded = base64.b64encode(snapshot.image_bytes).decode()
            return {"output_show_snapshot": f"data:image/jpeg;base64,{encoded}"}
        except Exception as exc:
            print(f"[SmartHomeCamerasGraph._handle_show_snapshot][ERROR]: {exc}")
            return {"output_show_snapshot": f"{entity_id}: snapshot indisponível"}

    def _handle_check_status(self, data):
        raw = data.get("output_check_status", "")
        print(f"[SmartHomeCamerasGraph._handle_check_status]: {raw}")

        if not raw:
            return {}

        available_entities = data.get("available_entities", {})
        entity_ids = self._find_entity_ids(raw, available_entities)

        if not entity_ids:
            return {"output_check_status": "Dispositivo não encontrado."}

        entity_id = entity_ids[0]
        try:
            camera: SmartHomeCamera = asyncio.run(
                self.smart_home_service.camera_get_state(entity_id)
            )
            name = camera.friendly_name or camera.entity_id
            return {"output_check_status": f"{name}: {camera.state}"}
        except Exception as exc:
            print(f"[SmartHomeCamerasGraph._handle_check_status][ERROR]: {exc}")
            return {"output_check_status": f"{entity_id}: estado indisponível"}

    def _handle_not_recognized(self, data):
        print(f"[SmartHomeCamerasGraph._handle_not_recognized]: Triggered...")
        return {
            "output_not_recognized": "Não consegui identificar qual câmera você quer consultar."
        }

    def _handle_final_response(self, data):
        print(
            f"[SmartHomeCamerasGraph._handle_final_response]: Aggregating response..."
        )

        if data.get("output_not_recognized"):
            return {
                "output": "Não consegui identificar qual câmera você quer consultar."
            }

        parts = []
        if data.get("output_show_snapshot"):
            parts.append(data["output_show_snapshot"])
        if data.get("output_check_status"):
            parts.append(data["output_check_status"])

        return {"output": "\n".join(parts) if parts else ""}

    # ===============================================
    # Private Methods
    # ===============================================

    def _compile(self):
        workflow = StateGraph(SmartHomeCamerasGraphState)

        workflow.add_node("classify", RunnableLambda(self._classify_intent))
        workflow.add_node("show_snapshot", RunnableLambda(self._handle_show_snapshot))
        workflow.add_node("check_status", RunnableLambda(self._handle_check_status))
        workflow.add_node("not_recognized", RunnableLambda(self._handle_not_recognized))
        workflow.add_node("final_response", RunnableLambda(self._handle_final_response))

        workflow.add_edge(START, "classify")

        def intent_router(state):
            return state.get("intent", [])

        workflow.add_conditional_edges("classify", intent_router)

        for node in ["show_snapshot", "check_status", "not_recognized"]:
            workflow.add_edge(node, "final_response")

        workflow.add_edge("final_response", END)

        return workflow.compile()

    def _find_entity_ids(
        self, entity_alias_delimited_str: str, available_entities: dict
    ) -> List[str]:
        parser_template = ChatPromptTemplate.from_template(
            self.load_prompt("smart_home_cameras_graph_id_parser_by_alias.md")
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
                print("[SmartHomeCamerasGraph._find_entity_ids][ERROR]: Timeout")
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
        return app.invoke({"input": invoke_request.message})
