import ast
import logging

from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph, START, END
from langchain_core.prompts import ChatPromptTemplate
from typing import Optional, TypedDict
from langchain_core.language_models.chat_models import BaseChatModel
from application.graphs.graph import Graph
from application.graphs.markers import SHOPPING_LIST_HEADER
from application.graphs.only_talk_graph import OnlyTalkGraph
from application.graphs.shopping_list_graph import ShoppingListGraph
from application.graphs.smart_home_lights_graph import SmartHomeLightsGraph
from application.graphs.smart_home_climate_graph import SmartHomeClimateGraph
from application.graphs.smart_home_sensors_graph import SmartHomeSensorsGraph
from application.graphs.smart_home_cameras_graph import SmartHomeCamerasGraph
from domain.entities import GraphInvokeRequest
from infra.utils import is_null_or_whitespace


logger = logging.getLogger(__name__)


class MainGraphState(TypedDict):
    input: str
    intent: Optional[list[str]]
    output_lights: Optional[str]
    output_shopping: Optional[str]
    output_cams: Optional[str]
    output_only_talking: Optional[str]
    output_climate: Optional[str]
    output_sensors: Optional[str]
    output_music: Optional[str]
    output_vehicle: Optional[str]
    output: Optional[str]
    # Side channel: the factual image description produced by the only_talk
    # graph. Consumed by LlmAppService for history persistence; deliberately
    # NOT read by _handle_final_response so it never leaks into `output`.
    image_description: Optional[str]
    # Side channel: the #N handle of an image re-visited this turn (Fase C), so
    # LlmAppService can persist the refreshed description under that handle.
    revised_image_index: Optional[str]


class MainGraph(Graph):
    def __init__(
        self,
        llm_chat: BaseChatModel,
        only_talk_graph: OnlyTalkGraph,
        shopping_list_graph: ShoppingListGraph,
        smart_home_lights_graph: SmartHomeLightsGraph,
        smart_home_climate_graph: SmartHomeClimateGraph,
        smart_home_sensors_graph: SmartHomeSensorsGraph,
        smart_home_cameras_graph: SmartHomeCamerasGraph = None,
        music_graph=None,
        vehicle_maintenance_graph=None,
        provider: str = "OLLAMA",
        strip_think_directive: bool = False,
    ):
        super().__init__(provider, strip_think_directive)
        self.llm_chat = llm_chat
        self.only_talk_graph = only_talk_graph
        self.shopping_list_graph = shopping_list_graph
        self.smart_home_lights_graph = smart_home_lights_graph
        self.smart_home_climate_graph = smart_home_climate_graph
        self.smart_home_sensors_graph = smart_home_sensors_graph
        self.smart_home_cameras_graph = smart_home_cameras_graph
        self.music_graph = music_graph
        self.vehicle_maintenance_graph = vehicle_maintenance_graph
        self.classification_prompt = ChatPromptTemplate.from_template(
            self.load_prompt("main_graph.md")
        )
        self.final_response_prompt = ChatPromptTemplate.from_template(
            self.load_prompt("main_graph_final_response.md")
        )

    # ===============================================
    # Graph Nodes
    # ===============================================
    def _classify_intent(self, data):
        request = data["input"]
        # Text-empty + image present: route straight to free conversation
        # without spending an LLM call (and never feeding the image to the
        # classifier). Images alone are always a "look at this" request.
        if request.images and is_null_or_whitespace(request.message):
            return {"intent": ["only_talking"], "input": request}

        music_is_playing = data["input"].context_hints.get("music_is_playing", False)
        hint_str = (
            "Sim, há música tocando no momento."
            if music_is_playing
            else "Não."
        )
        user_vehicles = data["input"].context_hints.get("user_vehicles") or "nenhum"
        invoke_payload = {
            "input": data["input"].message,
            "music_is_playing": hint_str,
            "user_vehicles": user_vehicles,
        }
        chain = self.classification_prompt | self.llm_chat
        try:
            response = chain.invoke(invoke_payload)
        except Exception:
            response = chain.invoke({"input": data["input"].message, "music_is_playing": hint_str})
        raw_content = response.content
        extracted = self._extract_structured_output(raw_content)
        if extracted is None:
            logger.warning(
                "classify_intent fallback: no structure found. raw=%r", raw_content
            )
            return {"intent": ["only_talking"], "input": data["input"]}
        try:
            intents = ast.literal_eval(extracted)
            if isinstance(intents, str):
                intents = [intents]
        except Exception:
            logger.warning(
                "classify_intent fallback: eval failed. extracted=%r", extracted
            )
            intents = ["only_talking"]
        return {"intent": intents, "input": data["input"]}

    def _handle_music(self, data):
        logger.info("music graph triggered")
        result = self.music_graph.invoke(invoke_request=data["input"])
        return {"output_music": result.get("output")}

    def _handle_vehicle_maintenance(self, data):
        logger.info("vehicle_maintenance graph triggered")
        result = self.vehicle_maintenance_graph.invoke(invoke_request=data["input"])
        # Main-classifier false positive: the sub-classifier found no actionable
        # maintenance intent. Degrade to free conversation instead of replying
        # "I did not understand" (§9.1). Only +1 LLM call, and only on this path.
        if result.get("intent") == ["not_recognized"]:
            logger.info("vehicle_maintenance not_recognized — falling back to only_talk")
            fallback = self.only_talk_graph.invoke(invoke_request=data["input"])
            output = fallback.get("output") if isinstance(fallback, dict) else fallback
            return {"output_vehicle": self._remove_thinking_tag(output or "")}
        return {"output_vehicle": result.get("output")}

    def _handle_final_response(self, data):
        output_shopping = data.get("output_shopping")
        listing = (
            output_shopping
            if output_shopping
            and output_shopping.strip()
            and SHOPPING_LIST_HEADER in output_shopping
            else None
        )

        mergeable_shopping = None if listing else output_shopping

        outputs = [
            e
            for e in [
                data.get("output_lights"),
                mergeable_shopping,
                data.get("output_cams"),
                data.get("output_only_talking"),
                data.get("output_climate"),
                data.get("output_sensors"),
                data.get("output_music"),
                data.get("output_vehicle"),
            ]
            if e is not None and e.strip()
        ]

        if len(outputs) <= 1:
            merged = outputs[0] if outputs else ""
        else:
            responses = "\n\n".join(outputs)
            final_reponse_chain = self.final_response_prompt | self.llm_chat
            llm_response = final_reponse_chain.invoke(
                {"input": data["input"].message, "responses": responses}
            )
            merged = self._remove_thinking_tag(llm_response.content)
            if not merged or not merged.strip():
                merged = "\n\n".join(outputs)

        # A verbatim listing is bypassed from the LLM (the model can never
        # rewrite its bytes), but any legitimate merged conversational content
        # is still appended after it so nothing the user asked for is dropped.
        if listing and merged and merged.strip():
            response = f"{listing}\n\n{merged}"
        elif listing:
            response = listing
        else:
            response = merged

        return {"output": response}

    def _handle_smart_home_lights(self, data):
        logger.info("smart_home_lights graph triggered")
        result: str = self.smart_home_lights_graph.invoke(invoke_request=data["input"])
        return {"output_lights": result.get("output")}

    def _handle_smart_home_climate(self, data):
        logger.info("smart_home_climate graph triggered")
        result = self.smart_home_climate_graph.invoke(invoke_request=data["input"])
        return {"output_climate": result.get("output")}

    def _handle_smart_home_sensors(self, data):
        logger.info("smart_home_sensors graph triggered")
        result = self.smart_home_sensors_graph.invoke(invoke_request=data["input"])
        return {"output_sensors": result.get("output")}

    def _handle_smart_home_security_cams(self, data):
        logger.info("smart_home_security_cams graph triggered")
        result = self.smart_home_cameras_graph.invoke(
            GraphInvokeRequest(message=data["input"].message, user=data["input"].user)
        )
        return {"output_cams": result.get("output", "")}

    def _handle_shopping_list(self, data):
        logger.info("shopping_list graph triggered")
        result: str = self.shopping_list_graph.invoke(invoke_request=data["input"])
        return {"output_shopping": result.get("output")}

    def _handle_only_talking(self, data):
        logger.info("only_talking graph triggered")
        result = self.only_talk_graph.invoke(invoke_request=data["input"])
        # The only_talk graph now returns a dict {"output", "image_description"};
        # a bare string is tolerated for backward compatibility.
        if isinstance(result, dict):
            output = result.get("output", "")
            image_description = result.get("image_description")
            revised_image_index = result.get("revised_image_index")
        else:
            output = result
            image_description = None
            revised_image_index = None
        return {
            "output_only_talking": f"{self._remove_thinking_tag(output or '')}",
            "image_description": image_description,
            "revised_image_index": revised_image_index,
        }

    # ===============================================
    # Private Methods
    # ===============================================

    def _compile(self):
        workflow = StateGraph(MainGraphState)

        workflow.add_node("classify", RunnableLambda(self._classify_intent))
        workflow.add_node(
            "smart_home_lights", RunnableLambda(self._handle_smart_home_lights)
        )
        workflow.add_node(
            "smart_home_security_cams",
            RunnableLambda(self._handle_smart_home_security_cams),
        )
        workflow.add_node("shopping_list", RunnableLambda(self._handle_shopping_list))
        workflow.add_node("only_talking", RunnableLambda(self._handle_only_talking))
        workflow.add_node(
            "smart_home_climate", RunnableLambda(self._handle_smart_home_climate)
        )
        workflow.add_node(
            "smart_home_sensors", RunnableLambda(self._handle_smart_home_sensors)
        )

        action_nodes = [
            "smart_home_lights",
            "smart_home_security_cams",
            "shopping_list",
            "only_talking",
            "smart_home_climate",
            "smart_home_sensors",
        ]

        if self.music_graph is not None:
            workflow.add_node("music", RunnableLambda(self._handle_music))
            action_nodes.append("music")

        if self.vehicle_maintenance_graph is not None:
            workflow.add_node(
                "vehicle_maintenance",
                RunnableLambda(self._handle_vehicle_maintenance),
            )
            action_nodes.append("vehicle_maintenance")

        workflow.add_node("final_response", RunnableLambda(self._handle_final_response))
        workflow.add_edge(START, "classify")

        def intent_router(state):
            return state.get("intent", [])

        workflow.add_conditional_edges("classify", intent_router)

        for node in action_nodes:
            workflow.add_edge(node, "final_response")

        workflow.add_edge("final_response", END)

        return workflow.compile()

    # ===============================================
    # Public Methods
    # ===============================================
    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        if self._compiled_graph is None:
            self._compiled_graph = self._compile()
        app = self._compiled_graph
        return app.invoke({"input": invoke_request})
