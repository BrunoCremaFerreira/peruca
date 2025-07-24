from typing import Optional, TypedDict
from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph, END
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from domain.entities import GraphInvokeRequest
from domain.graphs.graph import Graph

class ShoppingListGraphState(TypedDict):
        input: str
        intent: Optional[list[str]]
        output_add_item: Optional[str]
        output_edit_item: Optional[str]
        output_delete_item: Optional[str]
        output_check_item: Optional[str]
        output_uncheck_item: Optional[str]
        output_list_items: Optional[str]
        output_clear_items: Optional[str]
        output_not_recognized: Optional[str]
        output: Optional[str]

class ShoppingListGraph(Graph):
    """
    Shopping List category graph
    """

    def __init__(self, llm_chat: BaseChatModel):
        self.llm_chat = llm_chat
        self.classification_prompt = ChatPromptTemplate.from_template(self.load_prompt("shopping_list_graph.md"))

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
            intents = ["not_recognized"]
        return {"intent": intents, "input": data["input"]}  


    def _handle_final_response(self, data):
        outputs = [e for e in [
            data.get("output_add_item"),
            data.get("output_edit_item"),
            data.get("output_delete_item"),
            data.get("output_check_item"),
            data.get("output_uncheck_item"),
            data.get("output_list_items"),
            data.get("output_clear_items"),
            data.get("output_not_recognized")
        ] if e is not None]

        if len(outputs) > 1:
            # Merging multiple cathegory responses into a friendly response
            responses = '\n\n'.join([f"{i+1}. {s}" for i, s in enumerate(outputs)])
            final_response_prompt = ChatPromptTemplate.from_template(self.load_prompt("shopping_list_final_response.md"))
            final_reponse_chain = final_response_prompt | self.llm_chat
            llm_response = final_reponse_chain.invoke({"input": data["input"].message, "responses": responses})
            response = self._remove_thinking_tag(llm_response.content)
        else:
            # Unique response
            response = outputs[0]

        return {"output": response}
    
    def _handle_add_item(self, data):
        print(f"[shopping_list_graph.handle_add_item]: Triggered...")
        return {"output_add_item": "Add Item Triggered"}

    def _handle_edit_item(self, data):
        print(f"[shopping_list_graph.handle_edit_item]: : Triggered...")
        return {"output_edit_item": "Edit Item Triggered"}
    
    def _handle_delete_item(self, data):
        print(f"[shopping_list_graph.handle_delete_item]: Triggered...")
        return {"output_delete_item": "Delete Item Triggered"}

    def _handle_check_item(self, data):
        print(f"[shopping_list_graph.handle_check_item]: Triggered...")
        return {"output_check_item": "Check Item Triggered"}
    
    def _handle_uncheck_item(self, data):
        print(f"[shopping_list_graph.handle_uncheck_item]: Triggered...")
        return {"output_ucheck_item": "Uncheck Item Triggered"}
    
    def _handle_list_items(self, data):
        print(f"[shopping_list_graph.handle_list_items]: Triggered...")
        return {"output_list_items": "List Items Triggered"}
    
    def _handle_clear_items(self, data):
        print(f"[shopping_list_graph.handle_clear_items]: Triggered...")
        return {"output_clear_items": "Clear Items Triggered"}
    
    def _handle_not_recognized(self, data):
        print(f"[shopping_list_graph.handle_not_recognized]: Triggered...")
        return {"output_not_recognized": "Not Recognized Triggered"}

    #===============================================
    # Private Methods
    #===============================================

    def _compile(self):
        workflow = StateGraph(ShoppingListGraphState)

        workflow.add_node("classify", RunnableLambda(self._classify_intent))
        workflow.add_node("add_item", RunnableLambda(self._handle_add_item))
        workflow.add_node("edit_item", RunnableLambda(self._handle_edit_item))
        workflow.add_node("delete_item", RunnableLambda(self._handle_delete_item))
        workflow.add_node("check_item", RunnableLambda(self._handle_check_item))
        workflow.add_node("uncheck_item", RunnableLambda(self._handle_uncheck_item))
        workflow.add_node("list_items", RunnableLambda(self._handle_list_items))
        workflow.add_node("clear_items", RunnableLambda(self._handle_clear_items))
        workflow.add_node("not_recognized", RunnableLambda(self._handle_not_recognized))
        workflow.add_node("final_response", RunnableLambda(self._handle_final_response))
        workflow.set_entry_point("classify")

        def intent_router(state):
            return state.get("intent", [])
        
        workflow.add_conditional_edges("classify", intent_router)

        nodes = ["add_item", 
                 "edit_item", 
                 "delete_item", 
                 "check_item", 
                 "uncheck_item", 
                 "list_items", 
                 "clear_items", 
                 "not_recognized"]

        for node in nodes:
            workflow.add_edge(node, "final_response")

        workflow.add_edge("final_response", END)

        return workflow.compile()

    #===============================================
    # Public Methods
    #===============================================
    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        app = self._compile()
        return app.invoke({"input": invoke_request})