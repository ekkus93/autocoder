"""Offline named checks against isolated snapshots; independent terminal oracles."""

import json
import tempfile
from pathlib import Path

from autocoder.evaluator import rust_toolchain
from autocoder.protocol import digest, utc_now
from autocoder.v0.isolation import TaskSandbox
from autocoder.v0.journal import NeedsUser
from autocoder.v0.workspace import safe_file

PYTHON_DRIVER = """import importlib, json, sys
sys.path.insert(0, "/work")
sys.path.insert(0, "/work/src")
sys.path.insert(0, "/toolchain/lib/python3.12/site-packages")
sys.path.insert(0, "/toolchain")
module, function = sys.argv[1].rsplit(".", 1)
try:
    value = getattr(importlib.import_module(module), function)(*json.loads(sys.argv[2]))
    print(json.dumps({"value": value}, sort_keys=True))
except Exception as error:
    print(json.dumps({"exception": type(error).__name__}))
"""


def directory_digest(root):
    root = root.resolve()
    rows = []
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            # Runtime interpreter links to system Python are expected; do not traverse them.
            target = path.resolve()
            if not target.is_relative_to(root) and not target.is_relative_to(Path("/usr")):
                raise NeedsUser("Runtime symlink leaves approved runtime/system files")
            rows.append((str(path.relative_to(root)), "link", str(path.readlink())))
        elif path.is_file():
            total += path.stat().st_size
            if total > 2_000_000_000:
                raise NeedsUser("Runtime exceeds reviewed size cap")
            rows.append((str(path.relative_to(root)), digest(path.read_bytes())))
    return digest(json.dumps(rows, sort_keys=True).encode())


class VerificationRunner:
    def __init__(self, workspace, budget, sandbox=None):
        self.workspace, self.journal, self.budget = workspace, workspace.journal, budget
        self.sandbox = sandbox or TaskSandbox()
        self.dependencies = None
        from autocoder.v0.dependencies import prepare

        self.dependencies = prepare(self)

    def cancelled(self):
        if (self.journal.directory / "cancel").exists():
            import asyncio

            raise asyncio.CancelledError

    def execute(self, root, command, *, runtime=None, timeout=30, input_text=""):
        self.cancelled()
        if self.dependencies:
            ready = [r for r in self.journal.read() if r["kind"] == "DEPENDENCIES_READY"]
            if directory_digest(self.dependencies) != ready[-1]["data"]["sha256"]:
                raise NeedsUser("Prepared dependencies changed before check")
        result = self.sandbox.execute(
            root,
            command,
            toolchain=runtime,
            timeout=min(timeout, self.budget.remaining_seconds),
            input_text=input_text,
            readonly={"/deps": self.dependencies} if self.dependencies else None,
        )
        self.cancelled()
        _ = self.budget.remaining_seconds
        return result

    def copy(self, destination):
        self.workspace.assert_expected()
        values = self.workspace.fingerprint()
        for name in values:
            _, data = safe_file(self.workspace.root, name, maximum=8_000_000, text=False)
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod((self.workspace.root / name).stat().st_mode & 0o777)
        return digest(json.dumps(values, sort_keys=True).encode())

    def run(self, check, label):
        started = utc_now()
        runtime = None
        if check.runtime is not None:
            if not check.runtime_sha256 or directory_digest(check.runtime) != check.runtime_sha256:
                raise NeedsUser("Check runtime differs from explicitly reviewed content digest")
            runtime = check.runtime.resolve()
        elif check.language == "rust":
            runtime = rust_toolchain()
        with tempfile.TemporaryDirectory(prefix="autocoder-check-") as temporary:
            root = Path(temporary)
            tree = self.copy(root)
            result = self.execute(root, check.command, runtime=runtime, timeout=check.timeout)
            integrity = self.integrity(root)
        self.workspace.assert_expected()
        record = {
            "name": check.name,
            "kind": check.kind,
            "label": label,
            "started": started,
            "finished": utc_now(),
            "source_tree_sha256": tree,
            "base_sha": self.workspace.base_sha,
            "command": check.command,
            "runtime_sha256": check.runtime_sha256,
            "execution": result.model_dump(),
            "integrity_changes": integrity,
        }
        key = self.journal.artifact(record)
        passed = (
            result.status == "finished"
            and result.exit_code == 0
            and not result.truncated
            and not integrity
        )
        self.journal.emit(
            "CHECK",
            evidence_ref=key,
            status="pass" if passed else "fail",
            data={
                "name": check.name,
                "kind": check.kind,
                "label": label,
                "source_tree_sha256": tree,
            },
        )
        return record

    def integrity(self, root):
        changed = []
        for name, expected in self.workspace.expected().items():
            try:
                _, data = safe_file(root, name, maximum=8_000_000, text=False)
                if digest(data) != expected:
                    changed.append(name)
            except (OSError, NeedsUser):
                changed.append(name)
        return changed

    def all(self, label):
        return [self.run(check, label) for check in self.workspace.project.checks]

    def held_out(self):
        """Never return expected values/diagnostics to the model or public repair loop."""
        records = []
        for oracle in self.workspace.project.oracles:
            raw = oracle.cases_file.read_bytes()
            if len(raw) > 1_000_000:
                raise NeedsUser("Oracle exceeds size cap")
            cases = json.loads(raw)
            if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
                raise NeedsUser("Expected one to 100 independent oracle cases")
            with tempfile.TemporaryDirectory(prefix="autocoder-oracle-") as temporary:
                root = Path(temporary)
                tree = self.copy(root)
                runtime = None
                if oracle.language == "python":
                    if oracle.runtime:
                        if directory_digest(oracle.runtime) != oracle.runtime_sha256:
                            raise NeedsUser("Private checker runtime changed")
                        runtime = oracle.runtime.resolve()
                    command = ["/usr/bin/python3", "-I", "-c", PYTHON_DRIVER, oracle.entry]
                else:
                    if oracle.driver is None:
                        raise NeedsUser(
                            "Rust oracle needs an independently reviewed argument-only driver"
                        )
                    driver = oracle.driver.read_bytes()
                    (root / "autocoder-driver.rs").write_bytes(driver)
                    runtime = rust_toolchain()
                    compiled = self.execute(
                        root,
                        [
                            "/toolchain/bin/rustc",
                            "--edition=2021",
                            "-C",
                            "linker=" + str(Path("/usr/bin/cc").resolve()),
                            "autocoder-driver.rs",
                            "-o",
                            "oracle-program",
                        ],
                        runtime=runtime,
                    )
                    if compiled.exit_code != 0:
                        records.append(
                            {
                                "pass": False,
                                "source_tree_sha256": tree,
                                "compile": compiled.model_dump(),
                            }
                        )
                        continue
                    command = ["/work/oracle-program"]
                for case in cases:
                    args = (
                        [json.dumps(case["args"])]
                        if oracle.language == "python"
                        else [str(arg) for arg in case["args"]]
                    )
                    observed = self.execute(root, command + args, runtime=runtime)
                    try:
                        answer = json.loads(observed.stdout)
                        expected = (
                            {"exception": case["exception"]}
                            if "exception" in case
                            else {"value": case["expected"]}
                        )
                        correct = (
                            observed.exit_code == 0
                            and not observed.truncated
                            and json.dumps(answer, sort_keys=True)
                            == json.dumps(expected, sort_keys=True)
                        )
                        if oracle.language == "rust" and case.get("exception") == "panic":
                            correct = observed.exit_code != 0 and "panicked" in observed.stderr
                    except (ValueError, KeyError):
                        correct = (
                            oracle.language == "rust"
                            and case.get("exception") == "panic"
                            and observed.exit_code != 0
                            and "panicked" in observed.stderr
                        )
                    correct = correct and not self.integrity(root)
                    records.append(
                        {
                            "pass": correct,
                            "execution": observed.model_dump(),
                            "source_tree_sha256": tree,
                            "oracle_sha256": digest(raw),
                        }
                    )
        ref = self.journal.artifact(records)
        self.journal.emit(
            "HELD_OUT",
            evidence_ref=ref,
            status=("pass" if all(row["pass"] for row in records) else "fail")
            if records
            else "not_run",
            data={"cases": len(records)},
        )
        return records


def passed(records):
    return all(
        row["execution"]["status"] == "finished"
        and row["execution"]["exit_code"] == 0
        and not row["execution"]["truncated"]
        and not row.get("integrity_changes")
        for row in records
    )


def diagnostic(records):
    failing = next((row for row in records if not passed([row])), None)
    if not failing:
        return ""
    execution = failing["execution"]
    if failing.get("integrity_changes"):
        return "Verification changed tracked inputs: " + ", ".join(failing["integrity_changes"][:5])
    return (
        f"Check {failing['name']} exited {execution['exit_code']}: "
        + execution["stderr"][:2048]
        + execution["stdout"][:2048]
    )[:4096]
