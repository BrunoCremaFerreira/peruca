from abc import ABC, abstractmethod
from pathlib import Path

from domain.entities import GraphInvokeRequest


class Graph(ABC):
    """
    Graph Interface
    """

    @abstractmethod
    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        """
        Execute LLM processing
        """
        pass


    def load_prompt(self, name: str) -> str:
        """
        Load prompt file by name
        """

        PROMPTS_DIR = Path(__file__).parent.parent.parent / "infra" / "prompts"
        return (PROMPTS_DIR / name).read_text(encoding="utf-8")