from application.graphs.graph import Graph
from domain.entities import GraphInvokeRequest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from datetime import datetime


class OnlyTalkGraph(Graph):
    """
    Only talk category graph
    """

    _context_memory_store: dict[str, InMemoryChatMessageHistory] = {}

    def __init__(self, llm_chat: BaseChatModel, provider: str = "OLLAMA"):
        super().__init__(provider)
        self.llm_chat = llm_chat

    def invoke(self, invoke_request: GraphInvokeRequest) -> str:
        user = invoke_request.user

        formatted_system_message = self.load_prompt("only_talk_graph.md").format(
            user_name=user.name,
            user_summary=user.summary,
            current_datetime=datetime.now().strftime("%d/%m/%Y %H:%M"),
        )

        chat_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", formatted_system_message),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{input}"),
            ]
        )

        chain = chat_prompt | self.llm_chat

        def get_session_history(session_id: str) -> InMemoryChatMessageHistory:
            if session_id not in OnlyTalkGraph._context_memory_store:
                OnlyTalkGraph._context_memory_store[session_id] = (
                    InMemoryChatMessageHistory()
                )
            return OnlyTalkGraph._context_memory_store[session_id]

        chain_with_history = RunnableWithMessageHistory(
            chain,
            get_session_history,
            input_messages_key="input",
            history_messages_key="history",
        )

        response = chain_with_history.invoke(
            {"input": invoke_request.message},
            config={"configurable": {"session_id": user.id}},
        )

        return response.content
