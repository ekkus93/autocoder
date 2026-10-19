"""External oracle comparison: candidate processes never receive expected answers."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from autocoder.execution import Sandbox
from autocoder.fixtures import Fixture, safe_relative
from autocoder.protocol import Record


class Score(Record):
    status: str
    passed: int
    total: int
    tampered: list[str]
    observations: list[dict]


def source_snapshot(source: Path, destination: Path) -> None:
    """Copy bounded plain files; reject symlinks and special files before evaluation."""
    total = 0
    for directory, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = [name for name in dirs if name not in {".git", "__pycache__", "target"}]
        for name in [*dirs, *files]:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError("Candidate symlinks are forbidden in evaluator snapshots")
        for name in files:
            path = Path(directory) / name
            if name == ".git":
                continue
            if not path.is_file():
                raise ValueError("Only plain candidate files may be evaluated")
            size = path.stat().st_size
            total += size
            if size > 1_000_000 or total > 4_000_000:
                raise ValueError("Candidate snapshot exceeds the registered size limit")
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target, follow_symlinks=False)


def rust_toolchain() -> Path:
    compiler = subprocess.run(
        ["rustup", "which", "rustc"],
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    ).stdout.strip()
    return Path(compiler).resolve().parent.parent


def score(
    fixture: Fixture, task: dict, oracle: dict, registration: Path, sandbox: Sandbox
) -> Score:
    tampered = fixture.protected_changes(task["protected"])
    if tampered:
        return Score(
            status="TEST_TAMPERING",
            passed=0,
            total=len(oracle["cases"]),
            tampered=tampered,
            observations=[],
        )
    observations = []
    with tempfile.TemporaryDirectory(prefix="autocoder-evaluator-") as temporary:
        snapshot = Path(temporary)
        source_snapshot(fixture.worktree, snapshot)
        language = task["language"]
        toolchain = None
        if language == "rust":
            toolchain = rust_toolchain()
            # The driver contains marshalling only; it has no expected values or oracle checks.
            driver = (registration / "drivers" / f"{task['id']}.rs").read_text()
            (snapshot / "driver.rs").write_text(driver)
            compiled = sandbox.execute(
                snapshot,
                [
                    "/toolchain/bin/rustc",
                    "--edition=2021",
                    "-C",
                    f"linker={Path('/usr/bin/cc').resolve()}",
                    "driver.rs",
                    "-o",
                    "candidate",
                ],
                toolchain=toolchain,
            )
            if compiled.exit_code != 0 or compiled.status != "finished":
                return Score(
                    status="COMPILE_FAILURE",
                    passed=0,
                    total=len(oracle["cases"]),
                    tampered=[],
                    observations=[compiled.model_dump()],
                )
        for case in oracle["cases"]:
            if language == "python":
                driver = (registration / "drivers/python.py").read_text()
                command = ["/usr/bin/python3", "-I", "-c", driver, case.get("entry", task["entry"])]
                input_text = json.dumps(case["args"])
            else:
                command = ["/work/candidate", *[str(value) for value in case["args"]]]
                input_text = ""
            execution = sandbox.execute(
                snapshot, command, input_text=input_text, toolchain=toolchain
            )
            observed = None
            if execution.exit_code == 0 and not execution.truncated:
                try:
                    observed = json.loads(execution.stdout)
                except json.JSONDecodeError:
                    pass
            expected = (
                {"exception": case["exception"]}
                if "exception" in case
                else {"value": case["expected"]}
            )
            if language == "rust" and "exception" in case:
                passed = execution.status == "finished" and execution.exit_code == 101
            else:
                # Bool and int must remain distinct despite Python's True == 1.
                passed = json.dumps(observed, sort_keys=True) == json.dumps(
                    expected, sort_keys=True
                )
                passed = passed and execution.status == "finished" and execution.exit_code == 0
            observations.append({"pass": passed, "execution": execution.model_dump()})
    passed = sum(item["pass"] for item in observations)
    return Score(
        status="VERIFIED_LOCAL" if passed == len(oracle["cases"]) else "FAILED_VERIFICATION",
        passed=passed,
        total=len(oracle["cases"]),
        tampered=[],
        observations=observations,
    )


def load_task(registration: Path, task_id: str) -> tuple[dict, dict]:
    safe_relative(task_id)
    tasks = json.loads((registration / "tasks.json").read_text())
    task = next((task for task in tasks if task["id"] == task_id), None)
    if task is None:
        raise ValueError(f"Task is not registered: {task_id}")
    oracle = json.loads((registration / "oracles.json").read_text())[task_id]
    return task, oracle
