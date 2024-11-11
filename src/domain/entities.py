from dataclasses import dataclass
from enum import Enum
import uuid

# ========================
# Prompt Classes
# ========================


class PromptType(Enum):
    CLASSIFICATION = "CLASSIFICATION"
    EXECUTION = "EXECUTION"


@dataclass
class SystemPrompt:
    __table__ = "system_prompts"

    id: uuid.UUID
    data: object
