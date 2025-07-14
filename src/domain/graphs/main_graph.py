from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph, END
from langchain_core.prompts import ChatPromptTemplate
from typing import TypedDict, Optional

class MainGraphState(TypedDict):
        input: str
        intent: Optional[list[str]]
        output_lights: Optional[str]
        output_shopping: Optional[str]
        output_cams: Optional[str]
        output_only: Optional[str]

class MainGraph:

    def __init__(self, chat_llm):
        self.chat_llm = chat_llm
        self.classification_prompt = ChatPromptTemplate.from_template(
        """/no_think
Você se chama Peruca. Você é um assistente virtual de uma casa automatizada. 
Classifique a entrada do usuário nas seguintes categorias de intenções. Retorne uma lista, se mais de uma categoria estiver presente:

- smart_home_lights
- smart_home_security_cams
- shopping_list
- only_talking

Entrada: {input}

Responda apenas com uma lista Python. Ex: ["shopping_list", "smart_home_lights"]
"""
)
    
    #===============================================
    # Graph Nodes
    #===============================================
    def _classify_intent(self, data):
        chain = self.classification_prompt | self.chat_llm
        response = chain.invoke({"input": data["input"]})
        cleaned = response.content.replace("<think>\n\n</think>\n\n", "").strip()
        try:
            intents = eval(cleaned) if isinstance(cleaned, str) else []
            if isinstance(intents, str):
                intents = [intents]
        except:
            intents = ["only_talking"]
        return {"intent": intents, "input": data["input"]}  


    def _handle_final_response(self, data):
        outputs = [
            data.get("output_lights"),
            data.get("output_shopping"),
            data.get("output_cams"),
            data.get("output_only")
        ]
        resposta_final = "\n".join(o for o in outputs if o)
        
        return {**data, "output": resposta_final}
    
    def _handle_smart_home_lights(self, data):
        print(f"[handle_smart_home_lights]: Triggered...")
        return {"output_lights": "Luz ajustada com sucesso."}

    def _handle_smart_home_security_cams(self, data):
        print(f"[handle_smart_home_security_cams]: Triggered...")
        return {"output_cams": "Desculpe. Você não tem acesso para ver as câmeras."}

    def _handle_shopping_list(self, data):
        print(f"[handle_shopping_list]: : Triggered...")
        return {"output_shopping": "Item adicionado à lista de compras."}

    def _handle_only_talking(self, data):
        print(f"[handle_only_talking]: Triggered...")
        response = self.chat_llm.invoke(f"/no_think Usuário: {data['input']}\nPeruca:")
        return {"output_only": response.content.replace("<think>\n\n</think>\n\n", "").strip()}

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

    def invoke(self, user_message):
        app = self._compile()
        return app.invoke({"input": user_message})