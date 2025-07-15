from domain.graphs.graph import Graph
from langchain_community.chat_models import ChatOllama
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder
from datetime import datetime

class OnlyTalkGraph(Graph):
    """
    Only talk category graph
    """

    def __init__(self, chat_llm):
        self.chat_llm = chat_llm
        self.user = {
            "name": "Bruno",
            "description": ""
        }
        self.context_memory = []
        self.personality_template = PromptTemplate(
            input_variables=["user_name", "user_description", "current_datetime"],
            template=self.load_prompt("only_talk_graph.md")
        )

    def invoke(self, user_message) -> dict:
        formatted_system_message = self.personality_template.format(
        user_name=self.user["name"],
        user_description=self.user["description"],
        current_datetime=datetime.now().strftime("%d/%m/%Y %H:%M")
)
        return self.chat_llm.invoke(f"/no_think Usuário: {user_message}\nPeruca:")