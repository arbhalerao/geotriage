from typing import TypeVar

from pydantic import BaseModel, ValidationError

from llm.types import Client, LLMError, Reply

T = TypeVar("T", bound=BaseModel)


def every_field_required(schema: dict) -> dict:
    # constrained decoding lets a model skip any field that isn't required, and a small model does
    return {**schema, "required": list(schema.get("properties", {}))}


def ask_structured(client: Client, messages: list[dict], output: type[T], *, require_all: bool = False) -> tuple[T, Reply]:
    schema = output.model_json_schema()
    reply = client.chat(messages, schema=every_field_required(schema) if require_all else schema)
    try:
        return output.model_validate_json(reply.content), reply
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'reply'}: {e['msg']}" for e in exc.errors()[:3])
        raise LLMError(f"the reply did not match {output.__name__}: {problems}", reply=reply) from exc
