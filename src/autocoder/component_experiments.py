"""Edit/retrieval component qualification; not the full application engine."""

import asyncio
import json
import subprocess
import time
from pathlib import Path

from pydantic import ValidationError

from autocoder.budget import Budget, BudgetExhausted
from autocoder.editing_probe import FORMATS, apply
from autocoder.execution import Sandbox
from autocoder.experiments import append
from autocoder.fixtures import Fixture
from autocoder.inference import InferenceError, infer
from autocoder.protocol import Limits, digest, write_json
from autocoder.serena_probe import Serena


def content(result: dict) -> str:
    return "\n".join(item.get("text", "") for item in result.get("content", []))


async def edits(endpoint: str, model: str, registration: Path, output: Path):
    trials = json.loads((registration / "edit_trials.json").read_text())
    sandbox = Sandbox()
    records = []
    for method in ("exact", "diff", "symbol"):
        for trial in trials:
            budget = Budget(Limits())
            record = {
                "method": method,
                "trial_id": trial["id"],
                "kind": trial["kind"],
                "attempts": [],
            }
            with Fixture(trial["files"]) as fixture:
                serena = None
                try:
                    if method == "symbol":
                        serena = Serena(fixture.worktree)
                        record["startup_seconds"] = serena.startup_seconds
                        serena.call("initial_instructions", {})
                        record["serena_config"] = serena.call("get_current_config", {})
                    prompt = (
                        "Change only function value in module.py to return 1. "
                        "Preserve any other function. "
                        f"Use the {method} edit representation. "
                        "On the first attempt preserve supplied path and hash exactly, "
                        "even if stale; the host checks them. "
                        "For exact edits also preserve supplied old/new. "
                        "For diff edits emit a plain unified diff starting with "
                        "--- a/module.py and "
                        "+++ b/module.py, without diff --git headers. "
                        "For symbol edits use symbol value and a full function definition body.\n"
                        + json.dumps(
                            {
                                key: trial[key]
                                for key in ("path", "expected_sha256", "old", "new", "files")
                            }
                        )
                    )
                    messages = [{"role": "user", "content": prompt}]
                    for attempt in range(2):
                        observation = {
                            "schema_valid": False,
                            "clean_apply": False,
                            "correct_target": False,
                            "functional": False,
                        }
                        response = await infer(
                            endpoint,
                            model,
                            messages,
                            budget,
                            context=32768,
                            schema=FORMATS[method].model_json_schema(),
                            max_output=1024,
                        )
                        observation["inference"] = response
                        try:
                            decoded = json.loads(response["message"].get("content", ""))
                            FORMATS[method].model_validate(decoded)
                            observation["schema_valid"] = True
                            budget.consume(tool_calls=1)
                            apply(fixture, method, decoded, serena)
                            observation["clean_apply"] = True
                            observation["correct_target"] = decoded["path"] == "module.py"
                            check = sandbox.execute(
                                fixture.worktree,
                                [
                                    "/usr/bin/python3",
                                    "-I",
                                    "-c",
                                    'import sys,json;sys.path.insert(0,"/work");import module;'
                                    'print(json.dumps({"value":module.value(),"other":getattr(module,"other",lambda:0)()}))',
                                ],
                                timeout=min(30, budget.remaining_seconds),
                            )
                            observation["check"] = check.model_dump()
                            observation["functional"] = check.exit_code == 0 and json.loads(
                                check.stdout
                            ) == {"value": 1, "other": 0}
                        except (
                            ValueError,
                            ValidationError,
                            OSError,
                            subprocess.SubprocessError,
                        ) as error:
                            observation["error"] = str(error)[:1024]
                        record["attempts"].append(observation)
                        if observation["functional"]:
                            break
                        if attempt == 0:
                            budget.consume(repairs=1)
                            actual = (fixture.worktree / "module.py").read_text()
                            messages = [
                                {
                                    "role": "user",
                                    "content": prompt
                                    + "\nThe initial operation failed: "
                                    + observation.get("error", "functional check failed")
                                    + ". Correct path, hash, and old-text context from: "
                                    + json.dumps(
                                        {
                                            "path": "module.py",
                                            "expected_sha256": digest(actual.encode()),
                                            "source": actual,
                                        }
                                    ),
                                }
                            ]
                    _ = budget.remaining_seconds
                    record["status"] = (
                        "VERIFIED_LOCAL"
                        if record["attempts"][-1]["functional"]
                        else "FAILED_VERIFICATION"
                    )
                    record["diff"] = fixture.diff()
                except (BudgetExhausted, InferenceError, TimeoutError, RuntimeError) as error:
                    record["status"] = (
                        "BUDGET_EXHAUSTED"
                        if isinstance(error, BudgetExhausted)
                        else "BLOCKED_ENVIRONMENT"
                    )
                    record["error"] = str(error)[:1024]
                finally:
                    if serena:
                        serena.close()
                record["usage"] = budget.snapshot().model_dump()
            append(output / "trials.jsonl", record)
            records.append(record)
            print(
                json.dumps({"method": method, "trial": trial["id"], "status": record["status"]}),
                flush=True,
            )
    write_json(output / "summary.json", {"schema_version": 1, "family": "S0-C", "trials": records})


def retrieval(registration: Path, output: Path):
    trials = json.loads((registration / "retrieval_trials.json").read_text())
    results = []
    for trial in trials:
        with Fixture(trial["files"]) as fixture:
            started = time.monotonic()
            rg = subprocess.run(
                ["rg", "--json", "--fixed-strings", trial["symbol"], "."],
                cwd=fixture.worktree,
                capture_output=True,
                text=True,
                timeout=5,
            )
            rg_seconds = time.monotonic() - started
            with Serena(fixture.worktree) as serena:
                serena.call("initial_instructions", {})
                config = serena.call("get_current_config", {})
                started = time.monotonic()
                found = serena.call(
                    "find_symbol",
                    {
                        "name_path_pattern": trial["symbol"],
                        "relative_path": "",
                        "include_body": True,
                        "max_answer_chars": 2048,
                    },
                )
                elapsed = time.monotonic() - started
                matches = json.loads(content(found)) if not found.get("isError") else []
                correct = any(
                    item.get("relative_path") == trial["expected_path"] for item in matches
                )
                record = {
                    "trial_id": trial["id"],
                    "base_sha": fixture.base_sha,
                    "rg": {
                        "correct": rg.returncode == 0 and trial["symbol"] in rg.stdout,
                        "seconds": rg_seconds,
                        "bytes": len(rg.stdout.encode()),
                    },
                    "serena": {
                        "correct": correct,
                        "startup_seconds": serena.startup_seconds,
                        "query_seconds": elapsed,
                        "bytes": len(content(found).encode()),
                        "response": found,
                        "config": config,
                    },
                }
                append(output / "trials.jsonl", record)
                results.append(record)
                print(json.dumps({"trial": trial["id"], "serena_correct": correct}), flush=True)
    write_json(output / "summary.json", {"schema_version": 1, "family": "S0-D", "trials": results})


def run(family: str, endpoint: str, model: str, registration: Path, output: Path):
    if family == "edits":
        asyncio.run(edits(endpoint, model, registration, output))
    else:
        retrieval(registration, output)
