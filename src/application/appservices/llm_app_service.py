from application.appservices.view_models import ChatRequest
from application.graphs.main_graph import MainGraph
from domain.entities import GraphInvokeRequest, User
from domain.exceptions import EmptyParamValidationError, NofFoundValidationError
from domain.interfaces.repository import ContextRepository, UserRepository
from infra.utils import is_null_or_whitespace

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
        
        if is_null_or_whitespace(chat_request.external_user_id):
            raise EmptyParamValidationError(param_name="external_user_id")

        user = self.user_repository.get_by_external_id(external_id=chat_request.external_user_id)

        if not user:
            raise NofFoundValidationError(entity_name="user", key_name="external_id", value= chat_request.external_user_id)

        invoke_request = GraphInvokeRequest(message=chat_request.message, user=user)
        result = self.main_graph.invoke(invoke_request=invoke_request)
        output = result.get("output")
        intents = result.get("intent")

        print(f"[LlmAppService.chat]: Response: '{result}'")
        return {"intents": intents, "output": output}

        
