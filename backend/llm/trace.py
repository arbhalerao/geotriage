import logging
import time
import uuid
from dataclasses import asdict
from typing import Sequence

from core.db.models.enums import LlmCallOutcome
from core.db.models.llm import LlmCall
from llm.types import Client, Reply, Tool

log = logging.getLogger(__name__)


class TracedClient:
    def __init__(
        self,
        inner: Client,
        *,
        purpose: str,
        prompt_version: str | None = None,
        job_id: uuid.UUID | None = None,
        session_factory=None,
    ):
        self._inner = inner
        self.purpose = purpose
        self.prompt_version = prompt_version
        self.job_id = job_id
        self._session_factory = session_factory

    @property
    def identity(self) -> dict:
        return self._inner.identity

    def chat(self, messages: list[dict], *, tools: Sequence[Tool] = (), schema: dict | None = None) -> Reply:
        request = {"messages": messages, "tools": [t.name for t in tools], "schema": schema}
        started = time.monotonic()
        try:
            reply = self._inner.chat(messages, tools=tools, schema=schema)
        except Exception as exc:
            self._record(
                LlmCall(
                    outcome=LlmCallOutcome.error,
                    error=str(exc)[:1000],
                    duration_ms=int((time.monotonic() - started) * 1000),
                    request=request,
                    response=None,
                )
            )
            raise

        self._record(
            LlmCall(
                outcome=LlmCallOutcome.ok,
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                duration_ms=reply.duration_ms,
                request=request,
                response={"content": reply.content, "tool_calls": [asdict(c) for c in reply.tool_calls]},
                model=reply.model or None,
            )
        )
        return reply

    def _record(self, row: LlmCall) -> None:
        row.purpose = self.purpose
        row.prompt_version = self.prompt_version
        row.job_id = self.job_id
        row.model = row.model or self._inner.identity.get("model", "unknown")
        try:
            factory = self._session_factory or _default_session_factory()
            with factory() as db:
                db.add(row)
                db.commit()
        except Exception:  # noqa: BLE001 — tracing must never break the call it traces
            log.warning("could not record a %s call to the model", self.purpose, exc_info=True)


def _default_session_factory():
    # imported late, so building a client never needs a database connection
    from core.db.sync import get_session

    return get_session
