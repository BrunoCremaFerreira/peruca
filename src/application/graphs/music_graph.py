from infra import async_runner
import json
from typing import Annotated, List, Optional, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph

from application.graphs.graph import Graph
from domain.entities import GraphInvokeRequest
from domain.services.music_service import MusicService


def _merge_output(existing: Optional[str], new: Optional[str]) -> Optional[str]:
    """
    Reducer for the 'output' channel. Multiple action nodes may write 'output'
    in the same super-step when classify returns more than one intent (e.g.
    play_media + select_player). Without a reducer LangGraph raises
    InvalidUpdateError. Keep the latest non-empty value.
    """
    return new if new else existing


class MusicGraphState(TypedDict):
    input: GraphInvokeRequest
    intent: Optional[List[str]]
    play_media_query: Optional[str]
    play_media_type: Optional[str]
    player_command_value: Optional[str]
    set_volume_value: Optional[str]
    set_volume_direction: Optional[str]
    now_playing_value: Optional[str]
    player_name: Optional[str]
    player_id: Optional[str]
    output: Annotated[Optional[str], _merge_output]


class MusicGraph(Graph):
    """
    Music Assistant Graph — handles music playback commands via Music Assistant.
    """

    def __init__(
        self,
        llm_chat: BaseChatModel,
        music_service: MusicService,
        provider: str = "OLLAMA",
        strip_think_directive: bool = False,
    ) -> None:
        super().__init__(provider, strip_think_directive)
        self.llm_chat = llm_chat
        self.music_service = music_service
        self.classification_prompt = ChatPromptTemplate.from_template(
            self.load_prompt("music_graph.md")
        )

    # ===============================================
    # Graph Nodes
    # ===============================================

    def _classify_intent(self, data: dict) -> dict:
        invoke_request: GraphInvokeRequest = data["input"]
        print(f"[MusicGraph._classify_intent]: input={invoke_request.message!r}")

        try:
            players = async_runner.run(self.music_service.get_players())
        except Exception as error:
            print(f"[MusicGraph._classify_intent][ERROR][get_players]: {error}")
            players = []

        available_players_csv = ", ".join(p.name for p in players if p.name)

        chain = self.classification_prompt | self.llm_chat
        try:
            response = chain.invoke(
                {
                    "input": invoke_request,
                    "available_players": available_players_csv,
                }
            )
        except KeyError:
            response = chain.invoke({"input": invoke_request})

        extracted = self._extract_structured_output(response.content)
        print(f"[MusicGraph._classify_intent]: raw_output={extracted!r}")

        try:
            parsed = json.loads(extracted) if extracted else {}
            if not isinstance(parsed, dict):
                parsed = {}
        except (json.JSONDecodeError, ValueError):
            parsed = {}

        intents: List[str] = parsed.get("intent", ["not_recognized"]) or [
            "not_recognized"
        ]
        if isinstance(intents, str):
            intents = [intents]

        player_name: str = parsed.get("player_name", "") or ""
        player_id: Optional[str] = parsed.get("player_id") or None

        # Resolve player_name -> player_id
        if player_name:
            matched = next(
                (
                    p
                    for p in players
                    if p.name.lower() == player_name.lower()
                ),
                None,
            )
            if matched:
                player_id = matched.player_id
            elif len(players) == 1:
                player_id = players[0].player_id
            else:
                if "select_player" not in intents:
                    intents.append("select_player")
        else:
            # No player name provided
            if len(players) == 1:
                player_id = players[0].player_id
            elif len(players) > 1:
                if "select_player" not in intents:
                    intents.append("select_player")

        return {
            "intent": intents,
            "input": invoke_request,
            "play_media_query": parsed.get("play_media_query") or None,
            "play_media_type": parsed.get("play_media_type") or None,
            "player_command_value": parsed.get("player_command_value") or None,
            "set_volume_value": parsed.get("set_volume_value") or None,
            "set_volume_direction": parsed.get("set_volume_direction") or None,
            "now_playing_value": parsed.get("now_playing_value") or None,
            "player_name": player_name,
            "player_id": player_id,
        }

    def _handle_play_media(self, data: dict) -> dict:
        query = data.get("play_media_query", "")
        media_type = data.get("play_media_type", "track") or "track"
        player_id = data.get("player_id", "")
        print(
            f"[MusicGraph._handle_play_media]: query={query!r}, "
            f"media_type={media_type!r}, player_id={player_id!r}"
        )

        if not query:
            return {"output": "Nenhuma música especificada."}

        try:
            result = async_runner.run(
                self.music_service.search_and_play(
                    query=query, media_type=media_type, player_id=player_id
                )
            )
            return {"output": result}
        except Exception as error:
            print(f"[MusicGraph._handle_play_media][ERROR]: {error}")
            return {"output": f"Erro ao reproduzir: {error}"}

    def _handle_player_command(self, data: dict) -> dict:
        command = data.get("player_command_value", "")
        player_id = data.get("player_id", "")
        print(
            f"[MusicGraph._handle_player_command]: command={command!r}, "
            f"player_id={player_id!r}"
        )

        if not command:
            return {"output": "Nenhum comando especificado."}

        try:
            result = async_runner.run(
                self.music_service.send_player_command(
                    player_id=player_id, command=command
                )
            )
            return {"output": result}
        except Exception as error:
            print(f"[MusicGraph._handle_player_command][ERROR]: {error}")
            return {"output": f"Erro ao executar comando: {error}"}

    def _handle_set_volume(self, data: dict) -> dict:
        player_id = data.get("player_id", "")
        volume_value = data.get("set_volume_value")
        direction = data.get("set_volume_direction")
        print(
            f"[MusicGraph._handle_set_volume]: value={volume_value!r}, "
            f"direction={direction!r}, player_id={player_id!r}"
        )

        try:
            if volume_value is not None:
                volume = int(str(volume_value))
            elif direction == "up":
                volume = 60
            elif direction == "down":
                volume = 30
            else:
                return {"output": "Não foi possível determinar o volume desejado."}

            result = async_runner.run(
                self.music_service.set_volume(player_id=player_id, volume=volume)
            )
            return {"output": result}
        except Exception as error:
            print(f"[MusicGraph._handle_set_volume][ERROR]: {error}")
            return {"output": f"Erro ao ajustar volume: {error}"}

    def _handle_now_playing(self, data: dict) -> dict:
        player_id = data.get("player_id", "")
        print(f"[MusicGraph._handle_now_playing]: player_id={player_id!r}")

        try:
            result = async_runner.run(
                self.music_service.get_now_playing(player_id=player_id)
            )
            return {"output": result}
        except Exception as error:
            print(f"[MusicGraph._handle_now_playing][ERROR]: {error}")
            return {"output": f"Erro ao consultar reprodução: {error}"}

    def _handle_select_player(self, data: dict) -> dict:
        print(f"[MusicGraph._handle_select_player]: Requesting player selection...")
        try:
            players = async_runner.run(self.music_service.get_players())
            names = ", ".join(p.name for p in players if p.name)
            return {
                "output": (
                    f"Qual player você deseja usar? Disponíveis: {names}"
                )
            }
        except Exception as error:
            print(f"[MusicGraph._handle_select_player][ERROR]: {error}")
            return {"output": "Não consegui obter a lista de players disponíveis."}

    def _handle_not_recognized(self, data: dict) -> dict:
        print(f"[MusicGraph._handle_not_recognized]: Triggered...")
        return {"output": "Não entendi o comando de música. Tente novamente."}

    def _handle_final_response(self, data: dict) -> dict:
        print(f"[MusicGraph._handle_final_response]: Aggregating response...")
        output = data.get("output")
        if output:
            return {"output": output}
        return {"output": "Nenhuma ação de música executada."}

    # ===============================================
    # Private Methods
    # ===============================================

    def _compile(self):
        workflow = StateGraph(MusicGraphState)

        workflow.add_node("classify", RunnableLambda(self._classify_intent))
        workflow.add_node("play_media", RunnableLambda(self._handle_play_media))
        workflow.add_node(
            "player_command", RunnableLambda(self._handle_player_command)
        )
        workflow.add_node("set_volume", RunnableLambda(self._handle_set_volume))
        workflow.add_node("now_playing", RunnableLambda(self._handle_now_playing))
        workflow.add_node(
            "select_player", RunnableLambda(self._handle_select_player)
        )
        workflow.add_node(
            "not_recognized", RunnableLambda(self._handle_not_recognized)
        )
        workflow.add_node(
            "final_response", RunnableLambda(self._handle_final_response)
        )

        workflow.add_edge(START, "classify")

        def intent_router(state):
            return state.get("intent", [])

        workflow.add_conditional_edges("classify", intent_router)

        action_nodes = [
            "play_media",
            "player_command",
            "set_volume",
            "now_playing",
            "select_player",
            "not_recognized",
        ]
        for node in action_nodes:
            workflow.add_edge(node, "final_response")

        workflow.add_edge("final_response", END)

        return workflow.compile()

    # ===============================================
    # Public Methods
    # ===============================================

    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        if self._compiled_graph is None:
            self._compiled_graph = self._compile()
        app = self._compiled_graph
        return app.invoke({"input": invoke_request})
