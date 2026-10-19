"""Headless Stage 0 commands. No candidate execution before sandbox qualification."""

import argparse
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from autocoder import __version__
from autocoder.budget import Budget, BudgetExhausted
from autocoder.evaluator import load_task, score, source_snapshot
from autocoder.execution import Sandbox
from autocoder.experiments import run_micro, verify_engines
from autocoder.fixtures import Fixture, git
from autocoder.protocol import Limits, Result, utc_now, verify_protocol, write_json
from autocoder.provenance import inventory, request_json
from autocoder.sandbox import probe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3.5:9b")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("smoke", "inventory", "sandbox-probe"):
        command = subparsers.add_parser(name)
        command.add_argument("--output", type=Path, required=True, help="New evidence directory")
    for name in ("micro", "score-fixture"):
        command = subparsers.add_parser(name)
        command.add_argument("--registration", default="v2", choices=["v2"])
        command.add_argument("--expected-sha256", required=True)
        command.add_argument("--output", type=Path, required=True)
        if name == "micro":
            command.add_argument("--family", choices=["runtime", "tools"], required=True)
        else:
            command.add_argument("--task", required=True)
            command.add_argument("--candidate-directory", type=Path)
    verify = subparsers.add_parser("verify-protocol")
    verify.add_argument("--expected-sha256", required=True)
    arguments = parser.parse_args(argv)
    repository = arguments.repository.resolve()
    registration = repository / "benchmarks/v1"
    try:
        if arguments.command == "verify-protocol":
            checksum = verify_protocol(registration, arguments.expected_sha256)
            print(json.dumps({"status": "verified", "protocol_sha256": checksum}))
            return 0
        if arguments.command in {"micro", "score-fixture"}:
            return run_registered(arguments, repository)
        return run(arguments, repository, registration)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "BLOCKED_ENVIRONMENT", "detail": str(error)}), file=sys.stderr)
        return 2


def run(arguments: argparse.Namespace, repository: Path, registration: Path) -> int:
    protocol_hash = verify_protocol(registration)
    protocol = json.loads((registration / "protocol.json").read_text())
    limits = Limits(**protocol["limits"])
    # Creation is exclusive: do not mix independent runs or overwrite prior evidence.
    output = arguments.output.resolve()
    if output.is_relative_to(repository):
        raise ValueError("Store raw run evidence outside the tracked repository")
    output.mkdir(parents=True, exist_ok=False)
    manifest_hash = write_json(
        output / "manifest.json", inventory(repository, arguments.endpoint, arguments.model)
    )
    if arguments.command == "inventory":
        print(json.dumps({"manifest_sha256": manifest_hash, "output": str(output)}))
        return 0
    budget = Budget(limits)
    base_sha = None
    checks = {}
    status = "FAILED_VERIFICATION"
    detail = ""
    try:
        if arguments.command == "sandbox-probe":
            observed = probe()
            write_json(output / "sandbox.json", observed)
            status = observed["status"]
            checks = {
                name: "pass" if value else "fail"
                for name, value in observed.get("checks", {}).items()
            }
            detail = observed.get("stderr", observed.get("error_type", "Sandbox probe completed"))
        else:
            budget.consume(tool_calls=1)
            # Smoke is a trusted integrity experiment, not generated code or a scored task.
            with Fixture({"hello.py": 'MESSAGE = "hello"\n'}) as fixture:
                base_sha = fixture.base_sha
                clean = not git(fixture.worktree, "status", "--porcelain")
                original = (fixture.repository / "hello.py").read_bytes()
                candidate = (fixture.worktree / "hello.py").read_bytes()
                checks = {
                    "clean_worktree": "pass" if clean else "fail",
                    "identical_source": "pass" if original == candidate else "fail",
                    "pinned_revision": "pass"
                    if git(fixture.worktree, "rev-parse", "HEAD") == base_sha
                    else "fail",
                }
            _ = budget.remaining_seconds
            status = "VERIFIED_LOCAL" if set(checks.values()) == {"pass"} else status
            detail = "Fixture integrity only; inference, candidate tests, CI and hardware not run."
    except (OSError, subprocess.SubprocessError) as error:
        status = "BLOCKED_ENVIRONMENT"
        detail = f"Fixture operation failed: {type(error).__name__}"
    except BudgetExhausted as error:
        status = "BUDGET_EXHAUSTED"
        detail = str(error)
    result = Result(
        run_id=str(uuid.uuid4()),
        utc_time=utc_now(),
        experiment=arguments.command,
        status=status,
        base_sha=base_sha,
        protocol_sha256=protocol_hash,
        manifest_sha256=manifest_hash,
        limits=limits,
        usage=budget.snapshot(),
        checks=checks,
        detail=detail,
    )
    write_json(output / "result.json", result.model_dump())
    with (output / "events.jsonl").open("xb") as handle:
        handle.write(json.dumps(result.model_dump(), sort_keys=True).encode() + b"\n")
    print(result.model_dump_json())
    return 0 if status == "VERIFIED_LOCAL" else 2


def run_registered(arguments: argparse.Namespace, repository: Path) -> int:
    registration = repository / "benchmarks" / arguments.registration
    protocol = verify_engines(repository, registration, arguments.expected_sha256)
    if arguments.model != protocol["reference_model"]:
        raise ValueError("Model differs from frozen registration")
    tags = request_json(arguments.endpoint, "/api/tags")
    selected = next((item for item in tags["models"] if item["name"] == arguments.model), None)
    if not selected or selected["digest"] != protocol["reference_digest"]:
        raise ValueError("Model digest differs from frozen registration")
    output = arguments.output.resolve()
    if output.is_relative_to(repository):
        raise ValueError("Store raw evidence outside the repository")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "manifest.json", inventory(repository, arguments.endpoint, arguments.model))
    write_json(output / "registration.json", {"sha256": arguments.expected_sha256})
    if arguments.command == "micro":
        records = run_micro(
            arguments.family, arguments.endpoint, arguments.model, registration, output
        )
        return 0 if all(record["status"] == "VERIFIED_LOCAL" for record in records) else 2
    task, oracle = load_task(registration, arguments.task)
    with Fixture(task["files"]) as fixture:
        if arguments.candidate_directory:
            for path in fixture.worktree.iterdir():
                if path.name == ".git":
                    continue
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            source_snapshot(arguments.candidate_directory.resolve(), fixture.worktree)
        result = score(fixture, task, oracle, registration, Sandbox())
        write_json(output / "score.json", result.model_dump())
        print(result.model_dump_json())
    return 0 if result.status == "VERIFIED_LOCAL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
