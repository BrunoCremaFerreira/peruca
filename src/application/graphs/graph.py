import re
from abc import ABC, abstractmethod
from pathlib import Path

from domain.entities import GraphInvokeRequest

_prompt_cache: dict[str, str] = {}


class Graph(ABC):

    def __init__(self, provider: str = "OLLAMA", strip_think_directive: bool = False):
        self.provider = provider.upper()
        self.strip_think_directive = strip_think_directive
        self._compiled_graph = None

    @abstractmethod
    def invoke(self, invoke_request: GraphInvokeRequest) -> dict:
        pass

    def _remove_thinking_tag(self, input_str: str) -> str:
        cleaned = re.sub(
            r"<think>.*?</think>", "", input_str, flags=re.DOTALL
        )
        cleaned = cleaned.replace("<think>\n\n</think>\n\n", "").strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1]).strip()
        return cleaned

    def _extract_structured_output(self, raw: str) -> str | None:
        raw_str = raw if isinstance(raw, str) else ""
        cleaned = self._remove_thinking_tag(raw_str)
        cleaned = (
            cleaned
            .replace("\u201c", '"').replace("\u201d", '"')
            .replace("\u2018", "'").replace("\u2019", "'")
        )
        candidates = []
        for open_ch, close_ch in [("[", "]"), ("{", "}")]:
            start = cleaned.find(open_ch)
            if start == -1:
                continue
            candidates.append((start, open_ch, close_ch))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])
        start, open_ch, close_ch = candidates[0]
        depth = 0
        for i, ch in enumerate(cleaned[start:], start):
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return cleaned[start:i + 1]
        return None

    def load_prompt(self, name: str, llm_strip_think_directive: bool = False) -> str:
        global _prompt_cache
        if name not in _prompt_cache:
            PROMPTS_DIR = Path(__file__).parent.parent.parent / "infra" / "prompts"
            _prompt_cache[name] = (PROMPTS_DIR / name).read_text(encoding="utf-8")
        content = _prompt_cache[name]
        if self.provider != "OLLAMA" or llm_strip_think_directive or self.strip_think_directive:
            content = re.sub(r"^/no_think\S*[ \t]*\n?", "", content)
        return content
