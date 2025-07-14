from domain.graphs.main_graph import MainGraph
from domain.interfaces.repository import ContextRepository

class LlmAppService:
    """
    LLM Application Service
    """

    def __init__(self, context_repository: ContextRepository, main_graph: MainGraph) -> None:
        self.context_repository = context_repository
        self.main_graph = main_graph


    #===============================================
    # Public Methods
    #===============================================

    def chat(self, message: str, user_id: str, chat_id: str) -> str:
        return self.main_graph.invoke(user_message=message)

        
