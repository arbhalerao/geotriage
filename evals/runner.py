import json
import re
import statistics
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from llm import Client, LLMError, Prompt, Tool
from llm.types import Reply

EVALS_DIR = Path(__file__).parent
DATASETS_DIR = EVALS_DIR / "datasets"
RESULTS_DIR = EVALS_DIR / "results"
CACHE_DIR = EVALS_DIR / ".cache"


@dataclass(frozen=True)
class Suite:
    name: str
    description: str
    metrics: Sequence[str]
    prompts: Sequence[Prompt]
    run: Callable[[dict, Client], dict]
    score: Callable[[dict, dict], dict[str, float]]
    dataset: str = ""
    metrics_for: Callable[[dict], Sequence[str]] | None = None
    uses_model: bool = True
    targets: dict[str, tuple[str, float]] | None = None

    @property
    def dataset_name(self) -> str:
        return self.dataset or self.name

    def applicable(self, case: dict) -> Sequence[str]:
        return self.metrics_for(case) if self.metrics_for else self.metrics


def load_cases(suite: str, tag: str | None = None, directory: Path = DATASETS_DIR) -> list[dict]:
    """one JSON object per line: `id`, `input`, `expected`, and optional `tags`"""
    cases, seen = [], set()
    for number, line in enumerate((directory / f"{suite}.jsonl").read_text().splitlines(), 1):
        if not line.strip():
            continue
        case = json.loads(line)
        if case["id"] in seen:
            raise ValueError(f"{suite}.jsonl line {number}: case id {case['id']!r} is used twice")
        seen.add(case["id"])
        if tag is None or tag in case.get("tags", []):
            cases.append(case)
    return cases


class _Meter:
    def __init__(self, inner: Client):
        self._inner = inner
        self.reset()

    @property
    def identity(self) -> dict:
        return self._inner.identity

    def reset(self) -> None:
        self.calls = self.cached = self.input_tokens = self.output_tokens = self.duration_ms = 0

    def chat(self, messages: list[dict], *, tools: Sequence[Tool] = (), schema: dict | None = None) -> Reply:
        reply = self._inner.chat(messages, tools=tools, schema=schema)
        self.calls += 1
        self.cached += reply.cached
        self.input_tokens += reply.input_tokens
        self.output_tokens += reply.output_tokens
        # a replayed reply keeps the time it originally took, so latency stays comparable across runs
        self.duration_ms += reply.duration_ms
        return reply


def run_suite(suite: Suite, cases: list[dict], client: Client, progress: Callable[[str], None] = print) -> dict:
    meter = _Meter(client)
    started = datetime.now(timezone.utc)
    results = []

    for index, case in enumerate(cases, 1):
        meter.reset()
        output, error = None, None
        try:
            output = suite.run(case, meter)
            scores = suite.score(case, output)
        except Exception as exc:  # noqa: BLE001 — a case that fails scores zero, and the run carries on
            error = f"{type(exc).__name__}: {exc}"
            scores = {metric: 0.0 for metric in suite.applicable(case)}
            if isinstance(exc, LLMError) and exc.reply is not None:
                output = {"unusable_reply": exc.reply.content}

        results.append(
            {
                "id": case["id"],
                "tags": case.get("tags", []),
                "output": output,
                "scores": scores,
                "error": error,
                "calls": meter.calls,
                "cached": meter.cached,
                "input_tokens": meter.input_tokens,
                "output_tokens": meter.output_tokens,
                "duration_ms": meter.duration_ms,
            }
        )
        marks = " ".join(f"{m}={scores[m]:.2f}" for m in suite.metrics if m in scores)
        source = "cached" if meter.calls and meter.cached == meter.calls else f"{meter.duration_ms / 1000:.1f} s"
        progress(f"[{index}/{len(cases)}] {case['id']}  {marks}  ({source}){'  ' + error if error else ''}")

    return {
        "suite": suite.name,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "git": _git_revision(),
        "client": client.identity,
        "prompts": {p.name: p.version for p in suite.prompts},
        "summary": summarise(suite, results),
        "cases": results,
    }


def summarise(suite: Suite, results: list[dict]) -> dict:
    count = len(results)
    summary = {}
    for metric in suite.metrics:
        values = [r["scores"][metric] for r in results if metric in r["scores"]]
        summary[metric] = round(sum(values) / len(values), 3) if values else None
    summary.update(
        cases=count,
        errors=sum(1 for r in results if r["error"]),
        input_tokens=sum(r["input_tokens"] for r in results),
        output_tokens=sum(r["output_tokens"] for r in results),
        median_ms=int(statistics.median(r["duration_ms"] for r in results)) if count else 0,
    )
    return summary


def meets(value: float | None, target: tuple[str, float]) -> bool:
    op, bar = target
    if value is None:
        return False
    return value >= bar if op == ">=" else value <= bar


def save_run(run: dict, directory: Path = RESULTS_DIR) -> Path:
    stamp = datetime.fromisoformat(run["started_at"]).strftime("%Y%m%d-%H%M%S")
    model = re.sub(r"[^a-zA-Z0-9.]+", "-", run["client"].get("model", run["client"].get("provider", "unknown")))
    path = directory / run["suite"] / f"{stamp}_{model}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(run, indent=2) + "\n")
    return path


def saved_runs(suite: str, directory: Path = RESULTS_DIR) -> list[Path]:
    """oldest first, the timestamp leads every name"""
    return sorted((directory / suite).glob("*.json"))


def compare(before: dict, after: dict, metrics: Sequence[str]) -> str:
    lines = [f"{before['suite']}: {_label(before)}  ->  {_label(after)}"]
    for name in sorted(set(before["prompts"]) | set(after["prompts"])):
        was, now = before["prompts"].get(name), after["prompts"].get(name)
        if was != now:
            lines.append(f"prompt changed: {was} -> {now}")
    if before["client"] != after["client"]:
        lines.append(f"client changed: {before['client']} -> {after['client']}")
    if before.get("tag") != after.get("tag"):
        # scores over different case sets aren't like for like, only the cases both ran are
        lines.append(f"different cases: {_cases_label(before)} -> {_cases_label(after)}")

    lines += ["", f"{'':<20}{'before':>10}{'after':>10}{'change':>10}"]
    for key in [*metrics, "errors", "median_ms", "output_tokens"]:
        was, now = before["summary"].get(key), after["summary"].get(key)
        fmt = "{:.3f}" if key in metrics else "{:.0f}"
        change = now - was if was is not None and now is not None else 0
        shown = [fmt.format(v) if v is not None else "n/a" for v in (was, now)]
        lines.append(f"{key:<20}{shown[0]:>10}{shown[1]:>10}{('+' if change > 0 else '') + fmt.format(change) if change else '':>10}")

    old_cases = {c["id"]: c for c in before["cases"]}
    new_cases = {c["id"]: c for c in after["cases"]}
    changed = []
    for case_id, case in new_cases.items():
        if case_id not in old_cases:
            changed.append(f"  {case_id}  new case")
            continue
        was, now = old_cases[case_id]["scores"], case["scores"]
        flips = [f"{m} {was[m]:.2f} -> {now[m]:.2f}" for m in metrics if m in was and m in now and was[m] != now[m]]
        if flips:
            changed.append(f"  {case_id}  {', '.join(flips)}")
    changed += [f"  {case_id}  removed" for case_id in old_cases if case_id not in new_cases]

    lines += ["", "changed cases" if changed else "no case changed its score", *changed]
    return "\n".join(lines)


def _label(run: dict) -> str:
    return f"{run['started_at'][:16].replace('T', ' ')} {run['client'].get('model', run['client'].get('provider'))}"


def _cases_label(run: dict) -> str:
    return f"tagged {run['tag']!r}" if run.get("tag") else "every case"


def _git_revision() -> str | None:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=EVALS_DIR).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True, cwd=EVALS_DIR).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    # a run from uncommitted changes can't be reproduced from the sha alone, so say so
    return f"{sha}-dirty" if dirty else sha
