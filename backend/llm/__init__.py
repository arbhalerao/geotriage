from llm.cache import CachedClient
from llm.fake import FakeClient
from llm.ollama import OllamaClient
from llm.prompts import Prompt, load_prompt
from llm.structured import ask_structured
from llm.trace import TracedClient
from llm.types import Client, LLMError, Reply, Tool, ToolCall


def default_client() -> OllamaClient:
    from core.config import settings

    return OllamaClient(
        settings.LLM_BASE_URL,
        settings.LLM_MODEL,
        timeout_s=settings.LLM_TIMEOUT_SECONDS,
        context_tokens=settings.LLM_CONTEXT_TOKENS,
    )


__all__ = [
    "CachedClient",
    "Client",
    "FakeClient",
    "LLMError",
    "OllamaClient",
    "Prompt",
    "Reply",
    "Tool",
    "ToolCall",
    "TracedClient",
    "ask_structured",
    "default_client",
    "load_prompt",
]
