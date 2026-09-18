import json
import logging
import time
from typing import Sequence

import httpx

from llm.types import LLMError, Reply, Tool, ToolCall

log = logging.getLogger(__name__)

RETRIES = 2
BACKOFF_SECONDS = 2.0


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout_s: float = 300.0,
        context_tokens: int = 8192,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = model
        self.context_tokens = context_tokens
        self._http = httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_s, connect=5.0),
            transport=transport,
        )

    @property
    def identity(self) -> dict:
        return {"provider": "ollama", "model": self.model, "options": self._options()}

    def _options(self) -> dict:
        return {"temperature": 0, "seed": 0, "num_ctx": self.context_tokens}

    def chat(self, messages: list[dict], *, tools: Sequence[Tool] = (), schema: dict | None = None) -> Reply:
        body = {"model": self.model, "messages": messages, "stream": False, "options": self._options()}
        if tools:
            body["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}} for t in tools]
        if schema is not None:
            body["format"] = schema

        started = time.monotonic()
        data = self._post("/api/chat", body)
        return self._reply(data, duration_ms=int((time.monotonic() - started) * 1000))

    def _post(self, path: str, body: dict) -> dict:
        for attempt in range(RETRIES + 1):
            last = attempt == RETRIES
            try:
                response = self._http.post(path, json=body)
            except httpx.TransportError as exc:
                if last:
                    raise LLMError(f"could not reach the model server: {exc}") from exc
                log.warning("model server unreachable (attempt %d): %s", attempt + 1, exc)
            else:
                if response.status_code < 400:
                    return response.json()
                detail = _error_detail(response)
                if response.status_code == 404 and "not found" in detail:
                    raise LLMError(f"model {self.model!r} is not pulled, run `make llm-pull`")
                if response.status_code < 500 or last:
                    raise LLMError(f"model server returned {response.status_code}: {detail}")
                log.warning("model server returned %d (attempt %d): %s", response.status_code, attempt + 1, detail)
            time.sleep(BACKOFF_SECONDS * (2**attempt))
        raise AssertionError("unreachable")

    def _reply(self, data: dict, duration_ms: int) -> Reply:
        message = data.get("message") or {}
        calls = []
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            arguments = function.get("arguments") or {}
            if isinstance(arguments, str):
                # some models hand arguments back as a JSON string rather than an object
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError as exc:
                    raise LLMError(f"tool call {function.get('name')!r} had arguments that are not JSON") from exc
            calls.append(ToolCall(name=function.get("name", ""), arguments=arguments, id=call.get("id", "")))

        return Reply(
            content=message.get("content") or "",
            tool_calls=calls,
            model=data.get("model", self.model),
            # absent when Ollama reuses a prompt it already evaluated
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            duration_ms=duration_ms,
        )


def _error_detail(response: httpx.Response) -> str:
    try:
        return str(response.json().get("error", response.text))
    except ValueError:
        return response.text
