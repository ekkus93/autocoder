import json

import pytest

from autocoder.execution import Sandbox, SandboxUnavailable


def test_hostile_install_hook_is_confined(tmp_path):
    secret = tmp_path / "secret"
    secret.write_text("private")
    outside = tmp_path / "outside"
    work = tmp_path / "candidate"
    work.mkdir()
    hook = f"""
from pathlib import Path
import json, socket
results = {{}}
try:
    Path({str(secret)!r}).read_text()
    results["read_blocked"] = False
except OSError:
    results["read_blocked"] = True
try:
    Path({str(outside)!r}).write_text("escaped")
    results["write_blocked"] = False
except OSError:
    results["write_blocked"] = True
try:
    socket.create_connection(("127.0.0.1", 11434), timeout=1)
    results["network_blocked"] = False
except OSError:
    results["network_blocked"] = True
Path("installed-marker").write_text("task-local output")
print(json.dumps(results))
"""
    (work / "setup.py").write_text(hook)
    execution = Sandbox().execute(work, ["/usr/bin/python3", "-I", "setup.py"])
    assert execution.exit_code == 0, execution.stderr
    assert json.loads(execution.stdout) == {
        "read_blocked": True,
        "write_blocked": True,
        "network_blocked": True,
    }
    assert not outside.exists()
    assert secret.read_text() == "private"
    assert (work / "installed-marker").read_text() == "task-local output"


def test_unavailable_confinement_refuses_before_any_execution(monkeypatch):
    import autocoder.execution

    monkeypatch.setattr(autocoder.execution, "probe", lambda: {"status": "BLOCKED_ENVIRONMENT"})
    with pytest.raises(SandboxUnavailable, match="host execution is forbidden"):
        Sandbox()
