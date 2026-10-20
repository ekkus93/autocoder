"""One deterministic phase loop; models propose changes, checks decide completion."""

import asyncio
import json
from pathlib import Path

from autocoder.budget import BudgetExhausted
from autocoder.execution import SandboxUnavailable
from autocoder.inference import InferenceError
from autocoder.protocol import digest
from autocoder.provenance import inventory, request_json
from autocoder.v0.gateway import RepeatedObservation, ToolGateway
from autocoder.v0.journal import NeedsUser
from autocoder.v0.model import ContextBuilder, ModelBackend, TaskBudget
from autocoder.v0.navigation import Navigation
from autocoder.v0.schema import TRANSITIONS, Orientation, Outcome, Phase, Plan
from autocoder.v0.verification import VerificationRunner, diagnostic, passed
from autocoder.v0.workspace import Workspace, git


class Coordinator:
    def __init__(self, project, journal, *, transport=None, verifier=None):
        self.project, self.journal = project, journal
        self.workspace = Workspace(project, journal)
        self.budget = TaskBudget(project.limits, journal)
        self.model = ModelBackend(
            project, journal, self.budget, **({"transport": transport} if transport else {})
        )
        self.builder = ContextBuilder()
        self.phase = Phase.PREFLIGHT
        self.verifier_factory = verifier or VerificationRunner
        self.checks = None
        self.gateway = None
        self.navigator = None

    def transition(self, target):
        if target not in TRANSITIONS[self.phase]:
            raise ValueError(f"Invalid transition {self.phase} to {target}")
        self.phase = target
        self.journal.phase = str(target)
        self.journal.emit("PHASE", status="RUNNING")
        if self.gateway:
            self.gateway.enter(target)

    async def structured(
        self, schema, request, evidence, *, handoff=None, validate=None, schema_override=None
    ):
        error = None
        for attempt in range(2):
            messages = self.builder.build(self.phase, request, evidence, handoff, error)
            message = await self.model.request(
                messages, schema=schema_override or schema.model_json_schema(), output=1024
            )
            try:
                value = schema.model_validate_json(message.get("content", ""))
                if validate:
                    validate(value)
                ref = self.journal.artifact(value.model_dump(mode="json"))
                self.journal.emit("HANDOFF", evidence_ref=ref, data={"type": schema.__name__})
                return value
            except ValueError as failure:
                if attempt:
                    raise ValueError(
                        "Invalid phase artifact after one decoding repair"
                    ) from failure
                self.budget.consume(repairs=1)
                error = str(failure)[:1024]
        raise AssertionError("Unreachable bounded handoff")

    async def orient(self, task):
        evidence = self.gateway.evidence(request=task)
        if len(self.project.readable_paths) > 8 or any(
            v["truncated"] or (v["total_lines"] > 120 and not v["focused_symbol"])
            for v in evidence["files"].values()
        ):
            messages = self.builder.build(
                self.phase,
                task + "\nLocate relevant code using bounded read/search tools. "
                "When enough source is retrieved, reply without tools.",
                evidence,
            )
            stop_discovery = False
            for _ in range(4):
                if not self.model.fits_context(
                    messages, tools=self.gateway.tools(), output=768
                ) or not self.model.fits_request_budget(
                    messages, tools=self.gateway.tools(), output=768
                ):
                    self.journal.emit(
                        "CONTEXT_RESET",
                        data={
                            "reason": "orientation history reached context reserve; build handoff"
                        },
                    )
                    break
                message = await self.model.request(messages, tools=self.gateway.tools(), output=768)
                calls = message.get("tool_calls") or []
                if not calls:
                    break
                messages.append(dict(message, role="assistant"))
                retrieved = []
                for call in calls:
                    function = call.get("function", {})
                    try:
                        observation = self.gateway.dispatch(
                            function.get("name"), function.get("arguments")
                        )
                    except RepeatedObservation:
                        self.journal.emit(
                            "REPETITION_STOP", data={"action": "build orientation handoff"}
                        )
                        stop_discovery = True
                        break
                    retrieved.append(observation)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_name": function.get("name"),
                            "content": json.dumps(observation),
                        }
                    )
                    if (
                        isinstance(observation, dict)
                        and "path" in observation
                        and "source" in observation
                    ):
                        current = evidence["files"].get(observation["path"], {})
                        if not current.get("focused_symbol"):
                            evidence["files"][observation["path"]] = observation
                # Source is already in files; repeating it here can overflow the fresh handoff.
                evidence["last_retrieval"] = [
                    {key: observation[key] for key in ("path", "sha256", "start", "end")}
                    if isinstance(observation, dict) and "source" in observation
                    else observation
                    for observation in retrieved
                ]
                if stop_discovery:
                    break

        def validate(value):
            if value.base_sha != self.workspace.base_sha:
                raise ValueError("Orientation cites stale base revision")
            for finding in value.findings:
                actual = evidence["files"].get(finding.path)
                if (
                    not actual
                    or finding.sha256 != actual["sha256"]
                    or finding.end < finding.start
                    or not any(
                        start <= finding.start <= finding.end <= end and sha == finding.sha256
                        for start, end, sha in self.gateway.reads.get(finding.path, [])
                    )
                ):
                    raise ValueError("Orientation is not anchored to current source")

        return await self.structured(Orientation, task, evidence, validate=validate)

    async def plan(self, task, findings, baseline):
        self.workspace.assert_expected()
        evidence = {
            "base_sha": self.workspace.base_sha,
            "files": {
                f.path: self.gateway.read(f.path, f.start, min(f.end, f.start + 119))
                for f in findings.findings
            },
        }
        # A summary can omit a companion test/source file that discovery already exposed.
        # Carry only approved edit paths with actual read provenance into the fresh plan.
        for path in self.project.editable_paths:
            if path in evidence["files"] or not self.gateway.reads.get(path):
                continue
            start, end, sha = self.gateway.reads[path][-1]
            entry = self.gateway.read(path, start, min(end, start + 119))
            if entry["sha256"] != sha:
                raise NeedsUser("Observed companion source became stale before planning")
            evidence["files"][path] = entry
        evidence["allowed_edit_paths"] = [
            path for path in evidence["files"] if self.project.can_edit(path)
        ]
        if not evidence["allowed_edit_paths"]:
            raise NeedsUser("Planning has no approved, observed source to edit")
        evidence["baseline_diagnostic"] = diagnostic(baseline)
        evidence["required_check_names"] = [c.name for c in self.project.checks]
        if any(evidence["files"][f.path]["sha256"] != f.sha256 for f in findings.findings):
            raise NeedsUser("Orientation became stale before planning")

        def validate(plan):
            if plan.base_sha != self.workspace.base_sha:
                raise ValueError("Plan cites a stale revision")
            if len(plan.paths) != len(set(plan.paths)) or len(plan.checks) != len(set(plan.checks)):
                raise ValueError("Plan paths and check names must be unique")
            if not set(plan.paths) <= set(evidence["files"]) or not all(
                self.project.can_edit(p) for p in plan.paths
            ):
                raise ValueError("Plan paths must be grounded and approved for editing")
            # The model cannot remove or substitute configured acceptance checks.
            if set(plan.checks) != {c.name for c in self.project.checks}:
                raise ValueError("Plan must preserve all configured named checks")

        schema = Plan.model_json_schema()
        schema["properties"]["paths"]["items"] = {
            "type": "string",
            "enum": evidence["allowed_edit_paths"],
        }
        schema["properties"]["checks"]["items"] = {
            "type": "string",
            "enum": evidence["required_check_names"],
        }
        schema["properties"]["checks"].update(
            minItems=len(self.project.checks), maxItems=len(self.project.checks)
        )
        return await self.structured(
            Plan,
            task,
            evidence,
            handoff=findings.model_dump(),
            validate=validate,
            schema_override=schema,
        )

    async def implement(self, task, plan, failure):
        self.gateway.enter(self.phase, plan.paths)
        instruction = (
            task + "\nUse apply_edit with exact text and current hash. "
            "Retrieve source if needed. Fix every declared file. "
            "When ready for verification, reply without tools."
        )
        messages = self.builder.build(
            self.phase,
            instruction,
            self.gateway.evidence(plan.paths, request=task),
            plan.model_dump(),
            failure,
        )
        completed = []
        recent_source = {}
        mutated = False
        for _ in range(self.project.phase_tool_calls + 1):
            self.workspace.assert_expected()
            rendered = len(
                json.dumps({"messages": messages, "tools": self.gateway.tools()}).encode()
            )
            if rendered + 2560 > self.project.context * 0.75 or not self.model.fits_request_budget(
                messages, tools=self.gateway.tools(), output=1536
            ):
                evidence = self.gateway.evidence(plan.paths, request=task)
                expected = self.workspace.expected()
                for path, frame in recent_source.items():
                    current = evidence["files"].get(path)
                    if (
                        current
                        and not current.get("focused_symbol")
                        and frame["sha256"] == expected[path]
                    ):
                        evidence["files"][path] = frame
                initial = next(
                    row["observed_hashes"]
                    for row in self.journal.read()
                    if row["kind"] == "WORKTREE_OUTCOME"
                )
                changed = [path for path in plan.paths if expected[path] != initial[path]]
                evidence["changed_paths"] = changed
                evidence["unchanged_planned_paths"] = [
                    path for path in plan.paths if path not in changed
                ]
                evidence["completed_operation_summaries"] = completed[-4:]
                if mutated and failure:
                    evidence["historical_diagnostic_before_edits"] = failure[:4096]
                compact_instruction = (
                    instruction
                    + "\nHistory compacted. Changed paths report applied filesystem edits. "
                    + (
                        "Prior diagnostics predate edits in this phase. "
                        if mutated
                        else "The attached diagnostic is the latest verification failure. "
                    )
                    + "Focus on remaining work without repeating unchanged reads."
                )
                messages = self.builder.build(
                    self.phase,
                    compact_instruction,
                    evidence,
                    plan.model_dump(),
                    None if mutated else failure,
                )
                if not self.model.fits_request_budget(
                    messages, tools=self.gateway.tools(), output=1536
                ):
                    # Keep changed-file identity while making room for unfinished companion work.
                    # These files remain readable through the bounded gateway if needed again.
                    for path in changed:
                        evidence["files"][path] = {
                            key: value
                            for key, value in evidence["files"][path].items()
                            if key != "source"
                        }
                        evidence["files"][path]["source_omitted"] = (
                            "already changed; read if needed"
                        )
                    messages = self.builder.build(
                        self.phase,
                        compact_instruction,
                        evidence,
                        plan.model_dump(),
                        None if mutated else failure,
                    )
                self.journal.emit(
                    "CONTEXT_RESET", data={"reason": "context or remaining request allowance"}
                )
            if not self.model.fits_request_budget(
                messages, tools=self.gateway.tools(), output=1536
            ):
                if mutated:
                    self.journal.emit(
                        "VERIFY_WITHOUT_INFERENCE",
                        data={
                            "reason": "candidate edited; no affordable next inference reservation"
                        },
                    )
                    return
                raise BudgetExhausted("request_tokens")
            message = await self.model.request(messages, tools=self.gateway.tools(), output=1536)
            calls = message.get("tool_calls") or []
            if not calls:
                return
            messages.append(dict(message, role="assistant"))
            for call in calls:
                function = call.get("function", {})
                try:
                    observation = self.gateway.dispatch(
                        function.get("name"), function.get("arguments")
                    )
                except RepeatedObservation:
                    self.journal.emit("REPETITION_STOP", data={"action": "verify candidate"})
                    return
                messages.append(
                    {
                        "role": "tool",
                        "tool_name": function.get("name"),
                        "content": json.dumps(observation),
                    }
                )
                if isinstance(observation, dict):
                    if observation.get("changed"):
                        mutated = True
                        recent_source.pop(observation["path"], None)
                    elif "path" in observation and "source" in observation:
                        recent_source[observation["path"]] = observation
                completed.append(
                    {
                        "tool": function.get("name"),
                        "path": observation.get("path") if isinstance(observation, dict) else None,
                        "changed": bool(observation.get("changed"))
                        if isinstance(observation, dict)
                        else False,
                        "result_sha256": digest(json.dumps(observation, sort_keys=True).encode()),
                        "error": observation.get("error")
                        if isinstance(observation, dict)
                        else None,
                    }
                )
        raise BudgetExhausted("implementation step cap")

    def reproduction(self, baseline):
        if passed(baseline):
            raise NeedsUser("Bug reproduction is inconclusive: configured checks pass on the base")
        target = False
        for check, result in zip(self.project.checks, baseline, strict=True):
            execution = result["execution"]
            if execution["status"] != "finished" or execution["exit_code"] in {126, 127}:
                raise SandboxUnavailable("Baseline execution unavailable")
            if check.regression_pattern and execution["exit_code"] != 0:
                output = execution["stderr"] + execution["stdout"]
                # Literal expected signature avoids user-supplied catastrophic regexes.
                if check.regression_pattern in output:
                    target = True
        if not target:
            raise NeedsUser("Base failure does not match a configured regression signature")

    async def run(self, request, *, resume=False, metadata=True):
        result = {"status": str(Outcome.FAILED_VERIFICATION), "task_id": self.journal.task_id}
        baseline = []
        try:
            _ = self.budget.remaining_seconds
            if resume:
                self.workspace.restore()
                resumes = [r for r in self.journal.read() if r["kind"] == "RESUME"]
                if len(resumes) >= 1:
                    raise NeedsUser("One bounded restart/replan already used")
                self.journal.emit("RESUME", data={"replans": 1})
            else:
                self.workspace.create()
            if metadata:
                metadata_result = request_json(self.project.endpoint, "/api/tags")
                if not isinstance(metadata_result.get("models"), list):
                    raise SandboxUnavailable("Ollama inventory endpoint is unavailable")
                tags = metadata_result["models"]
                selected = next((m for m in tags if m["name"] == self.project.model), None)
                if selected is None or (
                    self.project.model_digest and selected["digest"] != self.project.model_digest
                ):
                    raise SandboxUnavailable("Configured model missing or digest changed")
                identities = [r for r in self.journal.read() if r["kind"] == "MODEL_IDENTITY"]
                if identities and identities[0]["data"]["digest"] != selected["digest"]:
                    raise NeedsUser("Model tag changed since task creation")
                self.journal.emit(
                    "MODEL_IDENTITY",
                    data={"digest": selected["digest"], "model": self.project.model},
                )
                manifest = inventory(
                    Path(__file__).resolve().parents[3], self.project.endpoint, self.project.model
                )
                self.journal.emit("MANIFEST", evidence_ref=self.journal.artifact(manifest))
            self.checks = self.verifier_factory(self.workspace, self.budget)
            if self.project.serena:
                self.navigator = Navigation(self.workspace, self.budget)
                try:
                    self.navigator.ensure()
                except (RuntimeError, TimeoutError, OSError, ValueError) as error:
                    self.journal.emit("NAVIGATION_FALLBACK", data={"reason": type(error).__name__})
                    self.navigator.close()
                    self.navigator = None
            self.gateway = ToolGateway(self.workspace, self.budget, self.checks, self.navigator)
            previous = [r for r in self.journal.read() if r["kind"] == "BASELINE"]
            if previous:
                baseline = self.journal.load(previous[0]["evidence_ref"])
            else:
                baseline = self.checks.all("baseline")
                self.journal.emit("BASELINE", evidence_ref=self.journal.artifact(baseline))
            self.reproduction(baseline)
            self.transition(Phase.ORIENT)
            findings = await self.orient(request)
            self.transition(Phase.REPRODUCE_AND_PLAN)
            plan = await self.plan(request, findings, baseline)
            self.transition(Phase.IMPLEMENT)
            await self.implement(request, plan, diagnostic(baseline))
            public_failures = 0
            while True:
                self.transition(Phase.VERIFY)
                checks = self.checks.all("candidate")
                self.workspace.assert_expected()
                if passed(checks):
                    # Private failures are terminal, never part of repair context.
                    held = self.checks.held_out()
                    if not all(row["pass"] for row in held):
                        result["detail"] = (
                            "Independent held-out acceptance failed; no oracle feedback disclosed"
                        )
                        break
                    if not self.workspace.diff():
                        raise NeedsUser(
                            "Checks passed without a source change; inspect reproducer stability"
                        )
                    self.workspace.checkpoint()
                    _ = self.budget.remaining_seconds
                    result["status"] = str(Outcome.VERIFIED_LOCAL)
                    break
                self.budget.consume(repairs=1)
                public_failures += 1
                replans = [r for r in self.journal.read() if r["kind"] in {"RESUME", "REPLAN"}]
                if public_failures == 2 and not replans:
                    self.journal.emit("REPLAN", data={"count": 1})
                    self.transition(Phase.ORIENT)
                    revised_request = (
                        request + "\nPublic failure after bounded repairs: " + diagnostic(checks)
                    )
                    findings = await self.orient(revised_request)
                    self.transition(Phase.REPRODUCE_AND_PLAN)
                    plan = await self.plan(revised_request, findings, baseline)
                    self.transition(Phase.IMPLEMENT)
                    await self.implement(request, plan, diagnostic(checks))
                    continue
                self.transition(Phase.REPAIR)
                await self.implement(request, plan, diagnostic(checks))
            self.transition(Phase.REPORT)
        except NeedsUser as error:
            result.update(status=str(Outcome.NEEDS_USER), detail=str(error))
        except BudgetExhausted as error:
            result.update(status=str(Outcome.BUDGET_EXHAUSTED), detail=str(error))
        except (SandboxUnavailable, InferenceError, OSError) as error:
            result.update(
                status=str(Outcome.BLOCKED_ENVIRONMENT),
                detail=f"{type(error).__name__}: {error}"[:1024],
            )
        except (asyncio.CancelledError, KeyboardInterrupt):
            result.update(
                status=str(Outcome.CANCELLED),
                detail="Cancelled; recorded operations retained for reconciliation",
            )
        except Exception as error:
            result.update(
                status=str(Outcome.FAILED_VERIFICATION),
                detail=f"{type(error).__name__}: {error}"[:1024],
            )
        finally:
            if self.navigator:
                self.navigator.close()
            result["usage"] = self.budget.snapshot().model_dump()
            result["phase"] = str(self.phase)
            result["branch"] = self.workspace.branch
            result["worktree"] = str(self.workspace.root)
            result["evidence_directory"] = str(self.journal.directory)
            result["base_sha"] = self.workspace.base_sha
            result["acceptance"] = {
                name: "not_run"
                for name in (
                    "format",
                    "lint",
                    "compile",
                    "tests",
                    "review",
                    "remote_ci",
                    "hardware",
                    "human_acceptance",
                )
            }
            result["acceptance"]["held_out"] = "not_run"
            try:
                events = self.journal.read()
                private = [r for r in events if r["kind"] == "HELD_OUT"]
                if private:
                    result["acceptance"]["held_out"] = private[-1]["status"]
                for kind in ("format", "lint", "compile", "tests"):
                    checks = [
                        r
                        for r in events
                        if r["kind"] == "CHECK"
                        and r["data"]["kind"] == kind
                        and r["data"]["label"] == "candidate"
                    ]
                    if checks:
                        # Every configured check of this kind must pass in the final verification.
                        names = {c.name for c in self.project.checks if c.kind == kind}
                        latest = {r["data"]["name"]: r["status"] for r in checks}
                        result["acceptance"][kind] = (
                            "pass" if all(latest.get(n) == "pass" for n in names) else "fail"
                        )
                if self.workspace.base_sha and self.workspace.root.exists():
                    result["diff_ref"] = self.journal.artifact({"patch": self.workspace.diff()})
                    result["changed_files"] = git(
                        self.workspace.root, "diff", "--name-only", self.workspace.base_sha
                    ).splitlines()
                    result["protected_files_changed"] = [
                        n for n in result["changed_files"] if n in self.project.approved_test_paths
                    ]
                    result["task_commit"] = git(self.workspace.root, "rev-parse", "HEAD")
                ref = self.journal.artifact(result)
                self.journal.emit("FINAL", status=result["status"], evidence_ref=ref)
            except (OSError, NeedsUser, ValueError):
                # Do not replace an earlier durable record when reporting itself fails.
                result["status"] = str(Outcome.NEEDS_USER)
                result["detail"] = "Could not safely persist report; inspect task journal"
        return result
