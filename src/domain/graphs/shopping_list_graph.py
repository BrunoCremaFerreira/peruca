from langchain_core.language_models.chat_models import BaseChatModel
from domain.entities import GraphInvokeRequest
from domain.graphs.graph import Graph


class ShoppingListGraph(Graph):
    """
    Shopping List category graph
    """

    def __init__(self, llm_chat: BaseChatModel):
        self.llm_chat = llm_chat


    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        """
        Execute LLM processing
        """
        
        return "Shopping command List Triggered"