import ast
import logging
import re
from typing import List, Optional, TypedDict
from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph, START, END
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from application.graphs.graph import Graph
from application.graphs.markers import SHOPPING_LIST_HEADER
from domain.commands import ShoppingListItemAdd
from domain.entities import (
    DisambiguationCandidate,
    GraphInvokeRequest,
    PendingDisambiguation,
    ShoppingListItem,
)
from domain.exceptions import ValidationError
from domain.services.disambiguation_service import DisambiguationService
from domain.services.shopping_list_service import ShoppingListService
from infra import async_runner


logger = logging.getLogger(__name__)


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
        disambiguation_service: Optional[DisambiguationService] = None,
        provider: str = "OLLAMA",
        strip_think_directive: bool = False,
    ):
        super().__init__(provider, strip_think_directive)
        self.llm_chat = llm_chat
        self.shopping_list_service = shopping_list_service
        self.disambiguation_service = disambiguation_service
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
            parsed = ast.literal_eval(extracted)
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
            # The classifier stores its raw fields in the state, so a value may
            # be an empty string or even a list (when gemma returns one). Keep
            # only non-empty strings so the join never sees a non-str item and
            # blank values do not pollute the reply with empty lines.
            if isinstance(e, str) and e.strip()
        ]

        if len(outputs) > 1:
            response = "\n\n".join(outputs)
        else:
            response = outputs[0] if outputs else ""

        return {"output": response}

    def _handle_add_item(self, data):
        payload: str = data.get("output_add_item")
        logger.debug("handle_add_item payload=%r", payload)

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
            logger.error("handle_add_item failed: %s", exception, exc_info=True)
            return {
                "output_add_item": "Tive um problema interno aqui, tente de novo daqui a pouco."
            }

    def _handle_delete_item(self, data):
        payload: str = data.get("output_delete_item")
        logger.debug("handle_delete_item payload=%r", payload)

        all_items = self.shopping_list_service.get_all()
        if not all_items:
            return {"output_delete_item": "A lista está vazia"}

        deleted, not_found, question = self._resolve_and_apply(
            data, payload, "delete", self.shopping_list_service.delete, all_items
        )

        parts = []
        if deleted:
            parts.append(f"Removido: {', '.join(deleted)}")
        if not_found:
            parts.append(f"Não encontrei na lista: {', '.join(not_found)}")
        if question:
            parts.append(question)

        return {
            "output_delete_item": " ".join(parts)
            if parts
            else "Não encontrei esse item na lista."
        }

    def _handle_edit_item(self, data):
        payload = data.get("output_edit_item")
        logger.debug("handle_edit_item payload=%r", payload)
        return {
            "output_edit_item": "Ainda não sei editar item da lista, mas já já aprendo."
        }

    def _handle_check_item(self, data):
        payload: str = data.get("output_check_item")
        logger.debug("handle_check_item payload=%r", payload)

        all_items = self.shopping_list_service.get_all()
        if not all_items:
            return {"output_check_item": "Nenhum item encontrado para marcar"}

        checked, not_found, question = self._resolve_and_apply(
            data, payload, "check", self.shopping_list_service.check, all_items
        )

        parts = []
        if checked:
            parts.append(f"Marcado como comprado: {', '.join(checked)}")
        if not_found:
            parts.append(f"Itens não encontrados na lista: {', '.join(not_found)}")
        if question:
            parts.append(question)

        return {
            "output_check_item": " ".join(parts)
            if parts
            else "Nenhum item encontrado para marcar"
        }

    def _handle_uncheck_item(self, data):
        payload: str = data.get("output_uncheck_item")
        logger.debug("handle_uncheck_item payload=%r", payload)

        all_items = self.shopping_list_service.get_all()
        if not all_items:
            return {"output_uncheck_item": "Nenhum item encontrado para desmarcar"}

        unchecked, not_found, question = self._resolve_and_apply(
            data, payload, "uncheck", self.shopping_list_service.uncheck, all_items
        )

        parts = []
        if unchecked:
            parts.append(f"Desmarcado: {', '.join(unchecked)}")
        if not_found:
            parts.append(f"Itens não encontrados na lista: {', '.join(not_found)}")
        if question:
            parts.append(question)

        return {
            "output_uncheck_item": " ".join(parts)
            if parts
            else "Nenhum item encontrado para desmarcar"
        }

    def _handle_list_items(self, data):
        logger.info("handle_list_items triggered")
        items: ShoppingListItem = self.shopping_list_service.get_all()

        if not items:
            return {"output_list_items": "A lista de compras está vazia"}

        return {"output_list_items": self._format_items(items)}

    def _handle_clear_items(self, data):
        logger.info("handle_clear_items triggered")
        self.shopping_list_service.clear()
        return {
            "output_clear_items": "Lista de compras limpa, todos os itens foram removidos"
        }

    def _handle_not_recognized(self, data):
        logger.info("handle_not_recognized triggered")
        return {
            "output_not_recognized": "Não entendi o que você quer fazer com a lista de compras."
        }

    # ===============================================
    # Private Methods
    # ===============================================

    def _resolve_and_apply(self, data, payload, operation, apply, all_items):
        """
        Resolve each term in the pipe-delimited payload against the loaded
        items via the domain resolver (handles typos and partial names) and
        apply ``operation`` on unambiguous matches. On the FIRST ambiguous term,
        record a pending disambiguation and build a question instead of acting.

        Returns (applied_names, not_found_names, question). ``question`` is None
        when nothing was ambiguous.
        """
        applied_names: List[str] = []
        not_found_names: List[str] = []
        question: Optional[str] = None

        terms = [e.split(",", 1)[0].strip() for e in payload.split("|")]
        for term in terms:
            if not term:
                continue
            candidates = self.shopping_list_service.find_items_by_name(term, all_items)
            if not candidates:
                not_found_names.append(term)
            elif len(candidates) == 1:
                apply(candidates[0].id)
                applied_names.append(candidates[0].name)
            elif question is None:
                question = self._store_disambiguation(
                    data, operation, term, candidates
                )

        return applied_names, not_found_names, question

    def _store_disambiguation(self, data, operation, query, candidates) -> str:
        """
        Persist a pending disambiguation for the user (when a disambiguation
        service is wired) and return the Portuguese question listing the
        candidate names.
        """
        names = ", ".join(candidate.name for candidate in candidates)
        question = f'Encontrei mais de um item para "{query}": {names}. Qual você quer?'

        if self.disambiguation_service is not None:
            pending = PendingDisambiguation(
                operation=operation,
                query=query,
                candidates=[
                    DisambiguationCandidate(id=candidate.id, name=candidate.name)
                    for candidate in candidates
                ],
            )
            user_id = data["input"].user.id
            async_runner.run(
                self.disambiguation_service.set_pending(user_id, pending)
            )

        return question

    def _format_items(self, items: List[ShoppingListItem]) -> str:
        lines = [SHOPPING_LIST_HEADER]
        for item in items:
            quantity = f" ({self._format_quantity(item.quantity)})" if item.quantity != 1 else ""
            status = " (comprado)" if item.checked else ""
            lines.append(f"- {item.name}{quantity}{status}")
        return "\n".join(lines)

    @staticmethod
    def _format_quantity(quantity: float) -> str:
        # Render whole numbers without the trailing ".0" (2.0 -> "2"), keep
        # genuine fractions intact (1.5 -> "1.5").
        if quantity == int(quantity):
            return str(int(quantity))
        return str(quantity)

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
                logger.warning("item ignored: %r", pair)
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
