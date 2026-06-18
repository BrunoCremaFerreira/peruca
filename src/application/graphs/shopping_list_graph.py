import re
from typing import List, Optional, TypedDict
from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph, START, END
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from application.graphs.graph import Graph
from domain.commands import ShoppingListItemAdd
from domain.entities import GraphInvokeRequest, ShoppingListItem
from domain.exceptions import ValidationError
from domain.services.shopping_list_service import ShoppingListService


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

    def __init__(
        self,
        llm_chat: BaseChatModel,
        shopping_list_service: ShoppingListService,
        provider: str = "OLLAMA",
        strip_think_directive: bool = False,
    ):
        super().__init__(provider, strip_think_directive)
        self.llm_chat = llm_chat
        self.shopping_list_service = shopping_list_service
        self.classification_prompt = ChatPromptTemplate.from_template(
            self.load_prompt("shopping_list_graph.md")
        )

    # ===============================================
    # Graph Nodes
    # ===============================================
    def _classify_intent(self, data):
        chain = self.classification_prompt | self.llm_chat
        response = chain.invoke({"input": data["input"].message})
        extracted = self._extract_structured_output(response.content)
        if extracted is None:
            return {"intent": ["not_recognized"], "input": data["input"],
                    "output_add_item": None, "output_edit_item": None,
                    "output_delete_item": None, "output_check_item": None,
                    "output_uncheck_item": None}
        try:
            parsed = eval(extracted)
            intents = parsed.get("intents", ["not_recognized"])
        except Exception:
            parsed = {}
            intents = ["not_recognized"]

        return {
            "intent": intents,
            "input": data["input"],
            "output_add_item": parsed.get("add_item"),
            "output_edit_item": parsed.get("edit_item"),
            "output_delete_item": parsed.get("delete_item"),
            "output_check_item": parsed.get("check_item"),
            "output_uncheck_item": parsed.get("uncheck_item"),
        }

    def _handle_final_response(self, data):
        outputs = [
            e
            for e in [
                data.get("output_add_item"),
                data.get("output_edit_item"),
                data.get("output_delete_item"),
                data.get("output_check_item"),
                data.get("output_uncheck_item"),
                data.get("output_list_items"),
                data.get("output_clear_items"),
                data.get("output_not_recognized"),
            ]
            if e is not None
        ]

        if len(outputs) > 1:
            response = "\n\n".join([f"{i + 1}. {s}" for i, s in enumerate(outputs)])
        else:
            response = outputs[0]

        return {"output": response}

    def _handle_add_item(self, data):
        payload: str = data.get("output_add_item")
        print(f"[shopping_list_graph.handle_add_item]: {payload}")

        try:
            items_to_add = self._parse_shopping_list_add(payload)

            for item in items_to_add:
                self.shopping_list_service.add(item)

            return {
                "output_add_item": f"Adicionado: {', '.join(item.name for item in items_to_add)}"
            }
        except ValidationError as validation_error:
            return {"output_add_item": validation_error.errors}
        except Exception as exception:
            print(f"ERROR: {exception}")
            return {"output_add_item": "An internal error was ocurred"}

    def _handle_delete_item(self, data):
        payload: str = data.get("output_delete_item")
        print(f"[shopping_list_graph.handle_delete_item]: {payload}")

        all_items = self.shopping_list_service.get_all()
        if not all_items:
            return {"output_delete_item": "A lista esta vazia"}

        items_to_delete = [e.split(",", 1)[0].strip() for e in payload.split("|")]
        for item_name in items_to_delete:
            item = next(
                (e for e in all_items if e.name.lower() == item_name.lower()), None
            )
            if item:
                self.shopping_list_service.delete(item.id)

        return {"output_delete_item": f"Removido: {payload}"}

    def _handle_edit_item(self, data):
        payload = data.get("output_edit_item")
        print(f"[shopping_list_graph.handle_edit_item]: {payload}")
        return {"output_edit_item": f"Items Edited: {payload}"}

    def _handle_check_item(self, data):
        payload: str = data.get("output_check_item")
        print(f"[shopping_list_graph.handle_check_item]: {payload}")

        all_items = self.shopping_list_service.get_all()
        if not all_items:
            return {"output_check_item": "Nenhum item encontrado para marcar"}

        names_to_check = [name.strip() for name in payload.split("|")]
        checked_names = []
        not_found_names = []

        for name in names_to_check:
            item = next((e for e in all_items if e.name.lower() == name.lower()), None)
            if item:
                self.shopping_list_service.check(item.id)
                checked_names.append(item.name)
            else:
                not_found_names.append(name)

        parts = []
        if checked_names:
            parts.append(f"Marcado como comprado: {', '.join(checked_names)}")
        if not_found_names:
            parts.append(
                f"Itens não encontrados na lista: {', '.join(not_found_names)}"
            )

        return {
            "output_check_item": "; ".join(parts)
            if parts
            else "Nenhum item encontrado para marcar"
        }

    def _handle_uncheck_item(self, data):
        payload: str = data.get("output_uncheck_item")
        print(f"[shopping_list_graph.handle_uncheck_item]: {payload}")

        all_items = self.shopping_list_service.get_all()
        if not all_items:
            return {"output_uncheck_item": "Nenhum item encontrado para desmarcar"}

        names_to_uncheck = [name.strip() for name in payload.split("|")]
        unchecked_names = []
        not_found_names = []

        for name in names_to_uncheck:
            item = next((e for e in all_items if e.name.lower() == name.lower()), None)
            if item:
                self.shopping_list_service.uncheck(item.id)
                unchecked_names.append(item.name)
            else:
                not_found_names.append(name)

        parts = []
        if unchecked_names:
            parts.append(f"Desmarcado: {', '.join(unchecked_names)}")
        if not_found_names:
            parts.append(
                f"Itens não encontrados na lista: {', '.join(not_found_names)}"
            )

        return {
            "output_uncheck_item": "; ".join(parts)
            if parts
            else "Nenhum item encontrado para desmarcar"
        }

    def _handle_list_items(self, data):
        print(f"[shopping_list_graph.handle_list_items]: Triggered...")
        items: ShoppingListItem = self.shopping_list_service.get_all()

        if not items:
            return {"output_list_items": "A lista de compras está vazia"}

        return {"output_list_items": self._format_items(items)}

    def _handle_clear_items(self, data):
        print(f"[shopping_list_graph.handle_clear_items]: Triggered...")
        self.shopping_list_service.clear()
        return {
            "output_clear_items": "Lista de compras limpa, todos os itens foram removidos"
        }

    def _handle_not_recognized(self, data):
        print(f"[shopping_list_graph.handle_not_recognized]: Triggered...")
        return {"output_not_recognized": "Not Recognized Triggered"}

    # ===============================================
    # Private Methods
    # ===============================================

    def _format_items(self, items: List[ShoppingListItem]) -> str:
        lines = []
        for index, item in enumerate(items, start=1):
            status = " (comprado)" if item.checked else ""
            lines.append(f"{index}. {item.name} ({item.quantity}){status}")
        return "\n".join(lines)

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
        workflow.add_edge(START, "classify")

        def intent_router(state):
            return state.get("intent", [])

        workflow.add_conditional_edges("classify", intent_router)

        nodes = [
            "add_item",
            "edit_item",
            "delete_item",
            "check_item",
            "uncheck_item",
            "list_items",
            "clear_items",
            "not_recognized",
        ]

        for node in nodes:
            workflow.add_edge(node, "final_response")

        workflow.add_edge("final_response", END)

        return workflow.compile()

    # ===============================================
    # Items Parse
    # ===============================================
    def _parse_shopping_list_add(self, input_str: str) -> List[ShoppingListItemAdd]:
        items = []
        if not input_str.strip():
            return items

        for pair in input_str.split("|"):
            if not pair.strip():
                continue
            name, _, quantity_raw = pair.partition(",")
            name = name.strip()
            if not name:
                print(f"Warning: Item ignored: '{pair}'")
                continue
            match = re.search(r"\d+(?:[.,]\d+)?", quantity_raw)
            quantity = float(match.group().replace(",", ".")) if match else 1.0
            items.append(ShoppingListItemAdd(name=name, quantity=quantity))
        return items

    # ===============================================
    # Public Methods
    # ===============================================
    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        if self._compiled_graph is None:
            self._compiled_graph = self._compile()
        app = self._compiled_graph
        return app.invoke({"input": invoke_request})
