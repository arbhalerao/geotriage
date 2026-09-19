import json
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel

import llm.ollama
from core.db.models.enums import LlmCallOutcome
from llm import CachedClient, FakeClient, LLMError, OllamaClient, Prompt, Reply, Tool, TracedClient, ask_structured


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(llm.ollama.time, "sleep", lambda _s: None)


def ollama(handler) -> tuple[OllamaClient, list[dict]]:
    bodies = []

    def record(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return handler(request)

    return OllamaClient("http://ollama", "small-model", transport=httpx.MockTransport(record)), bodies


def chat_response(content="", tool_calls=None, **extra) -> httpx.Response:
    return httpx.Response(200, json={"model": "small-model", "message": {"role": "assistant", "content": content, "tool_calls": tool_calls}, **extra})


USER = [{"role": "user", "content": "hi"}]


def test_a_reply_carries_its_text_and_token_counts():
    client, _ = ollama(lambda _r: chat_response("ready", prompt_eval_count=17, eval_count=2))
    reply = client.chat(USER)
    assert (reply.content, reply.input_tokens, reply.output_tokens, reply.model) == ("ready", 17, 2, "small-model")


def test_a_reusable_prompt_reports_zero_input_tokens_rather_than_failing():
    """Ollama leaves prompt_eval_count out when it reuses a prompt it already evaluated"""
    client, _ = ollama(lambda _r: chat_response("ready", eval_count=2))
    assert client.chat(USER).input_tokens == 0


def test_tool_calls_come_back_with_their_arguments():
    call = {"id": "c1", "function": {"name": "find_area", "arguments": {"place": "Dhaka"}}}
    client, _ = ollama(lambda _r: chat_response(tool_calls=[call]))
    [tool_call] = client.chat(USER).tool_calls
    assert (tool_call.name, tool_call.arguments, tool_call.id) == ("find_area", {"place": "Dhaka"}, "c1")


def test_tool_arguments_sent_as_a_json_string_are_decoded():
    call = {"function": {"name": "find_area", "arguments": '{"place": "Dhaka"}'}}
    client, _ = ollama(lambda _r: chat_response(tool_calls=[call]))
    assert client.chat(USER).tool_calls[0].arguments == {"place": "Dhaka"}


def test_tool_arguments_that_are_not_json_are_an_error_not_a_crash():
    call = {"function": {"name": "find_area", "arguments": "place=Dhaka"}}
    client, _ = ollama(lambda _r: chat_response(tool_calls=[call]))
    with pytest.raises(LLMError, match="find_area"):
        client.chat(USER)


def test_tools_and_schema_are_sent_and_sampling_is_deterministic():
    client, bodies = ollama(lambda _r: chat_response("{}"))
    tool = Tool("find_area", "look up a place", {"type": "object", "properties": {}})
    client.chat(USER, tools=[tool], schema={"type": "object"})

    [body] = bodies
    assert body["tools"][0]["function"]["name"] == "find_area"
    assert body["format"] == {"type": "object"}
    assert body["stream"] is False
    assert body["options"]["temperature"] == 0


def test_a_server_error_is_retried_until_it_clears():
    responses = iter([httpx.Response(500, json={"error": "loading"}), chat_response("ready")])
    client, bodies = ollama(lambda _r: next(responses))
    assert client.chat(USER).content == "ready"
    assert len(bodies) == 2


def test_a_server_error_that_persists_gives_up_after_the_retries():
    client, bodies = ollama(lambda _r: httpx.Response(503, json={"error": "overloaded"}))
    with pytest.raises(LLMError, match="503"):
        client.chat(USER)
    assert len(bodies) == llm.ollama.RETRIES + 1


def test_a_bad_request_is_not_retried():
    """asking again won't fix what was wrong with the question"""
    client, bodies = ollama(lambda _r: httpx.Response(400, json={"error": "invalid format"}))
    with pytest.raises(LLMError, match="invalid format"):
        client.chat(USER)
    assert len(bodies) == 1


def test_a_model_that_is_not_pulled_says_how_to_fix_it():
    client, _ = ollama(lambda _r: httpx.Response(404, json={"error": "model 'small-model' not found"}))
    with pytest.raises(LLMError, match="make llm-pull"):
        client.chat(USER)


def test_an_unreachable_server_is_retried_then_reported():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    client, bodies = ollama(refuse)
    with pytest.raises(LLMError, match="could not reach"):
        client.chat(USER)
    assert len(bodies) == llm.ollama.RETRIES + 1


class Counting(FakeClient):
    def __init__(self, model="small-model"):
        super().__init__([])
        self.model = model

    @property
    def identity(self):
        return {"provider": "fake", "model": self.model}

    def chat(self, messages, *, tools=(), schema=None):
        self.requests.append(messages)
        return Reply(content=f"reply {len(self.requests)}", model=self.model, output_tokens=3, duration_ms=1500)


def test_an_unchanged_request_is_replayed_from_the_cache(tmp_path: Path):
    inner = Counting()
    client = CachedClient(inner, tmp_path)

    first = client.chat(USER)
    again = client.chat(USER)

    assert len(inner.requests) == 1
    assert (again.content, again.output_tokens, again.duration_ms) == (first.content, 3, 1500)
    assert again.cached and not first.cached


def test_a_different_question_or_model_misses_the_cache(tmp_path: Path):
    client = CachedClient(Counting(), tmp_path)
    client.chat(USER)
    assert client.chat([{"role": "user", "content": "hello"}]).cached is False
    assert CachedClient(Counting(model="bigger-model"), tmp_path).chat(USER).cached is False


def test_an_interrupted_write_is_never_read_back(tmp_path: Path):
    client = CachedClient(Counting(), tmp_path)
    key = client.key(USER, (), None)
    (tmp_path / f"{key}.partial").write_text('{"content": "half')
    assert client.chat(USER).cached is False


def test_a_prompt_version_changes_with_its_text():
    assert Prompt("draft", "one").version != Prompt("draft", "two").version
    assert Prompt("draft", "one").version == Prompt("draft", "one").version
    assert Prompt("draft", "one").version.startswith("draft@")


def test_a_prompt_fills_placeholders_and_leaves_json_braces_alone():
    prompt = Prompt("draft", 'Today is $today. Reply like {"mode": "recurring"}')
    assert prompt.render(today="2026-09-14") == 'Today is 2026-09-14. Reply like {"mode": "recurring"}'


class Mode(BaseModel):
    mode: str


def test_a_structured_reply_is_parsed_into_its_model():
    fake = FakeClient(['{"mode": "recurring"}'])
    answer, _ = ask_structured(fake, USER, Mode)
    assert answer.mode == "recurring"
    assert fake.requests[0]["schema"]["properties"]["mode"]["type"] == "string"


class Optional(BaseModel):
    mode: str
    note: str | None = None


def test_every_field_can_be_required_of_the_model_while_the_reader_stays_lenient():
    """a small model skips any field it isn't made to write"""
    fake = FakeClient(['{"mode": "recurring"}'])
    answer, _ = ask_structured(fake, USER, Optional, require_all=True)
    assert fake.requests[0]["schema"]["required"] == ["mode", "note"]
    assert answer.note is None


def test_a_structured_reply_that_does_not_fit_keeps_the_reply_for_inspection():
    with pytest.raises(LLMError, match="Mode") as caught:
        ask_structured(FakeClient(['{"wrong": 1}']), USER, Mode)
    assert caught.value.reply.content == '{"wrong": 1}'


class Rows:
    def __init__(self, fail=False):
        self.rows, self.fail = [], fail

    @contextmanager
    def __call__(self):
        rows = self

        class Session:
            def add(self, row):
                rows.rows.append(row)

            def commit(self):
                if rows.fail:
                    raise RuntimeError("database went away")

        yield Session()


def test_a_successful_call_is_recorded_with_what_it_cost():
    rows = Rows()
    client = TracedClient(FakeClient([Reply("ready", model="small-model", input_tokens=17, output_tokens=2, duration_ms=900)]), purpose="check", prompt_version="check@abc", session_factory=rows)
    client.chat(USER, tools=[Tool("find_area", "look up a place", {})])

    [row] = rows.rows
    assert (row.purpose, row.prompt_version, row.outcome, row.model) == ("check", "check@abc", LlmCallOutcome.ok, "small-model")
    assert (row.input_tokens, row.output_tokens, row.duration_ms) == (17, 2, 900)
    assert row.request["tools"] == ["find_area"], "tool names only, their definitions repeat on every call"
    assert row.response["content"] == "ready"


def test_a_failed_call_is_recorded_and_still_raised():
    rows = Rows()
    client = TracedClient(FakeClient([LLMError("model server returned 503")]), purpose="check", session_factory=rows)
    with pytest.raises(LLMError):
        client.chat(USER)

    [row] = rows.rows
    assert row.outcome == LlmCallOutcome.error
    assert "503" in row.error
    assert row.model == "unknown", "a fake client names no model, and the row still needs one"


def test_a_database_failure_never_costs_the_caller_its_reply():
    client = TracedClient(FakeClient(["ready"]), purpose="check", session_factory=Rows(fail=True))
    assert client.chat(USER).content == "ready"


def test_the_fake_model_says_when_a_test_asked_more_than_it_scripted():
    fake = FakeClient(["one"])
    fake.chat(USER)
    with pytest.raises(AssertionError, match="request 2"):
        fake.chat(USER)
