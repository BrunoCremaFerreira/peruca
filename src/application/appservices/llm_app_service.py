from application.appservices.view_models import ChatRequest
from domain.entities import GraphInvokeRequest, User
from domain.exceptions import NofFoundValidationError
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

    def chat(self, chat_request: ChatRequest) -> str:
        print(f"[LlmAppService.chat]: Request: {{ {chat_request} }}")
        
        user = self.user_repository.get_by_external_id(external_id=chat_request.external_user_id)

        if not user:
            raise NofFoundValidationError(entity_name="user", key_name="external_id", value= chat_request.external_user_id)

        invoke_request = GraphInvokeRequest(message=chat_request.message, user=user)
        result = self.main_graph.invoke(invoke_request=invoke_request)

        print(f"[LlmAppService.chat]: Response: '{result}'")
        return f"{result}"

        
