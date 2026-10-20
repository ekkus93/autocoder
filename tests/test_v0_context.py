import asyncio
import json
from pathlib import Path

import pytest

from autocoder.fixtures import Fixture
from autocoder.v0.cli import journal_for
from autocoder.v0.coordinator import Coordinator
from autocoder.v0.gateway import ToolGateway
from autocoder.v0.schema import Check, Orientation, Phase, Project


def coordinator_for(repository, temporary, transport, *, edit_helper=False):
    project = Project(
        repository=repository,
        state_dir=temporary / "state",
        readable_paths=["source.py", "helper.py"],
        editable_paths=["source.py", "helper.py"] if edit_helper else ["source.py"],
        checks=[Check(name="unit", command=["/usr/bin/true"])],
        context=16384,
    )
    journal = journal_for(project, "c" * 32, create=True)
    controller = Coordinator(project, journal, transport=transport)
    controller.workspace.create()
    controller.gateway = ToolGateway(controller.workspace, controller.budget, None)
    controller.transition(Phase.ORIENT)
    return controller


def answer(message):
    return {
        "message": message,
        "prompt_tokens": 10,
        "output_tokens": 10,
        "truncated": False,
        "finished": True,
    }


def test_orientation_hands_off_before_native_tool_history_exceeds_context(tmp_path):
    source = "".join(f"# line {i:03}: " + "a" * 100 + "\n" for i in range(200))
    with Fixture({"source.py": source, "helper.py": source}) as fixture:
        calls = []

        async def transport(endpoint, model, messages, budget, **options):
            calls.append(options.get("tools") is not None)
            if options.get("tools"):
                assert calls == [True], "Oversized history should transition to a fresh handoff"
                return answer(
                    {
                        "content": "I am examining the relevant source. " * 80,
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "read_file_range",
                                    "arguments": {"path": "source.py", "start": 80, "end": 115},
                                }
                            }
                        ],
                    }
                )
            assert len(messages) == 2
            evidence = json.loads(messages[1]["content"])["evidence"]
            assert "source" not in evidence["last_retrieval"][0]
            frame = evidence["files"]["source.py"]
            assert frame["start"] == 80
            return answer(
                {
                    "content": json.dumps(
                        {
                            "base_sha": evidence["base_sha"],
                            "findings": [
                                {
                                    "path": "source.py",
                                    "sha256": frame["sha256"],
                                    "start": 80,
                                    "end": 81,
                                    "summary": "Relevant current source",
                                }
                            ],
                        }
                    )
                }
            )

        controller = coordinator_for(fixture.repository, tmp_path, transport)
        artifact = asyncio.run(controller.orient("Locate the source defect"))
        assert artifact.findings[0].start == 80
        assert calls == [True, False]
        resets = [row for row in controller.journal.read() if row["kind"] == "CONTEXT_RESET"]
        assert len(resets) == 1 and "orientation history" in resets[0]["data"]["reason"]


def test_qualified_method_focus_survives_unrelated_orientation_reads(tmp_path):
    source = (
        "class Client:\n"
        "    def consume(self, row):\n"
        '        self.status = row.get("status")\n'
        "\n"
        "def run():\n"
        + "".join("    # unrelated " + "x" * 80 + "\n" for _ in range(200))
        + "    pass\n"
    )
    helper = "".join("# helper " + "y" * 100 + "\n" for _ in range(200))
    with Fixture({"source.py": source, "helper.py": helper}) as fixture:
        discovery = 0

        async def transport(endpoint, model, messages, budget, **options):
            nonlocal discovery
            evidence = json.loads(messages[1]["content"])["evidence"]
            if options.get("tools") and discovery == 0:
                discovery += 1
                return answer(
                    {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "read_file_range",
                                    "arguments": {"path": "source.py", "start": 80, "end": 90},
                                }
                            }
                        ]
                    }
                )
            if options.get("tools"):
                return answer({"content": "Enough source retrieved"})
            frame = evidence["files"]["source.py"]
            assert frame["focused_symbol"] is True
            assert frame["start"] == 2 and frame["end"] == 3
            assert "def consume" in frame["source"] and "unrelated" not in frame["source"]
            return answer(
                {
                    "content": json.dumps(
                        {
                            "base_sha": evidence["base_sha"],
                            "findings": [
                                {
                                    "path": "source.py",
                                    "sha256": frame["sha256"],
                                    "start": 2,
                                    "end": 3,
                                    "summary": "Missing phase update",
                                }
                            ],
                        }
                    )
                }
            )

        controller = coordinator_for(fixture.repository, tmp_path, transport)
        artifact = asyncio.run(controller.orient("Fix Client.consume, then run all checks."))
        assert artifact.findings[0].start == 2


@pytest.mark.parametrize("observed_companion", [True, False])
def test_plan_companion_paths_require_actual_prior_source_observation(tmp_path, observed_companion):
    with Fixture({"source.py": "VALUE = 1\n", "helper.py": "OTHER = 2\n"}) as fixture:

        async def transport(endpoint, model, messages, budget, **options):
            evidence = json.loads(messages[1]["content"])["evidence"]
            allowed = {"source.py", "helper.py"} if observed_companion else {"source.py"}
            assert set(options["schema"]["properties"]["paths"]["items"]["enum"]) == allowed
            return answer(
                {
                    "content": json.dumps(
                        {
                            "base_sha": evidence["base_sha"],
                            "paths": ["source.py", "helper.py"],
                            "steps": ["Fix source and add companion coverage"],
                            "checks": ["unit"],
                        }
                    )
                }
            )

        controller = coordinator_for(fixture.repository, tmp_path, transport, edit_helper=True)
        evidence = controller.gateway.evidence(None if observed_companion else ["source.py"])
        frame = evidence["files"]["source.py"]
        findings = Orientation.model_validate(
            {
                "base_sha": evidence["base_sha"],
                "findings": [
                    {
                        "path": "source.py",
                        "sha256": frame["sha256"],
                        "start": 1,
                        "end": 1,
                        "summary": "Source needs a fix",
                    }
                ],
            }
        )
        controller.transition(Phase.REPRODUCE_AND_PLAN)
        if observed_companion:
            plan = asyncio.run(controller.plan("Fix source with companion tests", findings, []))
            assert plan.paths == ["source.py", "helper.py"]
        else:
            with pytest.raises(ValueError, match="Invalid phase artifact"):
                asyncio.run(controller.plan("Fix source with companion tests", findings, []))


@pytest.mark.parametrize("correct_patch", [True, False])
def test_edited_candidate_is_verified_when_another_inference_cannot_be_reserved(
    tmp_path, correct_patch
):
    from test_v0 import FIXED, SOURCE, fake_model, project_for

    from autocoder.v0.cli import start

    with Fixture({"greeting.py": SOURCE}) as fixture:
        project = project_for(fixture.repository, tmp_path)
        base = fake_model([])
        implementations = 0

        async def transport(endpoint, model, messages, budget, **options):
            nonlocal implementations
            result = await base(endpoint, model, messages, budget, **options)
            if json.loads(messages[1]["content"])["phase"] == "IMPLEMENT":
                implementations += 1
                assert implementations == 1
                if not correct_patch:
                    args = result["message"]["tool_calls"][0]["function"]["arguments"]
                    args["new"] = 'def greet(name):\n    return "Still broken"\n'
                remaining = project.limits.request_tokens - budget.snapshot().request_tokens
                budget.consume(request_tokens=remaining - 100)
            return result

        result = start(project, "Fix greet", transport=transport, metadata=False)
        assert result["status"] == ("VERIFIED_LOCAL" if correct_patch else "BUDGET_EXHAUSTED"), (
            result
        )
        assert result["acceptance"]["tests"] == ("pass" if correct_patch else "fail")
        assert implementations == 1
        assert result["usage"]["request_tokens"] <= project.limits.request_tokens
        assert (fixture.repository / "greeting.py").read_text() == SOURCE
        journal = journal_for(project, result["task_id"])
        assert any(row["kind"] == "VERIFY_WITHOUT_INFERENCE" for row in journal.read())
        if correct_patch:
            assert (Path(result["worktree"]) / "greeting.py").read_text() == FIXED


def test_repeated_orientation_read_transitions_to_a_validated_handoff(tmp_path):
    source = "".join("# source " + "x" * 60 + "\n" for _ in range(150))
    with Fixture({"source.py": source, "helper.py": source}) as fixture:
        discovery = 0

        async def transport(endpoint, model, messages, budget, **options):
            nonlocal discovery
            if options.get("tools"):
                discovery += 1
                assert discovery <= 2
                return answer(
                    {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "read_file_range",
                                    "arguments": {"path": "source.py", "start": 80, "end": 81},
                                }
                            }
                        ]
                    }
                )
            evidence = json.loads(messages[1]["content"])["evidence"]
            frame = evidence["files"]["source.py"]
            return answer(
                {
                    "content": json.dumps(
                        {
                            "base_sha": evidence["base_sha"],
                            "findings": [
                                {
                                    "path": "source.py",
                                    "sha256": frame["sha256"],
                                    "start": 80,
                                    "end": 81,
                                    "summary": "Current observed source",
                                }
                            ],
                        }
                    )
                }
            )

        controller = coordinator_for(fixture.repository, tmp_path, transport)
        result = asyncio.run(controller.orient("Locate the source defect"))
        assert result.findings[0].start == 80
        rows = controller.journal.read()
        assert len([row for row in rows if row["kind"] == "TOOL_CALL"]) == 1
        assert any(row["kind"] == "REPETITION_STOP" for row in rows)


def test_repeated_implementation_read_verifies_then_uses_bounded_repair(tmp_path):
    from test_v0 import SOURCE, fake_model, project_for

    from autocoder.v0.cli import start

    with Fixture({"greeting.py": SOURCE}) as fixture:
        project = project_for(fixture.repository, tmp_path)
        base = fake_model([])

        async def transport(endpoint, model, messages, budget, **options):
            if json.loads(messages[1]["content"])["phase"] == "IMPLEMENT":
                return answer(
                    {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "read_file_range",
                                    "arguments": {"path": "greeting.py", "start": 1, "end": 2},
                                }
                            }
                        ]
                    }
                )
            return await base(endpoint, model, messages, budget, **options)

        result = start(project, "Fix greet", transport=transport, metadata=False)
        assert result["status"] == "VERIFIED_LOCAL", result
        assert result["usage"]["repairs"] == 1
        assert (fixture.repository / "greeting.py").read_text() == SOURCE
        journal = journal_for(project, result["task_id"])
        checks = [
            row["status"]
            for row in journal.read()
            if row["kind"] == "CHECK" and row["data"]["label"] == "candidate"
        ]
        assert checks == ["fail", "pass"]
        assert any(row["kind"] == "REPETITION_STOP" for row in journal.read())


def test_compaction_preserves_edit_progress_and_dates_the_old_diagnostic(tmp_path):
    from autocoder.protocol import digest
    from autocoder.v0.schema import Plan

    source = "VALUE = 1\n" + "".join("# padding " + "x" * 80 + "\n" for _ in range(150))
    with Fixture({"source.py": source, "helper.py": source}) as fixture:
        calls = 0

        async def transport(endpoint, model, messages, budget, **options):
            nonlocal calls
            calls += 1
            body = json.loads(messages[1]["content"])
            if calls == 1:
                rendered = len(
                    json.dumps(
                        {"messages": messages, "tools": options["tools"], "schema": None}
                    ).encode()
                )
                remaining = rendered - 1000
                budget.consume(request_tokens=budget.limits.request_tokens - remaining)
                return answer(
                    {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "apply_edit",
                                    "arguments": {
                                        "path": "source.py",
                                        "old": "VALUE = 1",
                                        "new": "VALUE = 2",
                                        "expected_sha256": digest(source.encode()),
                                    },
                                }
                            }
                        ]
                    }
                )
            assert calls == 2
            evidence = body["evidence"]
            assert evidence["changed_paths"] == ["source.py"]
            assert evidence["unchanged_planned_paths"] == ["helper.py"]
            assert evidence["historical_diagnostic_before_edits"] == "previous failing check"
            assert "diagnostic" not in body
            assert "source_omitted" in evidence["files"]["source.py"]
            assert evidence["files"]["helper.py"]["source"]
            assert evidence["completed_operation_summaries"][0]["path"] == "source.py"
            return answer({"content": "Proceed to deterministic verification"})

        controller = coordinator_for(fixture.repository, tmp_path, transport, edit_helper=True)
        controller.transition(Phase.REPRODUCE_AND_PLAN)
        controller.transition(Phase.IMPLEMENT)
        plan = Plan(
            base_sha=controller.workspace.base_sha,
            paths=["source.py", "helper.py"],
            steps=["Update the files"],
            checks=["unit"],
        )
        asyncio.run(
            controller.implement("Update source and companion", plan, "previous failing check")
        )
        assert calls == 2
        assert (controller.workspace.root / "source.py").read_text().startswith("VALUE = 2")
