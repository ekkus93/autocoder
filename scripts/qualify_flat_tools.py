"""Unscored interface check on a distinct quoted, multiline Python fixture."""

import argparse
import asyncio
from pathlib import Path

from autocoder.budget import Budget
from autocoder.evaluator import score
from autocoder.fixtures import Fixture
from autocoder.pilot_v5 import BoundedSandbox, implement, public_diagnostic
from autocoder.protocol import Limits, write_json
from autocoder.provenance import inventory


def main(output):
    root = Path(__file__).resolve().parents[1]
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "manifest.json", inventory(root, "http://127.0.0.1:11434", "qwen3.5:9b"))
    task = {
        "id": "engineering-qualification",
        "language": "python",
        "entry": "greeting.greet",
        "files": {"greeting.py": 'def greet(name):\n    return "Hello!"\n'},
        "protected": [],
        "prompt": 'Fix greeting.greet(name) to return "Hello, " + name + "!".',
    }
    public = {"cases": [{"args": ["Ada"], "expected": "Hello, Ada!"}]}
    budget = Budget(Limits())
    with Fixture(task["files"]) as fixture:
        sandbox = BoundedSandbox(budget)
        base = score(fixture, task, public, root / "benchmarks/v4", sandbox)
        asyncio.run(
            implement(
                fixture,
                task,
                public,
                root / "benchmarks/v4",
                "http://127.0.0.1:11434",
                budget,
                output,
                sandbox,
                public_diagnostic(base, public),
            )
        )
        candidate = score(fixture, task, public, root / "benchmarks/v4", sandbox)
        write_json(
            output / "result.json",
            {
                "status": candidate.status,
                "usage": budget.snapshot().model_dump(),
                "scope": "unscored quoted multiline edit qualification",
            },
        )
        print(candidate.status)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    main(parser.parse_args().output)
