import re
from abc import ABC, abstractmethod
from pathlib import Path

from domain.entities import GraphInvokeRequest


class Graph(ABC):

    def __init__(self, provider: str = "OLLAMA"):
        self.provider = provider.upper()

    @abstractmethod
    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        pass

    def _remove_thinking_tag(self, input_str: str) -> str:
        cleaned = input_str.replace("<think>\n\n</think>\n\n", "").strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1]).strip()
        return cleaned

    def load_prompt(self, name: str) -> str:
        PROMPTS_DIR = Path(__file__).parent.parent.parent / "infra" / "prompts"
        content = (PROMPTS_DIR / name).read_text(encoding="utf-8")
        if self.provider != "OLLAMA":
            content = re.sub(r"^/no_think\S*[ \t]*\n?", "", content)
        return content
