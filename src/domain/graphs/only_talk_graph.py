from domain.graphs.graph import Graph
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_community.chat_models import ChatOllama
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder
from datetime import datetime

class OnlyTalkGraph(Graph):
    """
    Only talk category graph
    """

    def __init__(self, llm_chat: BaseChatModel):
        self.llm_chat = llm_chat

        # Mocked user - Test
        self.user = {
            "name": "Bruno",
            "description": ""
        }
        self.context_memory = ConversationBufferMemory(return_messages=True)
        

    def invoke(self, user_message: str) -> dict:
        personality_template = PromptTemplate(
            input_variables=["user_name", "user_description", "current_datetime"],
            template=self.load_prompt("only_talk_graph.md")
        )

        formatted_system_message = personality_template.format(
            user_name=self.user["name"],
            user_description=self.user["description"],
            current_datetime=datetime.now().strftime("%d/%m/%Y %H:%M")
        )

        chat_prompt = ChatPromptTemplate.from_messages([
            ("system", formatted_system_message),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}")
        ])

        conversation = ConversationChain(
            llm=self.llm_chat,
            memory=self.context_memory,
            prompt=chat_prompt,
            verbose=False
        )
        return conversation.predict(input=user_message)