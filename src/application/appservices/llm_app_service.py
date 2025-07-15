from domain.entities import GraphInvokeRequest, User
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
        print(f"[LlmAppService.chat]: Request: {{ user_id='{user_id}' message='{message}' }}")
        user = User(id=user_id, name= "Bruno", summary="- Arquiteto de Software e engenheiro elétrico, gosta de temas complexos sobre filosofia, psicologia e tecnologia.")

        invoke_request = GraphInvokeRequest(message=message, user=user)
        result = self.main_graph.invoke(invoke_request=invoke_request)

        print(f"[LlmAppService.chat]: Response: '{result}'")
        return f"{result}"

        
