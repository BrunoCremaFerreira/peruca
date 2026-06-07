from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph, START, END
from langchain_core.prompts import ChatPromptTemplate
from typing import Optional, TypedDict
from langchain_core.language_models.chat_models import BaseChatModel
from application.graphs.graph import Graph
from application.graphs.only_talk_graph import OnlyTalkGraph
from application.graphs.shopping_list_graph import ShoppingListGraph
from application.graphs.smart_home_lights_graph import SmartHomeLightsGraph
from application.graphs.smart_home_climate_graph import SmartHomeClimateGraph
from application.graphs.smart_home_sensors_graph import SmartHomeSensorsGraph
from application.graphs.smart_home_cameras_graph import SmartHomeCamerasGraph
from domain.entities import GraphInvokeRequest


class MainGraphState(TypedDict):
    input: str
    intent: Optional[list[str]]
    output_lights: Optional[str]
    output_shopping: Optional[str]
    output_cams: Optional[str]
    output_only_talking: Optional[str]
    output_climate: Optional[str]
    output_sensors: Optional[str]
    output_music: Optional[str]
    output: Optional[str]


class MainGraph(Graph):
    def __init__(
        self,
        llm_chat: BaseChatModel,
        only_talk_graph: OnlyTalkGraph,
        shopping_list_graph: ShoppingListGraph,
        smart_home_lights_graph: SmartHomeLightsGraph,
        smart_home_climate_graph: SmartHomeClimateGraph,
        smart_home_sensors_graph: SmartHomeSensorsGraph,
        smart_home_cameras_graph: SmartHomeCamerasGraph = None,
        music_graph=None,
        provider: str = "OLLAMA",
    ):
        super().__init__(provider)
        self.llm_chat = llm_chat
        self.only_talk_graph = only_talk_graph
        self.shopping_list_graph = shopping_list_graph
        self.smart_home_lights_graph = smart_home_lights_graph
        self.smart_home_climate_graph = smart_home_climate_graph
        self.smart_home_sensors_graph = smart_home_sensors_graph
        self.smart_home_cameras_graph = smart_home_cameras_graph
        self.music_graph = music_graph
        self.classification_prompt = ChatPromptTemplate.from_template(
            self.load_prompt("main_graph.md")
        )
        self.final_response_prompt = ChatPromptTemplate.from_template(
            self.load_prompt("main_graph_final_response.md")
        )

    # ===============================================
    # Graph Nodes
    # ===============================================
    def _classify_intent(self, data):
        music_is_playing = data["input"].context_hints.get("music_is_playing", False)
        hint_str = (
            "Sim, há música tocando no momento."
            if music_is_playing
            else "Não."
        )
        invoke_payload = {
            "input": data["input"].message,
            "music_is_playing": hint_str,
        }
        chain = self.classification_prompt | self.llm_chat
        try:
            response = chain.invoke(invoke_payload)
        except Exception:
            response = chain.invoke({"input": data["input"].message, "music_is_playing": hint_str})
        cleaned = self._remove_thinking_tag(response.content)
        if isinstance(cleaned, str):
            # Qwen3 mimics the prompt examples and may emit smart/curly quotes,
            # which eval() rejects. Normalize them so the classification is not
            # silently lost and collapsed into "only_talking".
            cleaned = (
                cleaned.replace("“", '"')
                .replace("”", '"')
                .replace("‘", "'")
                .replace("’", "'")
            )
        try:
            intents = eval(cleaned) if isinstance(cleaned, str) else []
            if isinstance(intents, str):
                intents = [intents]
        except:
            intents = ["only_talking"]
        return {"intent": intents, "input": data["input"]}

    def _handle_music(self, data):
        print(f"[main_graph.handle_music]: Triggered...")
        result = self.music_graph.invoke(invoke_request=data["input"])
        return {"output_music": result.get("output")}

    def _handle_final_response(self, data):
        outputs = [
            e
            for e in [
                data.get("output_lights"),
                data.get("output_shopping"),
                data.get("output_cams"),
                data.get("output_only_talking"),
                data.get("output_climate"),
                data.get("output_sensors"),
                data.get("output_music"),
            ]
            if e is not None and e.strip()
        ]

        intents = data.get("intent", [])

        if len(intents) == 1 and "only_talking" in intents:
            # Only_talking
            response = outputs[0]
        else:
            # Merging multiple cathegory responses into a friendly response
            responses = "\n\n".join([f"{i + 1}. {s}" for i, s in enumerate(outputs)])
            final_reponse_chain = self.final_response_prompt | self.llm_chat
            llm_response = final_reponse_chain.invoke(
                {"input": data["input"].message, "responses": responses}
            )
            response = self._remove_thinking_tag(llm_response.content)
            # The merge LLM occasionally returns an empty string; never surface
            # an empty output — fall back to the raw sub-graph responses.
            if not response or not response.strip():
                response = "\n\n".join(outputs)

        return {"output": response}

    def _handle_smart_home_lights(self, data):
        print(f"[main_graph.handle_smart_home_lights]: Triggered...")
        result: str = self.smart_home_lights_graph.invoke(invoke_request=data["input"])
        return {"output_lights": result.get("output")}

    def _handle_smart_home_climate(self, data):
        print(f"[main_graph.handle_smart_home_climate]: Triggered...")
        result = self.smart_home_climate_graph.invoke(invoke_request=data["input"])
        return {"output_climate": result.get("output")}

    def _handle_smart_home_sensors(self, data):
        print(f"[main_graph.handle_smart_home_sensors]: Triggered...")
        result = self.smart_home_sensors_graph.invoke(invoke_request=data["input"])
        return {"output_sensors": result.get("output")}

    def _handle_smart_home_security_cams(self, data):
        print(f"[main_graph.handle_smart_home_security_cams]: Triggered...")
        result = self.smart_home_cameras_graph.invoke(
            GraphInvokeRequest(message=data["input"].message, user=data["input"].user)
        )
        return {"output_cams": result.get("output", "")}

    def _handle_shopping_list(self, data):
        print(f"[main_graph.handle_shopping_list]: : Triggered...")
        result: str = self.shopping_list_graph.invoke(invoke_request=data["input"])
        return {"output_shopping": result.get("output")}

    def _handle_only_talking(self, data):
        print(f"[main_graph.handle_only_talking]: Triggered...")
        result = self.only_talk_graph.invoke(invoke_request=data["input"])
        return {"output_only_talking": f"{self._remove_thinking_tag(result)}"}

    # ===============================================
    # Private Methods
    # ===============================================

    def _compile(self):
        workflow = StateGraph(MainGraphState)

        workflow.add_node("classify", RunnableLambda(self._classify_intent))
        workflow.add_node(
            "smart_home_lights", RunnableLambda(self._handle_smart_home_lights)
        )
        workflow.add_node(
            "smart_home_security_cams",
            RunnableLambda(self._handle_smart_home_security_cams),
        )
        workflow.add_node("shopping_list", RunnableLambda(self._handle_shopping_list))
        workflow.add_node("only_talking", RunnableLambda(self._handle_only_talking))
        workflow.add_node(
            "smart_home_climate", RunnableLambda(self._handle_smart_home_climate)
        )
        workflow.add_node(
            "smart_home_sensors", RunnableLambda(self._handle_smart_home_sensors)
        )

        action_nodes = [
            "smart_home_lights",
            "smart_home_security_cams",
            "shopping_list",
            "only_talking",
            "smart_home_climate",
            "smart_home_sensors",
        ]

        if self.music_graph is not None:
            workflow.add_node("music", RunnableLambda(self._handle_music))
            action_nodes.append("music")

        workflow.add_node("final_response", RunnableLambda(self._handle_final_response))
        workflow.add_edge(START, "classify")

        def intent_router(state):
            return state.get("intent", [])

        workflow.add_conditional_edges("classify", intent_router)

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
