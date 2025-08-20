
from application.graphs.graph import Graph
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel

from domain.services.smart_home_service import SmartHomeService


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