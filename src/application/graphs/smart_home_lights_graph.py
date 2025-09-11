
import json
from typing import List, Optional, TypedDict
from application.graphs.graph import Graph
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableLambda
from domain.commands import LightTurnOn
from domain.entities import GraphInvokeRequest, SmartHomeEntityAlias
from domain.interfaces.data_repository import SmartHomeEntityAliasRepository
from domain.services.smart_home_service import SmartHomeService

class SmartHomeLightsGraphState(TypedDict):
        input: str
        intent: Optional[list[str]]
        output_turn_on: Optional[str]
        output_turn_off: Optional[str]
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

    def __init__(self, 
                 llm_chat: BaseChatModel, 
                 smart_home_service: SmartHomeService, 
                 smart_home_entity_alias_repository: SmartHomeEntityAliasRepository):
        self.llm_chat = llm_chat
        self.smart_home_service = smart_home_service
        self.smart_home_entity_alias_repository = smart_home_entity_alias_repository
        self.classification_prompt = ChatPromptTemplate.from_template(self.load_prompt("smart_home_lights_graph.md"))

    #===============================================
    # Graph Nodes
    #===============================================

    def _classify_intent(self, data):
        """
        Classify the user's intent based on the input text.
        """
        print(f"[SmartHomeLightsGraph._classify_intent]: input={data['input']}")

        chain = self.classification_prompt | self.llm_chat
        response = chain.invoke({"input": data["input"]})
        cleaned = self._remove_thinking_tag(response.content)

        print(f"[SmartHomeLightsGraph._classify_intent]: raw_output={cleaned}")

        try:
            parsed = eval(cleaned) if isinstance(cleaned, str) else cleaned
            intents = parsed.get("intents", ["not_recognized"])

            # Getting all entity_id x alias for lights devices
            entity_alias_list: List[SmartHomeEntityAlias] = \
                self.smart_home_entity_alias_repository \
                    .get_all(entity_id_starts_with="light.")
            entity_alias_dict = \
                {item.alias: item.entity_id for item in entity_alias_list}
            
        except Exception as e:
            print(f"[SmartHomeLightsGraph._classify_intent][ERROR]: {e}")
            parsed = {}
            intents = ["not_recognized"]
            entity_alias_dict = {}

        return {
            "intent": intents,
            "input": data["input"],
            "output_turn_on": parsed.get("turn_on"),
            "output_turn_off": parsed.get("turn_off"),
            "output_change_color": parsed.get("change_color"),
            "output_change_bright": parsed.get("change_bright"),
            "output_change_mode": parsed.get("change_mode"),
            "output_not_recognized": parsed.get("not_recognized"),
            "available_entities": entity_alias_dict
        }

    def _handle_turn_on(self, data):
        devices = data.get("output_turn_on", "")
        print(f"[SmartHomeLightsGraph._handle_turn_on]: {devices}")

        if not devices:
            return {}
        
        entity_id = self. \
            _find_entity_ids(entity_alias_delimited_str=devices, 
                             available_entities=data.get("available_entities", {}))
        
        if not entity_id:
            return {"output_turn_on": "Device not found"}

        turn_on_command = LightTurnOn(entity_id=entity_id)
        self.smart_home_service.light_turn_on(turn_on_command=turn_on_command)
        return {"output_turn_on": devices}

    def _handle_turn_off(self, data):
        devices = data.get("output_turn_off", "")
        print(f"[SmartHomeLightsGraph._handle_turn_off]: {devices}")

        if not devices:
            return {}
        
        entity_id = self. \
            _find_entity_ids(entity_alias_delimited_str=devices, 
                             available_entities=data.get("available_entities", {}))
        
        if not entity_id:
            return {"output_turn_on": "Device not found"}
        
        self.smart_home_service.light_turn_off(entity_id=entity_id)
        return {"output_turn_off": devices}

    def _handle_change_color(self, data):
        devices = data.get("output_change_color", "")
        if devices:
            print(f"[SmartHomeLightsGraph._handle_change_color]: {devices}")
            return {"output_change_color": devices}
        return {}

    def _handle_change_bright(self, data):
        devices = data.get("output_change_bright", "")
        if devices:
            print(f"[SmartHomeLightsGraph._handle_change_bright]: {devices}")
            return {"output_change_bright": devices}
        return {}

    def _handle_change_mode(self, data):
        devices = data.get("output_change_mode", "")
        if devices:
            print(f"[SmartHomeLightsGraph._handle_change_mode]: {devices}")
            return {"output_change_mode": devices}
        return {}

    def _handle_final_response(self, data):
        print(f"[SmartHomeLightsGraph._handle_final_response]: Aggregating response...")
        return {
            "output": {
                "turn_on": data.get("output_turn_on", ""),
                "turn_off": data.get("output_turn_off", ""),
                "change_color": data.get("output_change_color", ""),
                "change_bright": data.get("output_change_bright", ""),
                "change_mode": data.get("output_change_mode", ""),
                "not_recognized": data.get("output_not_recognized", "")
            }
        }

    def _handle_not_recognized(self, data):
        print(f"[SmartHomeLightsGraph.handle_not_recognized]: Triggered...")
        return {"output_not_recognized": "Not Recognized Triggered"}

    #===============================================
    # Private Methods
    #===============================================

    def _compile(self):
        workflow = StateGraph(SmartHomeLightsGraphState)

        workflow.add_node("classify", RunnableLambda(self._classify_intent))
        workflow.add_node("turn_on", RunnableLambda(self._handle_turn_on))
        workflow.add_node("turn_off", RunnableLambda(self._handle_turn_off))
        workflow.add_node("change_color", RunnableLambda(self._handle_change_color))
        workflow.add_node("change_bright", RunnableLambda(self._handle_change_bright))
        workflow.add_node("change_mode", RunnableLambda(self._handle_change_mode))
        workflow.add_node("not_recognized", RunnableLambda(self._handle_not_recognized))
        workflow.add_node("final_response", RunnableLambda(self._handle_final_response))
        workflow.set_entry_point("classify")

        def intent_router(state):
            return state.get("intent", [])
        
        workflow.add_conditional_edges("classify", intent_router)

        nodes = ["turn_on", 
                 "turn_off",
                 "change_color",
                 "change_bright",
                 "change_mode",
                 "not_recognized"]

        for node in nodes:
            workflow.add_edge(node, "final_response")

        workflow.add_edge("final_response", END)

        return workflow.compile()

    def _find_entity_ids(self, entity_alias_delimited_str: str, available_entities):
        parser_template = ChatPromptTemplate.from_template(
            self.load_prompt("smart_home_lights_graph_id_parser_by_alias.md"))
        
        chain = parser_template | self.llm_chat
        response = chain.invoke({
            "input": entity_alias_delimited_str, 
            "available_entities": str(available_entities)})
        return self._remove_thinking_tag(response.content)

    #===============================================
    # Public Methods
    #===============================================

    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        app = self._compile()
        return app.invoke({"input": invoke_request})