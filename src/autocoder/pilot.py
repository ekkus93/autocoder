"""Finite eight-task Stage 0 pilot; not the v0 autonomous application."""

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from autocoder.baseline_probe import run_baseline
from autocoder.budget import Budget, BudgetExhausted
from autocoder.evaluator import rust_toolchain, score, source_snapshot
from autocoder.execution import Sandbox
from autocoder.experiments import append
from autocoder.fixtures import Fixture, safe_relative
from autocoder.handoff_probe import decode
from autocoder.inference import infer
from autocoder.protocol import Limits, digest, write_json
from autocoder.tool_schema import Edit


class Changes(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    edits: Annotated[list[Edit], Field(min_length=1, max_length=6)]


def apply_exact(fixture: Fixture, task: dict, changes: Changes):
    editable = set(task["files"]) - set(task["protected"])
    for edit in changes.edits:
        relative = safe_relative(edit.path)
        if edit.path not in editable:
            raise ValueError("Write outside registered editable files")
        target = fixture.worktree / relative
        if any(path.is_symlink() for path in [target, *target.parents]):
            raise ValueError("Symlink source edit refused")
        source = target.read_bytes()
        if b"\x00" in source or digest(source) != edit.expected_sha256:
            raise ValueError("Binary or stale source precondition")
        text = source.decode()
        if not edit.old or text.count(edit.old) != 1:
            raise ValueError("Search text must match uniquely")
        content = text.replace(edit.old, edit.new, 1).encode()
        descriptor, temporary = tempfile.mkstemp(prefix=".edit-", dir=target.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
            if target.read_bytes() != source:
                raise ValueError("Source changed during write")
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)


def orient(fixture: Fixture, task: dict) -> dict:
    files = {}
    for name in task["files"]:
        if name in task["protected"]:
            continue
        path = fixture.worktree / safe_relative(name)
        raw = path.read_bytes()
        if len(raw) > 16384:
            raise ValueError("Fixture exceeds bounded orientation allowance")
        files[name] = {"sha256": digest(raw), "source": raw.decode()}
    return {"base_sha": fixture.base_sha, "files": files}


def public_check(fixture: Fixture, task: dict, sandbox: Sandbox, budget: Budget) -> dict:
    # No held-out cases/expected answers are used to guide repair.
    if task["language"] == "python":
        command = [
            "/usr/bin/python3",
            "-I",
            "-c",
            'import sys,importlib;sys.path.insert(0,"/work");'
            f"importlib.import_module({task['entry'].split('.')[0]!r})",
        ]
        result = sandbox.execute(
            fixture.worktree, command, timeout=min(30, budget.remaining_seconds)
        )
    else:
        command = [
            "/toolchain/bin/rustc",
            "--edition=2021",
            "--crate-type=lib",
            "src/lib.rs",
            "-o",
            "/tmp/fixture.rlib",
        ]
        result = sandbox.execute(
            fixture.worktree,
            command,
            toolchain=rust_toolchain(),
            timeout=min(30, budget.remaining_seconds),
        )
    return result.model_dump()


async def minimal(
    fixture: Fixture, task: dict, endpoint: str, budget: Budget, output: Path, sandbox: Sandbox
) -> dict:
    evidence = orient(fixture, task)
    append(
        output / "events.jsonl",
        {"phase": "ORIENT", "base_sha": fixture.base_sha, "paths": list(evidence["files"])},
    )
    from autocoder.handoff_probe import Plan

    response = await infer(
        endpoint,
        "qwen3.5:9b",
        [
            {
                "role": "user",
                "content": (
                    "Plan the source repair using the exact base_sha and actual paths. "
                    "Return one to five steps and acceptance checks. Task: "
                    + task["prompt"]
                    + "\nSource evidence: "
                    + json.dumps(evidence)
                ),
            }
        ],
        budget,
        context=32768,
        schema=Plan.model_json_schema(),
        max_output=512,
    )
    write_json(output / "plan-inference.json", response)
    if response["truncated"]:
        raise BudgetExhausted("planning request output cap")
    plan = decode(response["message"].get("content", ""), fixture.base_sha, set(evidence["files"]))
    write_json(output / "plan.json", plan.model_dump())
    diagnostic = ""
    for attempt in range(2):
        evidence = orient(fixture, task)
        append(
            output / "events.jsonl",
            {
                "phase": "IMPLEMENT" if attempt == 0 else "REPAIR",
                "attempt": attempt,
                "base_sha": fixture.base_sha,
            },
        )
        # Fresh messages: only validated plan, current source, and bounded diagnostics cross phases.
        response = await infer(
            endpoint,
            "qwen3.5:9b",
            [
                {
                    "role": "user",
                    "content": (
                        "Implement using unique exact search/replace edits. "
                        "Preserve indentation. "
                        "Copy each expected_sha256 exactly from current source evidence. "
                        "Do not change tests or configuration. Task: "
                        + task["prompt"]
                        + "\nValidated plan: "
                        + plan.model_dump_json()
                        + "\nCurrent source: "
                        + json.dumps(evidence)
                        + "\nDiagnostic: "
                        + diagnostic
                    ),
                }
            ],
            budget,
            context=32768,
            schema=Changes.model_json_schema(),
            max_output=1536,
        )
        write_json(output / f"edit-{attempt}-inference.json", response)
        try:
            if response["truncated"]:
                raise BudgetExhausted("implementation request output cap")
            changes = Changes.model_validate_json(response["message"].get("content", ""))
            budget.consume(tool_calls=len(changes.edits))
            apply_exact(fixture, task, changes)
            check = public_check(fixture, task, sandbox, budget)
            write_json(output / f"public-{attempt}.json", check)
            if check["exit_code"] == 0 and check["status"] == "finished":
                return {"public_check": "pass"}
            diagnostic = check["stderr"][:1024]
        except ValueError as error:
            diagnostic = str(error)[:1024]
        if attempt == 0:
            budget.consume(repairs=1)
    return {"public_check": "fail", "diagnostic": diagnostic}


def overlay(fixture: Fixture, snapshot: Path):
    for path in fixture.worktree.iterdir():
        if path.name == ".git":
            continue
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    source_snapshot(snapshot, fixture.worktree)


def run_task(
    arm: str,
    task: dict,
    oracle: dict,
    registration: Path,
    endpoint: str,
    limits: Limits,
    output: Path,
) -> dict:
    budget = Budget(limits)
    result = {"arm": arm, "task_id": task["id"], "status": "FAILED_VERIFICATION"}
    sandbox = Sandbox()
    with Fixture(task["files"]) as fixture:
        result["base_sha"] = fixture.base_sha
        try:
            baseline = score(fixture, task, oracle, registration, sandbox)
            write_json(output / "baseline-score.json", baseline.model_dump())
            if baseline.status != "FAILED_VERIFICATION":
                raise ValueError("Seeded baseline did not fail the target oracle cleanly")
            if arm == "minimal_loop":
                result["implementation"] = asyncio.run(
                    minimal(fixture, task, endpoint, budget, output, sandbox)
                )
            else:
                for attempt in range(2):
                    invocation = output / f"baseline-{attempt}"
                    invocation.mkdir()
                    result["implementation"] = run_baseline(arm, task, endpoint, budget, invocation)
                    write_json(invocation / "client.json", result["implementation"])
                    overlay(fixture, invocation / "candidate")
                    proxy_error = result["implementation"].get("proxy_error") or ""
                    if proxy_error.startswith("BudgetExhausted"):
                        raise BudgetExhausted(proxy_error)
                    if result["implementation"]["status"] == "timeout":
                        raise BudgetExhausted("baseline wall_seconds")
                    if result["implementation"]["exit_code"] != 0:
                        raise RuntimeError("Baseline client did not complete successfully")
                    check = public_check(fixture, task, sandbox, budget)
                    write_json(output / f"public-{attempt}.json", check)
                    if check["exit_code"] == 0:
                        break
                    if attempt == 0:
                        budget.consume(repairs=1)
                        task = dict(
                            task,
                            files={
                                name: (fixture.worktree / name).read_text()
                                for name in task["files"]
                            },
                            prompt=task["prompt"]
                            + "\nPublic compilation/import failed: "
                            + check["stderr"][:1024],
                        )
            if arm == "minimal_loop" and result["implementation"].get("public_check") != "pass":
                raise ValueError("Public compilation/import checks failed")
            if arm != "minimal_loop" and check["exit_code"] != 0:
                raise ValueError("Public compilation/import checks failed after repair")
            candidate = score(fixture, task, oracle, registration, sandbox)
            _ = budget.remaining_seconds
            write_json(output / "candidate-score.json", candidate.model_dump())
            result["status"] = candidate.status
        except BudgetExhausted as error:
            result["status"] = "BUDGET_EXHAUSTED"
            result["error"] = str(error)
        except Exception as error:
            result["status"] = (
                "BLOCKED_ENVIRONMENT" if isinstance(error, OSError) else "FAILED_VERIFICATION"
            )
            result["error"] = f"{type(error).__name__}: {error}"[:1024]
        finally:
            (output / "diff.patch").write_text(fixture.diff() + "\n")
            result["usage"] = budget.snapshot().model_dump()
            append(
                output / "events.jsonl",
                {
                    "phase": "FINAL",
                    "status": result["status"],
                    "base_sha": fixture.base_sha,
                    "usage": result["usage"],
                },
            )
    write_json(output / "result.json", result)
    return result
