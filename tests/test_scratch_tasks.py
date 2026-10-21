import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "make_scratch_tasks.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=120
    )


def test_generator_verifies_tasks_and_writes_projects(tmp_path):
    output = tmp_path / "tasks"
    done = run("--output", str(output), "--model", "example:1b")
    assert done.returncode == 0, done.stderr
    for name in ("paginate", "calc", "intervals", "report"):
        project = output / name
        assert (project / "task.txt").is_file()
        assert (project / "tests" / "regression.py").is_file()
        assert (project / ".git").is_dir()
        policy = json.loads((output / f"{name}.example-1b.json").read_text())
        assert policy["repository"] == str(project)
        assert policy["model"] == "example:1b"
        assert policy["editable_paths"]
        assert policy["state_dir"] == str(output / "state")


def test_generator_refuses_existing_output(tmp_path):
    done = run("--output", str(tmp_path))
    assert done.returncode != 0
    assert "already exists" in done.stderr
