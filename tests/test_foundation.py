import json
import shutil
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from autocoder.budget import Budget, BudgetExhausted
from autocoder.cli import main
from autocoder.fixtures import Fixture
from autocoder.protocol import Limits, digest, verify_protocol
from autocoder.sandbox import argv, probe

ROOT = Path(__file__).resolve().parents[1]


def test_version(capsys):
    with pytest.raises(SystemExit) as error:
        main(["--version"])
    assert error.value.code == 0
    assert capsys.readouterr().out.strip() == "0.1.0"


def test_fixture_repeats_without_contamination(tmp_path):
    files = {"module.py": "x = 1\n", "tests/test_module.py": "# protected\n"}
    with Fixture(files) as first:
        sha = first.base_sha
        location = first.root
        (first.worktree / "module.py").write_text("x = 2\n")
        assert "+x = 2" in first.diff()
        assert (first.repository / "module.py").read_text() == "x = 1\n"
        (first.worktree / "tests/test_module.py").unlink()
        assert first.protected_changes(["tests/test_module.py"]) == ["tests/test_module.py"]
    assert not location.exists()
    with Fixture(files) as second:
        assert second.base_sha == sha
        assert not second.diff()


@pytest.mark.parametrize("name", ["../escape", "/absolute", ".git/config", "a/../../escape"])
def test_fixture_rejects_unsafe_names(name):
    with pytest.raises(ValueError, match="Unsafe fixture path"):
        Fixture({name: "bad"})


@pytest.mark.parametrize("name", ["request_tokens", "output_tokens", "tool_calls", "repairs"])
def test_budget_enforces_each_counter_atomically(name):
    limits = Limits()
    budget = Budget(limits)
    budget.consume(**{name: getattr(limits, name)})
    with pytest.raises(BudgetExhausted, match=name):
        budget.consume(**{name: 1})
    assert getattr(budget.snapshot(), name) == getattr(limits, name)


def test_budget_enforces_elapsed_time(monkeypatch):
    budget = Budget(Limits(wall_seconds=1))
    monkeypatch.setattr(time, "monotonic", lambda: budget.started + 2)
    with pytest.raises(BudgetExhausted, match="wall_seconds"):
        budget.consume(tool_calls=1)


def test_invalid_limits_are_rejected():
    with pytest.raises(ValidationError):
        Limits(tool_calls=-1)
    with pytest.raises(ValueError):
        Budget(Limits()).consume(tool_calls=-1)


def test_registration_rejects_silent_changes(tmp_path):
    registered = tmp_path / "v1"
    shutil.copytree(ROOT / "benchmarks/v1", registered)
    checksum = digest((registered / "freeze.json").read_bytes())
    assert verify_protocol(registered, checksum) == checksum
    with pytest.raises(ValueError, match="digest differs"):
        verify_protocol(registered, "0" * 64)
    (registered / "protocol.json").write_text("{}\n")
    with pytest.raises(ValueError, match="Changed benchmark asset"):
        verify_protocol(registered, checksum)


def test_registration_rejects_added_file(tmp_path):
    registered = tmp_path / "v1"
    shutil.copytree(ROOT / "benchmarks/v1", registered)
    (registered / "unregistered.json").write_text("{}")
    with pytest.raises(ValueError, match="inventory changed"):
        verify_protocol(registered)


def test_smoke_writes_valid_records_before_rejecting_overwrite(tmp_path, monkeypatch):
    import autocoder.cli

    monkeypatch.setattr(autocoder.cli, "inventory", lambda *args: {"offline_test": True})
    output = tmp_path / "evidence"
    arguments = ["--repository", str(ROOT), "smoke", "--output", str(output)]
    assert main(arguments) == 0
    result = json.loads((output / "result.json").read_text())
    assert result["status"] == "VERIFIED_LOCAL"
    assert len(result["base_sha"]) == 40
    assert result["manifest_sha256"] == digest((output / "manifest.json").read_bytes())
    assert json.loads((output / "events.jsonl").read_text()) == result
    assert main(arguments) == 2


def test_sandbox_failure_does_not_execute_on_host(monkeypatch):
    import autocoder.sandbox

    calls = []

    def unavailable(arguments, **kwargs):
        calls.append(arguments)
        raise FileNotFoundError("bubblewrap unavailable")

    monkeypatch.setattr(autocoder.sandbox.subprocess, "run", unavailable)
    assert probe()["status"] == "BLOCKED_ENVIRONMENT"
    assert len(calls) == 1
    assert calls[0][0] == "bwrap"


def test_sandbox_policy_has_no_home_or_shared_network(tmp_path):
    arguments = argv(tmp_path, ["/usr/bin/true"])
    assert "--unshare-all" in arguments
    assert "--clearenv" in arguments
    assert "--share-net" not in arguments
    assert "/home" not in arguments
    assert arguments.count("--bind") == 1
