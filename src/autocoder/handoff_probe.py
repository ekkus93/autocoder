"""Strict, revision-anchored handoffs with a single bounded decoding recovery."""

import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from autocoder.budget import Budget
from autocoder.fixtures import safe_relative
from autocoder.inference import infer


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    base_sha: Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
    paths: Annotated[list[str], Field(min_length=1, max_length=8)]
    steps: Annotated[list[str], Field(min_length=1, max_length=5)]
    acceptance_checks: Annotated[list[str], Field(min_length=1, max_length=5)]


def decode(raw: str, base_sha: str, allowed_paths: set[str]) -> Plan:
    plan = Plan.model_validate_json(raw)
    if plan.base_sha != base_sha:
        raise ValueError("Stale handoff revision")
    for name in plan.paths:
        safe_relative(name)
        if name not in allowed_paths:
            raise ValueError("Handoff references an unknown source path")
    return plan


async def repair_plan(endpoint: str, model: str, raw: str, evidence: dict, budget: Budget):
    attempts = []
    for attempt in range(2):
        try:
            plan = decode(raw, evidence["base_sha"], set(evidence["files"]))
            attempts.append({"valid": True})
            return plan, attempts
        except (ValueError, ValidationError) as error:
            attempts.append({"valid": False, "error": str(error)[:512]})
            if attempt == 1:
                raise ValueError("Invalid handoff after bounded recovery") from error
            budget.consume(repairs=1)
            response = await infer(
                endpoint,
                model,
                [
                    {
                        "role": "user",
                        "content": (
                            "Return a plan for this exact base_sha and project paths. "
                            "Use one to five steps and acceptance checks. "
                            + json.dumps(evidence)
                            + "\nPrevious handoff was rejected: "
                            + str(error)[:512]
                        ),
                    }
                ],
                budget,
                context=32768,
                schema=Plan.model_json_schema(),
                max_output=512,
            )
            raw = response["message"].get("content", "")
    raise AssertionError("Unreachable bounded decoder")
