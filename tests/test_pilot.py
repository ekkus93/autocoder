import json
from pathlib import Path

import pytest

from autocoder.evaluator import load_task
from autocoder.execution import Sandbox
from autocoder.fixtures import Fixture
from autocoder.pilot import Changes, apply_exact, run_task
from autocoder.protocol import Limits, digest

ROOT = Path(__file__).resolve().parents[1]


def test_pilot_rejects_protected_stale_and_nonunique_changes():
    task, _ = load_task(ROOT / "benchmarks/v3", "py-clamp")
    with Fixture(task["files"]) as fixture:
        with pytest.raises(ValueError, match="registered editable"):
            apply_exact(
                fixture,
                task,
                Changes(
                    edits=[
                        {
                            "path": "tests/test_smoke.py",
                            "old": "import bounds",
                            "new": "# weak",
                            "expected_sha256": digest(
                                task["files"]["tests/test_smoke.py"].encode()
                            ),
                        }
                    ]
                ),
            )
        with pytest.raises(ValueError, match="stale"):
            apply_exact(
                fixture,
                task,
                Changes(
                    edits=[
                        {
                            "path": "bounds.py",
                            "old": "return",
                            "new": "yield",
                            "expected_sha256": "0" * 64,
                        }
                    ]
                ),
            )
        assert not fixture.diff()


def test_pilot_real_oracle_verifies_mock_model_patch_and_fresh_messages(tmp_path, monkeypatch):
    import autocoder.pilot

    task, oracle = load_task(ROOT / "benchmarks/v3", "py-clamp")
    with Fixture(task["files"]) as fixture:
        base = fixture.base_sha
    prompts = []

    async def fake_infer(endpoint, model, messages, budget, **kwargs):
        prompts.append(messages)
        if len(prompts) == 1:
            content = {
                "base_sha": base,
                "paths": ["bounds.py"],
                "steps": ["Repair clamp"],
                "acceptance_checks": ["Correct bounds and reversed bounds"],
            }
        else:
            content = {
                "edits": [
                    {
                        "path": "bounds.py",
                        "old": task["files"]["bounds.py"],
                        "new": (
                            "def clamp(value, lower, upper):\n"
                            '    if lower > upper:\n        raise ValueError("range")\n'
                            "    return max(lower, min(value, upper))\n"
                        ),
                        "expected_sha256": digest(task["files"]["bounds.py"].encode()),
                    }
                ]
            }
        return {"truncated": False, "message": {"content": json.dumps(content)}}

    monkeypatch.setattr(autocoder.pilot, "infer", fake_infer)
    output = tmp_path / "run"
    output.mkdir()
    result = run_task(
        "minimal_loop", task, oracle, ROOT / "benchmarks/v3", "http://localhost", Limits(), output
    )
    assert result["status"] == "VERIFIED_LOCAL", result
    assert len(prompts) == 2
    assert all(len(messages) == 1 for messages in prompts)
    assert (output / "candidate-score.json").exists()
    assert "return max" in (output / "diff.patch").read_text()


def test_actual_sandbox_process_count_limit(tmp_path):
    script = """import subprocess,json
children=[]
try:
    for _ in range(90):
        children.append(subprocess.Popen(["/usr/bin/sleep", "1"]))
except OSError:
    pass
finally:
    for child in children:
        child.terminate()
    for child in children:
        child.wait()
print(json.dumps({"children":len(children)}))
"""
    result = Sandbox().execute(tmp_path, ["/usr/bin/python3", "-I", "-c", script])
    assert result.exit_code == 0, result.stderr
    assert 1 <= json.loads(result.stdout)["children"] < 64
