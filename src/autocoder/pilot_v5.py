"""Versioned pilot correction: flat edit tools and public reproduce-first checks."""

import asyncio
import json
from pathlib import Path

from autocoder.baseline_probe import run_baseline
from autocoder.budget import Budget, BudgetExhausted
from autocoder.evaluator import score
from autocoder.execution import Sandbox
from autocoder.experiments import append
from autocoder.fixtures import Fixture
from autocoder.handoff_probe import Plan, decode
from autocoder.inference import infer
from autocoder.pilot import Changes, apply_exact, orient, overlay
from autocoder.protocol import Limits, write_json
from autocoder.tool_schema import Edit, inventory


class BoundedSandbox(Sandbox):
    def __init__(self, budget):
        self.budget = budget
        super().__init__()

    def execute(self, *args, **kwargs):
        kwargs["timeout"] = min(kwargs.get("timeout", 30), self.budget.remaining_seconds)
        return super().execute(*args, **kwargs)


def public_diagnostic(observed, cases):
    if observed.status == "COMPILE_FAILURE":
        return observed.observations[0].get("stderr", "Compilation failed")[:1024]
    if observed.status == "TEST_TAMPERING":
        raise ValueError("Protected tests/configuration were changed")
    for case, observation in zip(cases["cases"], observed.observations, strict=True):
        if not observation["pass"]:
            return json.dumps(
                {
                    "public_case": case,
                    "stdout": observation["execution"]["stdout"][:512],
                    "stderr": observation["execution"]["stderr"][:512],
                }
            )[:1536]
    return ""


async def implement(
    fixture, task, public, registration, endpoint, budget, output, sandbox, diagnostic
):
    evidence = orient(fixture, task)
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
                    + "\nPublic reproduction: "
                    + diagnostic
                    + "\nSource: "
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
        raise BudgetExhausted("Planning output cap")
    plan = decode(response["message"].get("content", ""), fixture.base_sha, set(evidence["files"]))
    write_json(output / "plan.json", plan.model_dump())
    edit_tool = [tool for tool in inventory(4) if tool["function"]["name"] == "apply_edit"]
    for attempt in range(2):
        try:
            for index, path in enumerate(dict.fromkeys(plan.paths)):
                evidence = orient(fixture, task)
                remaining_output = budget.limits.output_tokens - budget.snapshot().output_tokens
                if remaining_output <= 0:
                    raise BudgetExhausted("output_tokens")
                response = await infer(
                    endpoint,
                    "qwen3.5:9b",
                    [
                        {
                            "role": "user",
                            "content": (
                                "Call apply_edit exactly once for the named file. "
                                "Use unique exact matches and the current hash. "
                                "Preserve indentation. "
                                "If the file is already correct, emit identical old and new text. "
                                "Do not edit tests/configuration. Task: "
                                + task["prompt"]
                                + "\nCurrent file: "
                                + path
                                + "\nValidated plan: "
                                + plan.model_dump_json()
                                + "\nCurrent source: "
                                + json.dumps(evidence)
                                + "\nPublic diagnostic: "
                                + diagnostic
                            ),
                        }
                    ],
                    budget,
                    context=32768,
                    tools=edit_tool,
                    max_output=min(1536, remaining_output),
                )
                write_json(output / f"edit-{attempt}-{index}.json", response)
                if response["truncated"]:
                    raise BudgetExhausted("Implementation output cap")
                calls = response["message"].get("tool_calls") or []
                if len(calls) != 1 or calls[0]["function"]["name"] != "apply_edit":
                    raise ValueError("Exactly one apply_edit call is required")
                arguments = calls[0]["function"]["arguments"]
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                edit = Edit.model_validate(arguments)
                if edit.path != path:
                    raise ValueError("Edit does not target the declared current file")
                budget.consume(tool_calls=1)
                if edit.old != edit.new:
                    apply_exact(fixture, task, Changes(edits=[edit]))
            candidate = score(fixture, task, public, registration, sandbox)
            write_json(output / f"public-{attempt}.json", candidate.model_dump())
            if candidate.status == "VERIFIED_LOCAL":
                return
            diagnostic = public_diagnostic(candidate, public)
        except ValueError as error:
            diagnostic = str(error)[:1024]
        if attempt == 0:
            budget.consume(repairs=1)
    raise ValueError("Public verification failed after one repair: " + diagnostic[:512])


def run_task(
    arm: str,
    task: dict,
    oracle: dict,
    registration: Path,
    endpoint: str,
    limits: Limits,
    output: Path,
) -> dict:
    public = json.loads((registration / "public-checks.json").read_text())[task["id"]]
    budget = Budget(limits)
    result = {"arm": arm, "task_id": task["id"], "status": "FAILED_VERIFICATION"}
    sandbox = BoundedSandbox(budget)
    with Fixture(task["files"]) as fixture:
        result["base_sha"] = fixture.base_sha
        try:
            original = score(fixture, task, public, registration, sandbox)
            write_json(output / "public-baseline.json", original.model_dump())
            if original.status != "FAILED_VERIFICATION":
                raise ValueError("Public reproducer did not fail the base cleanly")
            diagnostic = public_diagnostic(original, public)
            if arm == "minimal_loop":
                asyncio.run(
                    implement(
                        fixture,
                        task,
                        public,
                        registration,
                        endpoint,
                        budget,
                        output,
                        sandbox,
                        diagnostic,
                    )
                )
            else:
                for attempt in range(2):
                    active_task = dict(
                        task,
                        files={
                            name: (fixture.worktree / name).read_text() for name in task["files"]
                        },
                        prompt=task["prompt"] + "\nPublic reproduction: " + diagnostic,
                    )
                    invocation = output / f"baseline-{attempt}"
                    invocation.mkdir()
                    client = run_baseline(arm, active_task, endpoint, budget, invocation)
                    write_json(invocation / "client.json", client)
                    overlay(fixture, invocation / "candidate")
                    if (client.get("proxy_error") or "").startswith("BudgetExhausted"):
                        raise BudgetExhausted(client["proxy_error"])
                    if client["status"] == "timeout":
                        raise BudgetExhausted("Baseline wall_seconds")
                    if client["exit_code"] != 0:
                        raise ValueError("Baseline client failed")
                    candidate = score(fixture, task, public, registration, sandbox)
                    write_json(output / f"public-{attempt}.json", candidate.model_dump())
                    if candidate.status == "VERIFIED_LOCAL":
                        break
                    diagnostic = public_diagnostic(candidate, public)
                    if attempt == 0:
                        budget.consume(repairs=1)
                if candidate.status != "VERIFIED_LOCAL":
                    raise ValueError("Public checks failed after one repair")
            # Held-out checks are terminal; no private values or diagnostics enter model prompts.
            acceptance = score(fixture, task, oracle, registration, sandbox)
            _ = budget.remaining_seconds
            write_json(output / "candidate-score.json", acceptance.model_dump())
            result["status"] = acceptance.status
        except BudgetExhausted as error:
            result.update(status="BUDGET_EXHAUSTED", error=str(error))
        except Exception as error:
            result.update(
                status="BLOCKED_ENVIRONMENT"
                if isinstance(error, OSError)
                else "FAILED_VERIFICATION",
                error=f"{type(error).__name__}: {error}"[:1024],
            )
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
