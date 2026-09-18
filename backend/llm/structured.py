from typing import TypeVar

from pydantic import BaseModel, ValidationError

from llm.types import Client, LLMError, Reply

T = TypeVar("T", bound=BaseModel)


def ask_structured(client: Client, messages: list[dict], output: type[T]) -> tuple[T, Reply]:
    reply = client.chat(messages, schema=output.model_json_schema())
    try:
        return output.model_validate_json(reply.content), reply
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'reply'}: {e['msg']}" for e in exc.errors()[:3])
        raise LLMError(f"the reply did not match {output.__name__}: {problems}", reply=reply) from exc
