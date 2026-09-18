from dataclasses import dataclass, field
from typing import Protocol, Sequence


class LLMError(Exception):
    def __init__(self, message: str, reply: "Reply | None" = None):
        super().__init__(message)
        self.reply = reply


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict
    id: str = ""


@dataclass
class Reply:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    cached: bool = False


class Client(Protocol):
    @property
    def identity(self) -> dict: ...

    def chat(self, messages: list[dict], *, tools: Sequence[Tool] = (), schema: dict | None = None) -> Reply: ...
