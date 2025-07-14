from domain.graphs.graph import Graph


class OnlyTalkGraph(Graph):
    """
    Only talk category graph
    """

    def __init__(self, chat_llm):
        self.chat_llm = chat_llm

    def invoke(self, user_message) -> dict:
        return self.chat_llm.invoke(f"/no_think Usuário: {user_message}\nPeruca:")