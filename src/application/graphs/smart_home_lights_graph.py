
from typing import List, Optional, TypedDict
from application.graphs.graph import Graph
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableLambda
from domain.entities import GraphInvokeRequest
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
        output: Optional[str]

class SmartHomeLightsGraph(Graph):
    """
    Smart Home Lights Graph
    """

    def __init__(self, llm_chat: BaseChatModel, smart_home_service: SmartHomeService):
        self.llm_chat = llm_chat
        self.smart_home_service = smart_home_service
        self.classification_prompt = ChatPromptTemplate.from_template(self.load_prompt("smart_home_lights_graph.md"))

    #===============================================
    # Graph Nodes
    #===============================================

    def _classify_intent(self, data):
         pass
    
    def _handle_final_response(self, data):
         pass
    
    def _handle_turn_on(self, data):
         pass
    
    def _handle_turn_off(self, data):
         pass
    
    def _handle_change_color(self, data):
         pass

    def _handle_change_bright(self, data):
         pass

    def _handle_change_mode(self, data):
         pass

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

    #===============================================
    # Public Methods
    #===============================================

    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        app = self._compile()
        return app.invoke({"input": invoke_request})