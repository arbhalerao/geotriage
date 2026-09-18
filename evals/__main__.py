"""
python -m evals list
python -m evals run SUITE [--tag TAG] [--no-cache]
python -m evals compare SUITE [BEFORE.json AFTER.json]
"""

import argparse
import json
import sys
from pathlib import Path

from evals.runner import CACHE_DIR, compare, load_cases, meets, run_suite, save_run, saved_runs
from evals.suites import SUITES


def _suite(name: str):
    if name not in SUITES:
        sys.exit(f"no suite named {name!r}, there is: {', '.join(sorted(SUITES))}")
    return SUITES[name]


def cmd_list(_args) -> int:
    for name, suite in sorted(SUITES.items()):
        print(f"{name:<24}{suite.description}")
    return 0


def cmd_run(args) -> int:
    from llm import CachedClient, FakeClient, default_client

    suite = _suite(args.suite)
    cases = load_cases(suite.dataset_name, tag=args.tag)
    if not cases:
        sys.exit(f"no cases in {suite.name} tagged {args.tag!r}")

    if not suite.uses_model:
        client = FakeClient([])
    else:
        client = default_client()
        if not args.no_cache:
            client = CachedClient(client, CACHE_DIR / suite.name)

    print(f"{suite.name}: {len(cases)} case(s) against {client.identity.get('model', 'no model')}")
    run = run_suite(suite, cases, client)
    run["tag"] = args.tag
    path = save_run(run)

    print()
    targets = suite.targets or {}
    for metric in suite.metrics:
        value = run["summary"][metric]
        line = f"{metric:<20}{'n/a' if value is None else f'{value:.3f}':>8}"
        if metric in targets:
            op, bar = targets[metric]
            line += f"   target {op} {bar:.2f}  {'met' if meets(value, targets[metric]) else 'missed'}"
        print(line)
    print(f"{'errors':<20}{run['summary']['errors']}")
    print(f"{'median':<20}{run['summary']['median_ms'] / 1000:.1f} s")
    print(f"\nsaved {path}")
    return 0


def cmd_compare(args) -> int:
    suite = _suite(args.suite)
    if args.runs:
        if len(args.runs) != 2:
            sys.exit("name two runs to compare, or none for the last two")
        before, after = (Path(p) for p in args.runs)
    else:
        runs = saved_runs(suite.name)
        if len(runs) < 2:
            sys.exit(f"{suite.name} has {len(runs)} saved run(s), comparing needs two")
        before, after = runs[-2], runs[-1]

    print(compare(json.loads(before.read_text()), json.loads(after.read_text()), suite.metrics))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m evals")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list").set_defaults(handler=cmd_list)

    run = commands.add_parser("run")
    run.add_argument("suite")
    run.add_argument("--tag", help="only the cases carrying this tag, e.g. quick")
    run.add_argument("--no-cache", action="store_true", help="ask the model again even for unchanged cases")
    run.set_defaults(handler=cmd_run)

    comp = commands.add_parser("compare")
    comp.add_argument("suite")
    comp.add_argument("runs", nargs="*", help="two saved result files, oldest first")
    comp.set_defaults(handler=cmd_compare)

    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
