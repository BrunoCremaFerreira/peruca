from typing import Callable

from application.graphs.graph import Graph
from domain.entities import GraphInvokeRequest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from datetime import datetime


class OnlyTalkGraph(Graph):
    """
    Only talk category graph
    """

    def __init__(
        self,
        llm_chat: BaseChatModel,
        get_session_history: Callable[[str], BaseChatMessageHistory],
        provider: str = "OLLAMA",
    ):
        super().__init__(provider)
        self.llm_chat = llm_chat
        self._get_session_history = get_session_history

    def invoke(self, invoke_request: GraphInvokeRequest) -> str:
        user = invoke_request.user

        if invoke_request.memories:
            user_memories = "\n".join(
                f"- {memory}" for memory in invoke_request.memories
            )
        else:
            user_memories = (
                "(você ainda não tem memórias registradas sobre esta pessoa)"
            )

        formatted_system_message = self.load_prompt("only_talk_graph.md").format(
            user_name=user.name,
            user_summary=user.summary,
            user_memories=user_memories,
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

        history_messages = self._get_session_history(user.id).messages

        response = chain.invoke(
            {"input": invoke_request.message, "history": history_messages}
        )

        return response.content
