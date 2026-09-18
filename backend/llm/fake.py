from typing import Iterable, Sequence

from llm.types import Reply, Tool


class FakeClient:
    def __init__(self, replies: Iterable[Reply | str | Exception]):
        self._replies = list(replies)
        self.requests: list[dict] = []

    @property
    def identity(self) -> dict:
        return {"provider": "fake"}

    def chat(self, messages: list[dict], *, tools: Sequence[Tool] = (), schema: dict | None = None) -> Reply:
        self.requests.append({"messages": messages, "tools": list(tools), "schema": schema})
        if not self._replies:
            raise AssertionError(f"the fake model has no reply scripted for request {len(self.requests)}")
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return Reply(content=reply, model="fake") if isinstance(reply, str) else reply
