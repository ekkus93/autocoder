import asyncio
import json

import pytest

from autocoder.budget import Budget
from autocoder.handoff_probe import decode, repair_plan
from autocoder.protocol import Limits

BASE = "a" * 40
PLAN = {"base_sha": BASE, "paths": ["file.py"], "steps": ["Repair"], "acceptance_checks": ["unit"]}


def test_handoffs_reject_stale_revision_unknown_paths_and_missing_fields():
    assert decode(json.dumps(PLAN), BASE, {"file.py"}).base_sha == BASE
    with pytest.raises(ValueError, match="Stale"):
        decode(json.dumps(PLAN), "b" * 40, {"file.py"})
    with pytest.raises(ValueError, match="unknown"):
        decode(json.dumps(PLAN), BASE, {"other.py"})
    with pytest.raises(ValueError):
        decode('{"steps": []}', BASE, {"file.py"})


def test_malformed_handoff_cannot_enter_state_after_bounded_recovery(monkeypatch):
    import autocoder.handoff_probe

    calls = []

    async def invalid(*args, **kwargs):
        calls.append(args)
        return {"message": {"content": "not json"}}

    monkeypatch.setattr(autocoder.handoff_probe, "infer", invalid)
    budget = Budget(Limits())
    with pytest.raises(ValueError, match="bounded recovery"):
        asyncio.run(
            repair_plan(
                "http://localhost",
                "model",
                "invalid",
                {
                    "base_sha": BASE,
                    "files": {"file.py": "source"},
                },
                budget,
            )
        )
    assert len(calls) == 1
    assert budget.snapshot().repairs == 1
