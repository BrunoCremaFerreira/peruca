from domain.entities import GraphInvokeRequest
from domain.graphs.graph import Graph
from langchain_core.language_models.chat_models import BaseChatModel
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder
from datetime import datetime

class OnlyTalkGraph(Graph):
    """
    Only talk category graph
    """

    _context_memory_store = {}

    def __init__(self, llm_chat: BaseChatModel):
        self.llm_chat = llm_chat

    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        personality_template = PromptTemplate(
            input_variables=["user_name", "user_summary", "current_datetime"],
            template=self.load_prompt("only_talk_graph.md")
        )

        user = invoke_request.user
        user_id = user.id
        if user_id not in OnlyTalkGraph._context_memory_store:
            OnlyTalkGraph._context_memory_store[user_id] = ConversationBufferMemory(return_messages=True)

        user_context_memory = OnlyTalkGraph._context_memory_store[user_id]

        formatted_system_message = personality_template.format(
            user_name=user.name,
            user_summary=user.summary,
            current_datetime=datetime.now().strftime("%d/%m/%Y %H:%M")
        )

        chat_prompt = ChatPromptTemplate.from_messages([
            ("system", formatted_system_message),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}")
        ])

        conversation = ConversationChain(
            llm=self.llm_chat,
            memory=user_context_memory,
            prompt=chat_prompt,
            verbose=False
        )
        return conversation.predict(input=invoke_request.message)