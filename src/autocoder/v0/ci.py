"""Operator-only GitHub Actions plans, single approved dispatches and exact-SHA evidence."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

from pydantic import Field, field_validator

from autocoder.v0.cli import journal_for, load_project
from autocoder.v0.journal import NeedsUser
from autocoder.v0.schema import Strict


class Policy(Strict):
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", max_length=200)
    workflow_id: int = Field(gt=0)
    ref: str = Field(min_length=1, max_length=200)
    inputs: dict[str, str] = Field(default_factory=dict, max_length=16)

    @field_validator("repository")
    @classmethod
    def valid_repository(cls, value):
        if any(part in {".", ".."} for part in value.split("/")):
            raise ValueError("Expected a GitHub owner/repository")
        return value

    @field_validator("ref")
    @classmethod
    def valid_ref(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]*", value) or ".." in value:
            raise ValueError("Expected an explicit branch or tag")
        return value

    @field_validator("inputs")
    @classmethod
    def bounded_inputs(cls, value):
        if len(json.dumps(value).encode()) > 8192:
            raise ValueError("Workflow inputs exceed 8KB")
        return value


class Gh:
    """No shell/extensions; bounded time/output; only GET retries, never POST retries."""

    def __init__(self, executable="/usr/bin/gh"):
        self.executable = executable

    def request(self, endpoint, *, payload=None):
        if not re.fullmatch(r"repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/[A-Za-z0-9_./%+-]+", endpoint):
            raise ValueError("Unsupported GitHub API path")
        argv = [self.executable, "api", "--hostname", "github.com", "--method"]
        argv += ["POST" if payload is not None else "GET", endpoint]
        if payload is not None:
            argv += ["--input", "-"]
        names = {"PATH", "HOME", "GH_CONFIG_DIR", "GH_TOKEN", "GITHUB_TOKEN", "SSL_CERT_FILE"}
        environment = {key: value for key, value in os.environ.items() if key in names}
        environment.update(
            GH_PROMPT_DISABLED="1", GH_PAGER="cat", GH_HOST="github.com", NO_COLOR="1"
        )
        attempts = 1 if payload is not None else 3
        for attempt in range(attempts):
            with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as input_file:
                if payload is not None:
                    input_file.write(json.dumps(payload).encode())
                    input_file.seek(0)
                with subprocess.Popen(
                    argv,
                    stdin=input_file,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    env=environment,
                ) as process:
                    deadline = time.monotonic() + 15
                    while process.poll() is None:
                        if (
                            os.fstat(output.fileno()).st_size > 262144
                            or time.monotonic() > deadline
                        ):
                            process.kill()
                            process.wait()
                            raise NeedsUser(
                                "GitHub request exceeded time/output bound; inspect remote state"
                            )
                        time.sleep(0.05)
                    output.seek(0)
                    raw = output.read(262145)
                    if len(raw) > 262144:
                        raise NeedsUser("GitHub response exceeds output bound")
                if process.returncode == 0:
                    return json.loads(raw) if raw.strip() else None
                transient = any(
                    word in raw for word in (b"HTTP 502", b"HTTP 503", b"HTTP 504", b"HTTP 429")
                )
                if not transient or attempt + 1 == attempts:
                    raise NeedsUser("GitHub request failed; no remote completion is inferred")
                time.sleep(0.2 * (attempt + 1))
        raise AssertionError("Unreachable retry state")


class Actions:
    def __init__(self, policy, journal, backend=None):
        self.policy, self.journal = policy, journal
        self.backend = backend or Gh()
        self.prefix = f"repos/{policy.repository}"

    def candidate(self):
        rows = self.journal.read()
        last = max((i for i, row in enumerate(rows) if row["kind"] == "FINAL"), default=-1)
        if last < 0 or any(not row["kind"].startswith("CI_") for row in rows[last + 1 :]):
            raise NeedsUser("Task has unfinished controller operations")
        result = task_result_from_rows(self.journal)
        if result["status"] not in {"VERIFIED_LOCAL", "INTEGRATED_BY_USER"}:
            raise NeedsUser("CI operations require a locally verified task commit")
        sha = result.get("task_commit", "")
        if not re.fullmatch("[a-f0-9]{40}", sha):
            raise NeedsUser("Missing exact task commit")
        return sha

    def resolve(self, sha):
        value = self.backend.request(f"{self.prefix}/commits/{quote(self.policy.ref, safe='')}")
        if not isinstance(value, dict) or value.get("sha") != sha:
            raise NeedsUser("Remote ref differs from the exact task commit; no push is performed")

    def plan(self):
        sha = self.candidate()
        self.resolve(sha)
        value = {"policy": self.policy.model_dump(), "task_id": self.journal.task_id, "sha": sha}
        key = self.journal.artifact(value)
        self.journal.emit("CI_PLAN", evidence_ref=key)
        return {
            "plan": key,
            **value,
            "note": "Review workflow and inputs before approving dispatch",
        }

    def dispatch(self, key, approval):
        if approval != key:
            raise NeedsUser("Explicit approval must match the concrete plan's SHA-256")
        rows = self.journal.read()
        if not any(row["kind"] == "CI_PLAN" and row["evidence_ref"] == key for row in rows):
            raise NeedsUser("Unknown CI plan")
        if any(row["kind"] == "CI_DISPATCH_INTENT" and row["evidence_ref"] == key for row in rows):
            raise NeedsUser("Dispatch already attempted; inspect remote state instead of retrying")
        plan = self.journal.load(key)
        if plan != {
            "policy": self.policy.model_dump(),
            "task_id": self.journal.task_id,
            "sha": self.candidate(),
        }:
            raise NeedsUser("Task or CI policy differs from reviewed plan")
        self.resolve(plan["sha"])
        self.journal.emit("CI_DISPATCH_INTENT", evidence_ref=key)
        try:
            self.backend.request(
                f"{self.prefix}/actions/workflows/{self.policy.workflow_id}/dispatches",
                payload={"ref": self.policy.ref, "inputs": self.policy.inputs},
            )
        except Exception:
            self.journal.emit("CI_DISPATCH_UNKNOWN", evidence_ref=key)
            raise
        self.journal.emit("CI_DISPATCH_SENT", evidence_ref=key)
        return {
            "status": "DISPATCH_SENT",
            "plan": key,
            "remote_ci": "not_run",
            "note": "Inspect run ID and head SHA; the ref can move during dispatch",
        }

    def inspect(self, run_id):
        if type(run_id) is not int or run_id < 1:
            raise ValueError("Expected a positive run ID")
        sha = self.candidate()
        value = self.backend.request(f"{self.prefix}/actions/runs/{run_id}")
        if (
            not isinstance(value, dict)
            or value.get("id") != run_id
            or value.get("head_sha") != sha
            or value.get("workflow_id") != self.policy.workflow_id
            or value.get("repository", {}).get("full_name", "").lower()
            != self.policy.repository.lower()
            or value.get("event") != "workflow_dispatch"
        ):
            raise NeedsUser("Run identity/workflow/event/SHA differs from configured task")
        status, conclusion = value.get("status"), value.get("conclusion")
        acceptance = (
            "not_run" if status != "completed" else ("pass" if conclusion == "success" else "fail")
        )
        record = {
            "run_id": run_id,
            "sha": sha,
            "repository": self.policy.repository,
            "workflow_id": self.policy.workflow_id,
            "status": status,
            "conclusion": conclusion,
            "remote_ci": acceptance,
        }
        key = self.journal.artifact(record)
        self.journal.emit("CI_INSPECTION", evidence_ref=key, status=acceptance)
        # Task reporting expects FINAL last; preserve its other local/human acceptance fields.
        result = task_result_from_rows(self.journal)
        result["acceptance"]["remote_ci"] = acceptance
        result["remote_ci_ref"] = key
        self.journal.emit(
            "FINAL", status=result["status"], evidence_ref=self.journal.artifact(result)
        )
        return record


def task_result_from_rows(journal):
    finals = [row for row in journal.read() if row["kind"] == "FINAL"]
    if not finals:
        raise NeedsUser("Missing final task report")
    return journal.load(finals[-1]["evidence_ref"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan")
    dispatch = commands.add_parser("dispatch")
    dispatch.add_argument("--plan", required=True)
    dispatch.add_argument("--approve", required=True, help="Exact reviewed plan SHA-256")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("run_id", type=int)
    args = parser.parse_args(argv)
    try:
        if args.policy.stat().st_size > 32768:
            raise ValueError("CI policy exceeds 32KB")
        policy = Policy.model_validate_json(args.policy.read_bytes())
        journal = journal_for(load_project(args.config), args.task_id)
        with journal.lock():
            actions = Actions(policy, journal)
            # CI records must not make a completed task appear RUNNING to existing readers.
            actions.candidate()
            original = task_result_from_rows(journal)
            try:
                if args.command == "plan":
                    result = actions.plan()
                elif args.command == "dispatch":
                    result = actions.dispatch(args.plan, args.approve)
                else:
                    result = actions.inspect(args.run_id)
            finally:
                if journal.read()[-1]["kind"] != "FINAL":
                    journal.emit(
                        "FINAL", status=original["status"], evidence_ref=journal.artifact(original)
                    )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError, NeedsUser) as error:
        print(json.dumps({"status": "NEEDS_USER", "detail": str(error)[:1024]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
