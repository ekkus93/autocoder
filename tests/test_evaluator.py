import asyncio
from pathlib import Path

import pytest

from autocoder.budget import Budget, BudgetExhausted
from autocoder.evaluator import load_task, score, source_snapshot
from autocoder.execution import Sandbox
from autocoder.fixtures import Fixture
from autocoder.inference import InferenceError, infer
from autocoder.protocol import Limits

ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = ROOT / "benchmarks/v2"


@pytest.fixture(scope="module")
def sandbox():
    return Sandbox()


def test_candidate_cannot_read_actual_oracle_or_host_secret(sandbox, tmp_path):
    sentinel = tmp_path / "secret"
    sentinel.write_text("sensitive evaluator value")
    script = (
        "from pathlib import Path; "
        f"assert not Path({str(sentinel)!r}).exists(); "
        f"assert not Path({str(REGISTRATION / 'oracles.json')!r}).exists(); "
        "assert not Path('/proc/1/root/home/phil').exists(); print('confined')"
    )
    work = tmp_path / "work"
    work.mkdir()
    result = sandbox.execute(
        work,
        [
            "/usr/bin/python3",
            "-I",
            "-c",
            script,
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert result.stdout.strip() == "confined"


def test_timeout_and_output_limits(sandbox, tmp_path):
    result = sandbox.execute(
        tmp_path, ["/usr/bin/python3", "-I", "-c", "while True: pass"], timeout=0.1
    )
    assert result.status == "timeout"
    result = sandbox.execute(
        tmp_path,
        [
            "/usr/bin/python3",
            "-I",
            "-c",
            "print('a' * 100000)",
        ],
    )
    assert result.truncated
    assert len(result.stdout) == 65536


def test_snapshot_does_not_follow_symlinks(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "escape").symlink_to("/etc/passwd")
    with pytest.raises(ValueError, match="symlinks"):
        source_snapshot(source, tmp_path / "copy")


def test_python_base_fails_fixed_candidate_passes_and_tamper_disqualifies(sandbox):
    task, oracle = load_task(REGISTRATION, "py-clamp")
    with Fixture(task["files"]) as fixture:
        baseline = score(fixture, task, oracle, REGISTRATION, sandbox)
        assert baseline.status == "FAILED_VERIFICATION"
        (fixture.worktree / "bounds.py").write_text(
            "def clamp(value, lower, upper):\n"
            '    if lower > upper:\n        raise ValueError("range")\n'
            "    return max(lower, min(value, upper))\n"
        )
        candidate = score(fixture, task, oracle, REGISTRATION, sandbox)
        assert candidate.status == "VERIFIED_LOCAL", candidate
        (fixture.worktree / "tests/test_smoke.py").write_text("# weakened")
        assert score(fixture, task, oracle, REGISTRATION, sandbox).status == "TEST_TAMPERING"


@pytest.mark.parametrize("task_id", ["rs-clamp", "rs-divceil", "rs-ranges", "rs-config"])
def test_rust_baselines_compile_and_fail_oracle(sandbox, task_id):
    task, oracle = load_task(REGISTRATION, task_id)
    with Fixture(task["files"]) as fixture:
        observed = score(fixture, task, oracle, REGISTRATION, sandbox)
        assert observed.status == "FAILED_VERIFICATION", observed
        assert observed.passed < observed.total


def test_fixed_rust_and_cross_file_imports_pass(sandbox):
    task, oracle = load_task(REGISTRATION, "rs-config")
    with Fixture(task["files"]) as fixture:
        (fixture.worktree / "src/parser.rs").write_text(
            "pub fn parse_bool(value: &str) -> Option<bool> {\n"
            "  match value.trim().to_lowercase().as_str() {\n"
            '    "true" | "yes" | "1" => Some(true),\n'
            '    "false" | "no" | "0" => Some(false),\n'
            "    _ => None,\n  }\n}\n"
        )
        (fixture.worktree / "src/config.rs").write_text(
            "pub fn enabled(value: &str) -> Option<bool> { crate::parser::parse_bool(value) }\n"
        )
        assert score(fixture, task, oracle, REGISTRATION, sandbox).status == "VERIFIED_LOCAL"


def test_token_reservation_refuses_request_before_network(monkeypatch):
    import autocoder.inference

    called = []

    async def unexpected(*args):
        called.append(args)
        raise AssertionError("network called")

    monkeypatch.setattr(autocoder.inference, "post", unexpected)
    with pytest.raises(BudgetExhausted, match="request_tokens"):
        asyncio.run(
            infer(
                "http://localhost:11434",
                "model",
                [],
                Budget(Limits(request_tokens=1)),
                context=32768,
            )
        )
    assert not called


def test_failed_inference_is_not_replayed_and_reservation_is_retained(monkeypatch):
    import autocoder.inference

    called = []

    async def fail(*args):
        called.append(args)
        raise TimeoutError("ambiguous inference")

    monkeypatch.setattr(autocoder.inference, "post", fail)
    budget = Budget(Limits())
    with pytest.raises(BudgetExhausted, match="no source mutation"):
        asyncio.run(infer("http://localhost:11434", "model", [], budget, context=32768))
    assert len(called) == 1
    assert budget.snapshot().output_tokens == 512


def test_provider_usage_settlement_and_missing_usage_rejection(monkeypatch):
    import autocoder.inference

    async def success(*args):
        return {
            "message": {"content": "ok"},
            "done": True,
            "prompt_eval_count": 40,
            "eval_count": 10,
        }

    monkeypatch.setattr(autocoder.inference, "post", success)
    budget = Budget(Limits())
    asyncio.run(infer("http://localhost:11434", "model", [], budget, context=32768))
    assert budget.snapshot().request_tokens == 40
    assert budget.snapshot().output_tokens == 10

    async def missing(*args):
        return {"message": {"content": "ok"}}

    monkeypatch.setattr(autocoder.inference, "post", missing)
    with pytest.raises(InferenceError, match="usage"):
        asyncio.run(infer("http://localhost:11434", "model", [], Budget(Limits()), context=32768))
