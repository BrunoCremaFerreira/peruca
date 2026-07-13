import json
import logging
from typing import List, Optional, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph

from application.appservices.prompt_sanitizer import sanitize_for_prompt
from application.graphs.graph import Graph
from domain.entities import GraphInvokeRequest
from domain.exceptions import ValidationError
from domain.services.timezone_resolver import resolve_timezone


logger = logging.getLogger(__name__)

_INTENTS = {"set_timezone", "get_timezone", "not_recognized"}

_MAX_LOCATION_CHARS = 60

_UNRESOLVED_MESSAGE = (
    "Não reconheci esse fuso. Me diga uma cidade grande de referência — por "
    "exemplo: São Paulo, Lisboa, Nova York ou Londres."
)
_NOT_RECOGNIZED_MESSAGE = (
    "Não entendi qual configuração você quer alterar ou consultar."
)
_SET_FAILED_MESSAGE = (
    "Não consegui alterar o fuso horário. Pode me dizer de novo qual cidade "
    "devo usar como referência?"
)


class UserSettingsGraphState(TypedDict, total=False):
    input: GraphInvokeRequest
    intent: Optional[List[str]]
    location: Optional[str]
    timezone_iana: Optional[str]
    resolved_timezone: Optional[str]
    output_set: Optional[str]
    output_get: Optional[str]
    output_not_recognized: Optional[str]
    output: Optional[str]


class UserSettingsGraph(Graph):
    """
    User settings graph: reads and changes the assistant's per-user preferences —
    today only the timezone used in the answers.

    Classify is the ONLY LLM call: the model transcribes the spoken location and,
    when it is sure, suggests an IANA identifier. Python — never the LLM — is the
    authority: ``resolve_timezone`` validates the suggestion against the tz
    database and falls back to the curated pt-BR dictionary, so a hallucinated
    identifier is discarded instead of persisted. The action nodes are 100%
    deterministic.
    """

    def __init__(
        self,
        llm_chat: BaseChatModel,
        user_settings_service,
        provider: str = "OLLAMA",
        strip_think_directive: bool = False,
    ):
        super().__init__(provider, strip_think_directive)
        self.llm_chat = llm_chat
        self.user_settings_service = user_settings_service
        self.classification_prompt = ChatPromptTemplate.from_template(
            self.load_prompt("user_settings_graph.md")
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

        # The location is free text transcribed by the LLM and is echoed back in an
        # answer that is persisted in the `assistant` role and replayed raw by
        # OnlyTalkGraph — without collapsing whitespace, it can forge a history turn.
        location = sanitize_for_prompt(parsed.get("location"), _MAX_LOCATION_CHARS)
        timezone_iana = (parsed.get("timezone_iana") or "").strip()

        return {
            "intent": intents,
            "input": request,
            "location": location,
            "timezone_iana": timezone_iana,
            "resolved_timezone": resolve_timezone(
                location=location, timezone_iana=timezone_iana
            ),
        }

    def _handle_set_timezone(self, data):
        user = data["input"].user
        resolved = data.get("resolved_timezone")
        if not resolved:
            return {"output_set": _UNRESOLVED_MESSAGE}

        try:
            self.user_settings_service.set_timezone(user.id, resolved)
        except ValidationError as error:
            logger.warning("set_timezone rejected %r: %s", resolved, error.errors)
            return {"output_set": _SET_FAILED_MESSAGE}
        except Exception as error:  # noqa: BLE001
            logger.error("set_timezone failed: %s", error, exc_info=True)
            return {"output_set": _SET_FAILED_MESSAGE}

        location = data.get("location") or ""
        place = f" ({location})" if location else ""
        return {"output_set": f"Pronto! Agora uso o fuso de {resolved}{place}."}

    def _handle_get_timezone(self, data):
        user = data["input"].user
        current = self.user_settings_service.get_timezone(user.id)
        return {"output_get": f"Estou usando o fuso {current}."}

    def _handle_not_recognized(self, data):
        return {"output_not_recognized": _NOT_RECOGNIZED_MESSAGE}

    def _handle_final_response(self, data):
        outputs = [
            e
            for e in [
                data.get("output_set"),
                data.get("output_get"),
                data.get("output_not_recognized"),
            ]
            if isinstance(e, str) and e.strip()
        ]
        response = (
            "\n\n".join(outputs) if len(outputs) > 1 else (outputs[0] if outputs else "")
        )
        return {"output": response}

    # ===============================================
    # Private Methods
    # ===============================================
    def _compile(self):
        workflow = StateGraph(UserSettingsGraphState)
        workflow.add_node("classify", RunnableLambda(self._classify_intent))
        workflow.add_node("set_timezone", RunnableLambda(self._handle_set_timezone))
        workflow.add_node("get_timezone", RunnableLambda(self._handle_get_timezone))
        workflow.add_node(
            "not_recognized", RunnableLambda(self._handle_not_recognized)
        )
        workflow.add_node("final_response", RunnableLambda(self._handle_final_response))
        workflow.add_edge(START, "classify")

        def intent_router(state):
            return state.get("intent", [])

        workflow.add_conditional_edges("classify", intent_router)

        for node in ["set_timezone", "get_timezone", "not_recognized"]:
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
