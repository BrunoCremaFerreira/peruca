import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from application.graphs.graph import Graph
from domain.entities import GraphInvokeRequest

NO_MEMORIES_TEXT = "(nenhuma memória registrada até o momento)"


class MemoryGraph(Graph):
    """
    Memory extraction graph (single-step chain: prompt | llm)
    """

    def __init__(self, llm_chat: BaseChatModel, provider: str = "OLLAMA"):
        super().__init__(provider)
        self.llm_chat = llm_chat

    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        if invoke_request.memories:
            existing_memories = "\n".join(
                f"- {memory}" for memory in invoke_request.memories
            )
        else:
            existing_memories = NO_MEMORIES_TEXT

        prompt = ChatPromptTemplate.from_template(self.load_prompt("memory_graph.md"))
        chain = prompt | self.llm_chat

        response = chain.invoke(
            {
                "input": invoke_request.message,
                "existing_memories": existing_memories,
            }
        )

        cleaned = self._remove_thinking_tag(response.content)

        try:
            parsed = json.loads(cleaned) if isinstance(cleaned, str) else cleaned
            if not isinstance(parsed, dict):
                parsed = {}
        except (json.JSONDecodeError, ValueError, TypeError):
            parsed = {}

        memories = parsed.get("memories", [])
        if not isinstance(memories, list):
            memories = []

        return {"memories": memories}
