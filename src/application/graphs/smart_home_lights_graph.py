
from typing import List, Optional, TypedDict
from application.graphs.graph import Graph
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel

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


    #===============================================
    # Private Methods
    #===============================================


    #===============================================
    # Public Methods
    #===============================================

    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        """
        Execute LLM processing
        """
        pass