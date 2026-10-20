"""Pre-registered handoff, thinking, schema and cache measurements."""

import asyncio
import json
from pathlib import Path

from autocoder.budget import Budget, BudgetExhausted
from autocoder.experiments import SYSTEM, append
from autocoder.handoff_probe import Plan, decode, repair_plan
from autocoder.inference import InferenceError, infer
from autocoder.protocol import Limits, write_json
from autocoder.provenance import request_json
from autocoder.tool_schema import inventory, validate_choice


async def handoffs(endpoint: str, model: str, registration: Path, output: Path):
    evidence = json.loads((registration / "handoff_trial.json").read_text())
    results = []
    for api in ("native", "openai"):
        budget = Budget(Limits())
        record = {"api": api}
        try:
            response = await infer(
                endpoint,
                model,
                [
                    {
                        "role": "user",
                        "content": (
                            "Return a repair plan for this exact source and revision: "
                            + json.dumps(evidence)
                        ),
                    }
                ],
                budget,
                context=32768,
                api=api,
                schema=Plan.model_json_schema(),
                max_output=512,
            )
            record["response"] = response
            plan = decode(
                response["message"].get("content", ""), evidence["base_sha"], set(evidence["files"])
            )
            record["valid"] = True
            record["paths"] = plan.paths
            # Separately measure seeded decoder recovery, not as first-try model performance.
            repaired, attempts = await repair_plan(
                endpoint, model, '{"steps": []}', evidence, budget
            )
            record["seeded_recovery"] = {"attempts": attempts, "plan": repaired.model_dump()}
            record["status"] = "VERIFIED_LOCAL"
        except (ValueError, BudgetExhausted, InferenceError) as error:
            record["status"] = (
                "BUDGET_EXHAUSTED" if isinstance(error, BudgetExhausted) else "FAILED_VERIFICATION"
            )
            record["error"] = str(error)[:1024]
        record["usage"] = budget.snapshot().model_dump()
        append(output / "trials.jsonl", record)
        results.append(record)
    write_json(output / "summary.json", {"family": "structured_handoffs", "trials": results})


async def cache_and_thinking(endpoint: str, model: str, registration: Path, output: Path):
    trials = json.loads((registration / "tool_trials.json").read_text())[:8]
    records = []
    for arm in ("fixed", "per_phase", "thinking"):
        for trial in trials:
            definitions = inventory(6)
            if arm == "per_phase":
                requested = trial["expected"]["name"] if trial["expected"] else "search_text"
                phase = (
                    {"search_text", "read_file_range"}
                    if requested in {"search_text", "read_file_range"}
                    else {requested}
                )
                definitions = [tool for tool in definitions if tool["function"]["name"] in phase]
            budget = Budget(Limits())
            record = {
                "arm": arm,
                "trial_id": trial["id"],
                "schema_bytes": len(json.dumps(definitions).encode()),
            }
            try:
                response = await infer(
                    endpoint,
                    model,
                    [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": trial["prompt"]},
                    ],
                    budget,
                    context=32768,
                    think=arm == "thinking",
                    tools=definitions,
                    max_output=512,
                )
                valid, correct = validate_choice(
                    response["message"], trial["expected"], definitions
                )
                record.update(
                    {
                        "response": response,
                        "schema_valid": valid,
                        "semantic_correct": correct,
                        "status": "VERIFIED_LOCAL" if valid and correct else "FAILED_VERIFICATION",
                    }
                )
            except (BudgetExhausted, InferenceError) as error:
                record["status"] = (
                    "BUDGET_EXHAUSTED"
                    if isinstance(error, BudgetExhausted)
                    else "BLOCKED_ENVIRONMENT"
                )
                record["error"] = str(error)
            record["usage"] = budget.snapshot().model_dump()
            record["residency"] = request_json(endpoint, "/api/ps")
            append(output / "trials.jsonl", record)
            records.append(record)
    # Measure schema surface cost against a constant no-tool request on the actual template.
    calibrations = []
    for count in (0, 4, 6, 12):
        response = await infer(
            endpoint,
            model,
            [{"role": "user", "content": "Return the number zero."}],
            Budget(Limits()),
            context=32768,
            tools=inventory(count) if count else None,
            max_output=128,
        )
        calibrations.append({"inventory": count, "response": response})
    write_json(
        output / "summary.json",
        {"family": "cache_thinking", "trials": records, "schema_calibration": calibrations},
    )


def run(family: str, endpoint: str, model: str, registration: Path, output: Path):
    asyncio.run(
        {"handoffs": handoffs, "cache": cache_and_thinking}[family](
            endpoint, model, registration, output
        )
    )
