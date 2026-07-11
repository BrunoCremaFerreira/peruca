import json
import logging
import re
from decimal import Decimal, InvalidOperation as _DecimalInvalidOperation
from typing import List, Optional, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph

from application.graphs.graph import Graph
from application.graphs.markers import CALCULATOR_RESULT_HEADER
from domain.entities import GraphInvokeRequest
from domain.exceptions import (
    CalculationTimeoutError,
    DivisionByZeroError,
    MathDomainError,
    NoClosedFormError,
    ValidationError,
)
from domain.services.calculator_service import evaluate_expression
from domain.services.symbolic_math_service import SymbolicMathService


logger = logging.getLogger(__name__)

_INTENTS = {"calculate", "calculate_symbolic", "not_supported", "not_recognized"}
_SYMBOLIC_OPERATIONS = {"integrate", "diff", "gradient", "limit", "simplify"}

_PRESENTATION_DECIMAL_PLACES = Decimal("1E-10")

_ASK_COMPLETE_EXPRESSION_MESSAGE = (
    "Para eu calcular, preciso da expressão completa — por exemplo: "
    "\"quanto é 10 mais 5?\"."
)
_DIVISION_BY_ZERO_MESSAGE = (
    "Não dá para dividir por zero. Pode revisar os valores e repetir o cálculo?"
)
_MATH_DOMAIN_MESSAGE = (
    "Essa operação não tem resultado definido — como raiz de número negativo "
    "ou logaritmo de zero. Pode revisar os valores?"
)
_INVALID_EXPRESSION_MESSAGE = (
    "Não consegui entender a expressão matemática. Pode repetir o cálculo de "
    "outra forma?"
)
_TIMEOUT_MESSAGE = (
    "Esse cálculo demorou demais e foi interrompido. Pode tentar uma expressão "
    "mais simples?"
)
_NO_CLOSED_FORM_MESSAGE = (
    "Não consegui resolver simbolicamente — essa expressão não tem uma forma "
    "fechada conhecida."
)
_NOT_SUPPORTED_MESSAGE = (
    "Ainda não sei resolver esse tipo de cálculo — como equações, integrais "
    "definidas, matrizes ou estatística."
)
_NOT_RECOGNIZED_MESSAGE = "Não entendi qual cálculo você quer fazer."
_SEQUENTIAL_ORDER_NOTE = " (calculado na ordem em que você disse)"


class CalculatorGraphState(TypedDict, total=False):
    input: GraphInvokeRequest
    intent: Optional[List[str]]
    expression: Optional[str]
    operation: Optional[str]
    variable: Optional[str]
    to: Optional[str]
    reason: Optional[str]
    output_calculate: Optional[str]
    output_symbolic: Optional[str]
    output_not_supported: Optional[str]
    output_not_recognized: Optional[str]
    output: Optional[str]


class CalculatorGraph(Graph):
    """
    Calculator graph: the LLM only transcribes the dictated expression
    (classify — the single LLM call); the action nodes are 100% deterministic.
    Numeric expressions are folded left-to-right by calculator_service
    (Decimal); symbolic requests (integrate/diff/gradient/limit/simplify) go
    through SymbolicMathService behind the CAS port. The LLM never does math.
    """

    def __init__(
        self,
        llm_chat: BaseChatModel,
        symbolic_math_service: SymbolicMathService,
        provider: str = "OLLAMA",
        strip_think_directive: bool = False,
    ):
        super().__init__(provider, strip_think_directive)
        self.llm_chat = llm_chat
        self.symbolic_math_service = symbolic_math_service
        self.classification_prompt = ChatPromptTemplate.from_template(
            self.load_prompt("calculator_graph.md")
        )

    # ===============================================
    # Graph Nodes
    # ===============================================
    def _classify_intent(self, data):
        request: GraphInvokeRequest = data["input"]
        chain = self.classification_prompt | self.llm_chat
        response = chain.invoke({"input": request.message})

        extracted = self._extract_structured_output(response.content)
        parsed = {}
        if extracted:
            try:
                loaded = json.loads(extracted)
                if isinstance(loaded, dict):
                    parsed = loaded
            except (json.JSONDecodeError, ValueError):
                parsed = {}

        intents = parsed.get("intents") or ["not_recognized"]
        if isinstance(intents, str):
            intents = [intents]
        intents = [intent for intent in intents if intent in _INTENTS]
        if not intents:
            intents = ["not_recognized"]

        operation = (parsed.get("operation") or "").strip()
        if "calculate_symbolic" in intents and operation not in _SYMBOLIC_OPERATIONS:
            # The LLM invented an operation outside the closed set: degrade to
            # not_recognized instead of guessing.
            intents = ["not_recognized"]

        return {
            "intent": intents,
            "input": request,
            "expression": (parsed.get("expression") or "").strip(),
            "operation": operation,
            "variable": (parsed.get("variable") or "").strip(),
            "to": (parsed.get("to") or "").strip(),
            "reason": (parsed.get("reason") or "").strip(),
        }

    def _handle_calculate(self, data):
        expression = (data.get("expression") or "").strip()
        if not expression:
            return {"output_calculate": _ASK_COMPLETE_EXPRESSION_MESSAGE}
        try:
            result = evaluate_expression(expression)
        except DivisionByZeroError:
            return {"output_calculate": _DIVISION_BY_ZERO_MESSAGE}
        except MathDomainError:
            return {"output_calculate": _MATH_DOMAIN_MESSAGE}
        except ValidationError:
            return {"output_calculate": _INVALID_EXPRESSION_MESSAGE}

        rendered = (
            f"{CALCULATOR_RESULT_HEADER} "
            f"{self._render_numeric_expression(expression)} = "
            f"{self._format_decimal_pt_br(result)}"
        )
        if len(re.findall(r"\*\*|[+\-*/]", expression)) >= 2:
            rendered += _SEQUENTIAL_ORDER_NOTE
        return {"output_calculate": rendered}

    def _handle_calculate_symbolic(self, data):
        operation = (data.get("operation") or "").strip()
        expression = (data.get("expression") or "").strip()
        variable = (data.get("variable") or "").strip()
        to = (data.get("to") or "").strip()
        try:
            result = self.symbolic_math_service.evaluate(
                operation=operation,
                expression=expression,
                variable=variable,
                to=to,
            )
        except CalculationTimeoutError:
            return {"output_symbolic": _TIMEOUT_MESSAGE}
        except NoClosedFormError:
            return {"output_symbolic": _NO_CLOSED_FORM_MESSAGE}
        except MathDomainError:
            return {"output_symbolic": _MATH_DOMAIN_MESSAGE}
        except ValidationError:
            return {"output_symbolic": _INVALID_EXPRESSION_MESSAGE}

        rendered = self._render_symbolic(operation, expression, variable, to, result)
        return {"output_symbolic": f"{CALCULATOR_RESULT_HEADER} {rendered}"}

    def _handle_not_supported(self, data):
        return {"output_not_supported": _NOT_SUPPORTED_MESSAGE}

    def _handle_not_recognized(self, data):
        return {"output_not_recognized": _NOT_RECOGNIZED_MESSAGE}

    def _handle_final_response(self, data):
        outputs = [
            e
            for e in [
                data.get("output_calculate"),
                data.get("output_symbolic"),
                data.get("output_not_supported"),
                data.get("output_not_recognized"),
            ]
            if isinstance(e, str) and e.strip()
        ]
        response = (
            "\n\n".join(outputs) if len(outputs) > 1 else (outputs[0] if outputs else "")
        )
        return {"output": response}

    # ===============================================
    # Deterministic presentation helpers
    # ===============================================
    @staticmethod
    def _format_decimal_pt_br(value: Decimal) -> str:
        quantized = value
        exponent = value.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -10:
            try:
                quantized = value.quantize(_PRESENTATION_DECIMAL_PLACES)
            except _DecimalInvalidOperation:
                quantized = value
        normalized = quantized.normalize() if quantized != 0 else Decimal(0)
        return format(normalized, "f").replace(".", ",")

    @staticmethod
    def _render_numeric_expression(expression: str) -> str:
        display = expression.replace("**", "^").replace("*", "×").replace("/", "÷")
        return re.sub(r"(?<=\d)\.(?=\d)", ",", display)

    def _render_symbolic(
        self, operation: str, expression: str, variable: str, to: str, result
    ) -> str:
        expression_display = self._render_symbolic_expression(expression)
        variable_display = variable or "x"
        if operation == "gradient":
            parts = result if isinstance(result, list) else [result]
            rendered = ", ".join(
                self._render_symbolic_expression(str(part)) for part in parts
            )
            return f"∇({expression_display}) = ({rendered})"
        result_display = self._render_symbolic_expression(str(result))
        if operation == "integrate":
            return f"∫ {expression_display} d{variable_display} = {result_display}"
        if operation == "diff":
            return f"d/d{variable_display} ({expression_display}) = {result_display}"
        if operation == "limit":
            target_display = to.replace("oo", "∞") if to else "?"
            return (
                f"lim {variable_display} → {target_display} de "
                f"{expression_display} = {result_display}"
            )
        return f"{expression_display} = {result_display}"

    @staticmethod
    def _render_symbolic_expression(expression: str) -> str:
        return expression.replace("**", "^").replace("*", "·")

    # ===============================================
    # Private Methods
    # ===============================================
    def _compile(self):
        workflow = StateGraph(CalculatorGraphState)
        workflow.add_node("classify", RunnableLambda(self._classify_intent))
        workflow.add_node("calculate", RunnableLambda(self._handle_calculate))
        workflow.add_node(
            "calculate_symbolic", RunnableLambda(self._handle_calculate_symbolic)
        )
        workflow.add_node("not_supported", RunnableLambda(self._handle_not_supported))
        workflow.add_node(
            "not_recognized", RunnableLambda(self._handle_not_recognized)
        )
        workflow.add_node("final_response", RunnableLambda(self._handle_final_response))
        workflow.add_edge(START, "classify")

        def intent_router(state):
            return state.get("intent", [])

        workflow.add_conditional_edges("classify", intent_router)

        for node in [
            "calculate",
            "calculate_symbolic",
            "not_supported",
            "not_recognized",
        ]:
            workflow.add_edge(node, "final_response")
        workflow.add_edge("final_response", END)
        return workflow.compile()

    # ===============================================
    # Public Methods
    # ===============================================
    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        if self._compiled_graph is None:
            self._compiled_graph = self._compile()
        return self._compiled_graph.invoke({"input": invoke_request})
