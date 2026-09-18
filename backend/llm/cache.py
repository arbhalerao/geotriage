import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from llm.types import Client, Reply, Tool, ToolCall


class CachedClient:
    def __init__(self, inner: Client, directory: Path):
        self._inner = inner
        self._directory = directory

    @property
    def identity(self) -> dict:
        return self._inner.identity

    def key(self, messages: list[dict], tools: Sequence[Tool], schema: dict | None) -> str:
        material = {"client": self._inner.identity, "messages": messages, "tools": [asdict(t) for t in tools], "schema": schema}
        return hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()

    def chat(self, messages: list[dict], *, tools: Sequence[Tool] = (), schema: dict | None = None) -> Reply:
        path = self._directory / f"{self.key(messages, tools, schema)}.json"
        if path.exists():
            stored = json.loads(path.read_text())
            stored["tool_calls"] = [ToolCall(**call) for call in stored["tool_calls"]]
            return Reply(**{**stored, "cached": True})

        reply = self._inner.chat(messages, tools=tools, schema=schema)

        self._directory.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".partial")
        partial.write_text(json.dumps(asdict(reply)))
        os.replace(partial, path)
        return reply
