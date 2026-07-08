import re
from typing import Callable, Optional

from application.graphs.graph import Graph
from domain.entities import GraphInvokeRequest
from domain.interfaces.data_repository import ImageStore
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from datetime import datetime


# Sentinel that separates the user-facing answer from the factual image
# description meant only for the conversation memory (the user never sees it).
IMAGE_DESC_MARKER = "<<<DESC_IMAGEM>>>"

# Generic fallback description stored when the model omits the marker.
_IMAGE_DESC_FALLBACK = "[imagem enviada]"

# Sentinel the model may emit on the first (cheap) pass to request re-vision of
# a previously stored image: "<<<REVER_IMAGEM: #3>>>" / ": mais_recente>>>".
_REVISION_RE = re.compile(
    r"<<<REVER_IMAGEM(?::\s*(?P<target>[^>]*))?>>>", re.IGNORECASE
)

# Injected into the system prompt ONLY on turns that carry an image, so the
# text-only path never sees (nor accidentally emits) the marker directive.
_IMAGE_DESC_DIRECTIVE = (
    "## Imagem enviada neste turno\n"
    "O usuário enviou uma ou mais imagens junto da mensagem. Observe e comente "
    "a foto com naturalidade, em português e no seu personagem, sem inventar o "
    "que não está visível.\n"
    "Ao final da sua resposta, emita **uma linha** contendo exatamente "
    f"{IMAGE_DESC_MARKER} e, logo abaixo, uma descrição factual e neutra da "
    "imagem (2 a 4 frases: o que é, quem/quantos, cores, texto legível, "
    "ambiente, ações). Essa descrição é uma anotação para a sua própria "
    "memória — o usuário não a vê — então escreva-a sem persona e sem floreio."
)

# Injected only when the conversation already has a stored image (a follow-up
# context). Calibrated conservatively: re-vision is the exception, not the rule.
_IMAGE_REVISION_DIRECTIVE = (
    "## Rever uma foto anterior\n"
    "As linhas do histórico marcadas como [Imagem #N enviada pelo usuário: ...] "
    "referem-se a fotos que o usuário já enviou; a descrição ali quase sempre "
    "basta para responder.\n"
    "SOMENTE quando a pergunta atual exigir um detalhe visual concreto que a "
    "descrição NÃO cobre (um número, um texto pequeno ou etiqueta, uma cor "
    "exata, uma contagem fina), acrescente ao final da resposta **uma linha** "
    "exatamente com <<<REVER_IMAGEM: #N>>> (usando o #N da foto) — ou "
    "<<<REVER_IMAGEM: mais_recente>>> para a última foto — nomeando o atributo "
    "pedido. Se a descrição já basta, responda direto e NÃO emita essa linha."
)


class OnlyTalkGraph(Graph):
    """
    Only talk category graph
    """

    def __init__(
        self,
        llm_chat: BaseChatModel,
        get_session_history: Callable[[str], BaseChatMessageHistory],
        provider: str = "OLLAMA",
        image_store: Optional[ImageStore] = None,
        history_max_messages: Optional[int] = None,
    ):
        super().__init__(provider)
        self.llm_chat = llm_chat
        self._get_session_history = get_session_history
        self._image_store = image_store
        # Cap the number of history messages injected into the prompt. Injecting
        # an unbounded history lets a long conversation fill num_ctx, leaving no
        # room for generation — the model then stops mid-sentence
        # (done_reason=length). None keeps the full history (legacy behavior).
        self._history_max_messages = history_max_messages

    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        user = invoke_request.user
        images = invoke_request.images or []
        has_images = bool(images)

        history_messages = self._get_session_history(user.id).messages
        if (
            self._history_max_messages
            and len(history_messages) > self._history_max_messages
        ):
            history_messages = history_messages[-self._history_max_messages:]
        has_prior_image = self._image_store is not None and any(
            "[Imagem #" in str(getattr(m, "content", "")) for m in history_messages
        )

        base_system = self._format_system(invoke_request)

        first_system = base_system
        if has_images:
            first_system = f"{first_system}\n\n{_IMAGE_DESC_DIRECTIVE}"
        if has_prior_image:
            first_system = f"{first_system}\n\n{_IMAGE_REVISION_DIRECTIVE}"

        first_content = self._build_human_content(invoke_request.message, images)
        first_output = self._run_pass(first_system, history_messages, first_content)

        # Re-vision gate: only when a store is available and the model asked for
        # it. The id is always resolved within THIS user's scope.
        revision_target = self._parse_revision_target(first_output)
        if revision_target is not None and self._image_store is not None:
            image_id = self._resolve_image_id(user.id, revision_target)
            data_uri = (
                self._image_store.get(user.id, image_id) if image_id else None
            )
            if data_uri is not None:
                second_system = f"{base_system}\n\n{_IMAGE_DESC_DIRECTIVE}"
                second_content = self._build_human_content(
                    invoke_request.message, [data_uri]
                )
                second_output = self._run_pass(
                    second_system, history_messages, second_content
                )
                output, description = self._split_output_and_description(
                    second_output
                )
                return {
                    "output": output,
                    "image_description": description,
                    "revised_image_index": image_id,
                }

        if has_images:
            output, description = self._split_output_and_description(first_output)
            return {
                "output": output,
                "image_description": description,
                "revised_image_index": None,
            }

        return {
            "output": self._strip_revision_sentinel(first_output),
            "image_description": None,
            "revised_image_index": None,
        }

    # ===============================================
    # Private Methods
    # ===============================================

    def _format_system(self, invoke_request: GraphInvokeRequest) -> str:
        user = invoke_request.user
        if invoke_request.memories:
            user_memories = "\n".join(
                f"- {memory}" for memory in invoke_request.memories
            )
        else:
            user_memories = (
                "(você ainda não tem memórias registradas sobre esta pessoa)"
            )
        siblings = (invoke_request.context_hints or {}).get("user_pets_persona")
        if not siblings or not str(siblings).strip():
            siblings = "(nenhum pet cadastrado no momento)"
        return self.load_prompt("only_talk_graph.md").format(
            user_name=user.name,
            user_summary=user.summary,
            user_memories=user_memories,
            siblings=siblings,
            current_datetime=datetime.now().astimezone().strftime("%d/%m/%Y %H:%M"),
        )

    def _run_pass(self, system_message, history_messages, human_content) -> str:
        chat_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_message),
                MessagesPlaceholder(variable_name="history"),
                MessagesPlaceholder(variable_name="input"),
            ]
        )
        chain = chat_prompt | self.llm_chat
        response = chain.invoke(
            {
                "input": [HumanMessage(content=human_content)],
                "history": history_messages,
            }
        )
        return response.content

    def _parse_revision_target(self, content: str):
        """
        Return the re-vision target parsed from the sentinel, or None when no
        sentinel is present:
          - ("id", "<digits>")  for an explicit "#N"
          - ("latest", None)    for "mais_recente" (or a bare sentinel)
        """
        match = _REVISION_RE.search(content or "")
        if not match:
            return None
        target = (match.group("target") or "").strip()
        digits = re.search(r"\d+", target)
        if digits:
            return ("id", digits.group(0))
        return ("latest", None)

    def _resolve_image_id(self, user_id: str, revision_target) -> Optional[str]:
        kind, ident = revision_target
        if kind == "id":
            return ident
        return self._image_store.latest_id(user_id)

    def _split_output_and_description(self, content: str):
        """
        Split the model output on IMAGE_DESC_MARKER into (user_output,
        image_description). Falls back to the whole content as output and a
        generic description when the marker is absent. Any re-vision sentinel is
        stripped from the user-facing output.
        """
        cleaned = self._remove_thinking_tag(content or "")
        if IMAGE_DESC_MARKER in cleaned:
            before, after = cleaned.split(IMAGE_DESC_MARKER, 1)
            output = self._strip_revision_sentinel(before)
            description = after.strip() or _IMAGE_DESC_FALLBACK
            return output, description
        return self._strip_revision_sentinel(cleaned), _IMAGE_DESC_FALLBACK

    def _strip_revision_sentinel(self, text: str) -> str:
        return _REVISION_RE.sub("", self._remove_thinking_tag(text or "")).strip()
