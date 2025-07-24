from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph, END
from langchain_core.prompts import ChatPromptTemplate
from typing import TypedDict, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from domain.entities import GraphInvokeRequest
from domain.graphs.graph import Graph
from domain.graphs.only_talk_graph import OnlyTalkGraph
from domain.graphs.shopping_list_graph import ShoppingListGraph

class MainGraphState(TypedDict):
        input: str
        intent: Optional[list[str]]
        output_lights: Optional[str]
        output_shopping: Optional[str]
        output_cams: Optional[str]
        output_only_talking: Optional[str]
        output: Optional[str]

class MainGraph(Graph):

    def __init__(self, 
                 llm_chat: BaseChatModel, 
                 only_talk_graph: OnlyTalkGraph, 
                 shopping_list_graph: ShoppingListGraph):
        self.llm_chat = llm_chat
        self.only_talk_graph = only_talk_graph
        self.shopping_list_graph = shopping_list_graph
        self.classification_prompt = ChatPromptTemplate.from_template(self.load_prompt("main_graph.md"))
    
    #===============================================
    # Graph Nodes
    #===============================================
    def _classify_intent(self, data):
        chain = self.classification_prompt | self.llm_chat
        response = chain.invoke({"input": data["input"].message})
        cleaned = self._remove_thinking_tag(response.content)
        try:
            intents = eval(cleaned) if isinstance(cleaned, str) else []
            if isinstance(intents, str):
                intents = [intents]
        except:
            intents = ["only_talking"]
        return {"intent": intents, "input": data["input"]}  


    def _handle_final_response(self, data):
        outputs = [e for e in [
            data.get("output_lights"),
            data.get("output_shopping"),
            data.get("output_cams"),
            data.get("output_only_talking")
        ] if e is not None]

        if len(outputs) > 1:
            # Merging multiple cathegory responses into a friendly response
            responses = '\n\n'.join([f"{i+1}. {s}" for i, s in enumerate(outputs)])
            final_response_prompt = ChatPromptTemplate.from_template(self.load_prompt("main_graph_final_response.md"))
            final_reponse_chain = final_response_prompt | self.llm_chat
            llm_response = final_reponse_chain.invoke({"input": data["input"].message, "responses": responses})
            response = self._remove_thinking_tag(llm_response.content)
        else:
            # Unique response
            response = outputs[0]

        return {"output": response}
    
    def _handle_smart_home_lights(self, data):
        print(f"[main_graph.handle_smart_home_lights]: Triggered...")
        return {"output_lights": "Luz ajustada com sucesso."}

    def _handle_smart_home_security_cams(self, data):
        print(f"[main_graph.handle_smart_home_security_cams]: Triggered...")
        return {"output_cams": "Desculpe. Você não tem acesso para ver as câmeras."}

    def _handle_shopping_list(self, data):
        print(f"[main_graph.handle_shopping_list]: : Triggered...")
        result: str = self.shopping_list_graph.invoke(invoke_request=data['input'])
        return {"output_shopping": result}

    def _handle_only_talking(self, data):
        print(f"[main_graph.handle_only_talking]: Triggered...")
        result = self.only_talk_graph.invoke(invoke_request=data['input'])
        return {"output_only_talking": f"{self._remove_thinking_tag(result)}"}

    #===============================================
    # Private Methods
    #===============================================

    def _compile(self):
        workflow = StateGraph(MainGraphState)

        workflow.add_node("classify", RunnableLambda(self._classify_intent))
        workflow.add_node("smart_home_lights", RunnableLambda(self._handle_smart_home_lights))
        workflow.add_node("smart_home_security_cams", RunnableLambda(self._handle_smart_home_security_cams))
        workflow.add_node("shopping_list", RunnableLambda(self._handle_shopping_list))
        workflow.add_node("only_talking", RunnableLambda(self._handle_only_talking))

        workflow.add_node("final_response", RunnableLambda(self._handle_final_response))
        workflow.set_entry_point("classify")

        def intent_router(state):
            return state.get("intent", [])
        
        workflow.add_conditional_edges("classify", intent_router)

        for node in ["smart_home_lights", "smart_home_security_cams", "shopping_list", "only_talking"]:
            workflow.add_edge(node, "final_response")

        workflow.add_edge("final_response", END)

        return workflow.compile()

    #===============================================
    # Public Methods
    #===============================================
    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        app = self._compile()
        return app.invoke({"input": invoke_request})