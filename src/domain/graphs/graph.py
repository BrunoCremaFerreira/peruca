from abc import ABC, abstractmethod
from pathlib import Path


class Graph(ABC):
    """
    Graph Interface
    """

    @abstractmethod
    def invoke(self, user_message) -> dict:
        pass


    def load_prompt(self, name: str) -> str:
        PROMPTS_DIR = Path(__file__).parent.parent.parent / "infra" / "prompts"
        return (PROMPTS_DIR / name).read_text(encoding="utf-8")