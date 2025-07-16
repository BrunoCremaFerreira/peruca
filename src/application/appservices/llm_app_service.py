from domain.entities import GraphInvokeRequest, User
from domain.graphs.main_graph import MainGraph
from domain.interfaces.repository import ContextRepository, UserRepository

class LlmAppService:
    """
    LLM Application Service
    """

    def __init__(self, main_graph: MainGraph, context_repository: ContextRepository, user_repository: UserRepository) -> None:
        self.main_graph = main_graph
        self.context_repository = context_repository
        self.user_repository = user_repository


    #===============================================
    # Public Methods
    #===============================================

    def chat(self, message: str, user_id: str, chat_id: str) -> str:
        print(f"[LlmAppService.chat]: Request: {{ user_id='{user_id}' message='{message}' }}")
        
        user = self.user_repository.get_by_id(user_id=user_id)

        invoke_request = GraphInvokeRequest(message=message, user=user)
        result = self.main_graph.invoke(invoke_request=invoke_request)

        print(f"[LlmAppService.chat]: Response: '{result}'")
        return f"{result}"

        
