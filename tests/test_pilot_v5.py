import json
from pathlib import Path

from autocoder.budget import Budget
from autocoder.evaluator import load_task, score
from autocoder.fixtures import Fixture
from autocoder.pilot_v5 import BoundedSandbox, implement
from autocoder.protocol import Limits, digest

ROOT = Path(__file__).resolve().parents[1]


def test_flat_edit_tool_and_public_verification_do_not_expose_private_oracle(tmp_path, monkeypatch):
    import asyncio

    import autocoder.pilot_v5

    task, oracle = load_task(ROOT / "benchmarks/v4", "py-clamp")
    public = {"cases": [{"args": [8, -2, 6], "expected": 6}]}
    seen = []
    with Fixture(task["files"]) as fixture:

        async def fake(endpoint, model, messages, budget, **kwargs):
            seen.append(messages)
            if len(seen) == 1:
                body = {
                    "base_sha": fixture.base_sha,
                    "paths": ["bounds.py"],
                    "steps": ["Fix bounds"],
                    "acceptance_checks": ["Public regression"],
                }
                return {"truncated": False, "message": {"content": json.dumps(body)}}
            original = (fixture.worktree / "bounds.py").read_text()
            replacement = "def clamp(value, lower, upper):\n    return 6\n"
            return {
                "truncated": False,
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "apply_edit",
                                "arguments": {
                                    "path": "bounds.py",
                                    "old": original,
                                    "new": replacement,
                                    "expected_sha256": digest(original.encode()),
                                },
                            }
                        }
                    ]
                },
            }

        monkeypatch.setattr(autocoder.pilot_v5, "infer", fake)
        budget = Budget(Limits())
        asyncio.run(
            implement(
                fixture,
                task,
                public,
                ROOT / "benchmarks/v4",
                "http://local",
                budget,
                tmp_path,
                BoundedSandbox(budget),
                "public regression",
            )
        )
        assert len(seen) == 2
        assert "oracles.json" not in json.dumps(seen)
        # This constant would fail held-out checks; public success is not final acceptance.
        assert (fixture.worktree / "bounds.py").read_text().endswith("return 6\n")
        assert (
            score(fixture, task, oracle, ROOT / "benchmarks/v4", BoundedSandbox(budget)).status
            == "FAILED_VERIFICATION"
        )
