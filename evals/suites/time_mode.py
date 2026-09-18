from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from evals.runner import Suite
from llm import Client, ask_structured, load_prompt

# fixed, so "last summer" means the same months in every run, whatever the calendar says
TODAY = "2026-09-14"

PROMPT = load_prompt("time_mode", Path(__file__).parent)


class Answer(BaseModel):
    mode: Literal["historical", "recurring"]


def run(case: dict, client: Client) -> dict:
    messages = [
        {"role": "system", "content": PROMPT.render(today=TODAY)},
        {"role": "user", "content": case["input"]},
    ]
    answer, _ = ask_structured(client, messages, Answer)
    return answer.model_dump()


def score(case: dict, output: dict) -> dict[str, float]:
    return {"mode": float(output["mode"] == case["expected"]["mode"])}


SUITE = Suite(
    name="time_mode",
    description="historical or recurring, from one sentence",
    metrics=["mode"],
    prompts=[PROMPT],
    run=run,
    score=score,
)
