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


@pytest.mark.parametrize("correct_patch", [True, False])
@pytest.mark.parametrize("unfinished", [True, False])
def test_incomplete_response_discards_calls_and_verifies_prior_edits(
    tmp_path, correct_patch, unfinished
):
    from test_v0 import FIXED, SOURCE, fake_model, project_for

    from autocoder.protocol import digest
    from autocoder.v0.cli import start

    with Fixture({"greeting.py": SOURCE}) as fixture:
        project = project_for(fixture.repository, tmp_path)
        base = fake_model([])
        implementation_calls = 0
        repair_calls = 0

        async def transport(endpoint, model, messages, budget, **options):
            nonlocal implementation_calls, repair_calls
            body = json.loads(messages[1]["content"])
            phase = body["phase"]
            if phase == "REPAIR":
                repair_calls += 1
                assert len(messages) == (2 if repair_calls == 1 else 4)
                assert "greeting regression" in body["diagnostic"]
                assert "TRUNCATED RESPONSE" not in json.dumps(messages)
                current = body["evidence"]["files"]["greeting.py"]
                if repair_calls == 1:
                    return answer(
                        {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "apply_edit",
                                        "arguments": {
                                            "path": "greeting.py",
                                            "old": current["source"],
                                            "new": FIXED.rstrip("\n"),
                                            "expected_sha256": current["sha256"],
                                        },
                                    }
                                }
                            ]
                        }
                    )
                return answer({"content": "Ready"})
            result = await base(endpoint, model, messages, budget, **options)
            if phase == "IMPLEMENT":
                implementation_calls += 1
                if implementation_calls == 1 and not correct_patch:
                    result["message"]["tool_calls"][0]["function"]["arguments"]["new"] = (
                        SOURCE.replace("Hello!", "Still broken")
                    )
                if implementation_calls == 2:
                    # Even a syntactically complete call in an incomplete response is discarded.
                    current = FIXED if correct_patch else SOURCE.replace("Hello!", "Still broken")
                    result["message"] = {
                        "content": "TRUNCATED RESPONSE",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "apply_edit",
                                    "arguments": {
                                        "path": "greeting.py",
                                        "old": current,
                                        "new": "raise RuntimeError\n",
                                        "expected_sha256": digest(current.encode()),
                                    },
                                },
                            }
                        ],
                    }
                    result["finished"] = not unfinished
                    result["truncated"] = not unfinished
            return result

        result = start(project, "Fix greet", transport=transport, metadata=False)
        assert result["status"] == "VERIFIED_LOCAL", result
        assert implementation_calls == 2
        assert result["usage"]["repairs"] == (0 if correct_patch else 1)
        assert (fixture.repository / "greeting.py").read_text() == SOURCE
        assert (Path(result["worktree"]) / "greeting.py").read_text() == FIXED
        journal = journal_for(project, result["task_id"])
        assert len([row for row in journal.read() if row["kind"] == "EDIT_OUTCOME"]) == (
            1 if correct_patch else 2
        )
        checks = [
            row["status"]
            for row in journal.read()
            if row["kind"] == "CHECK" and row["data"]["label"] == "candidate"
        ]
        assert checks == (["pass"] if correct_patch else ["fail", "pass"])
        assert any(row["kind"] == "INCOMPLETE_RESPONSE" for row in journal.read())


def test_repeated_incomplete_responses_without_edits_exhaust_repair_budget(tmp_path):
    from test_v0 import SOURCE, fake_model, project_for

    from autocoder.v0.cli import start

    with Fixture({"greeting.py": SOURCE}) as fixture:
        project = project_for(fixture.repository, tmp_path)
        project = project.model_copy(
            update={"limits": project.limits.model_copy(update={"repairs": 1})}
        )
        base = fake_model([])

        async def transport(endpoint, model, messages, budget, **options):
            phase = json.loads(messages[1]["content"])["phase"]
            if phase in {"IMPLEMENT", "REPAIR"}:
                budget.consume(request_tokens=10, output_tokens=10)
                result = answer({"content": "unfinished"})
                result["truncated"] = True
                return result
            return await base(endpoint, model, messages, budget, **options)

        result = start(project, "Fix greet", transport=transport, metadata=False)
        assert result["status"] == "BUDGET_EXHAUSTED", result
        assert result["detail"] == "repairs"
        assert result["acceptance"]["tests"] == "fail"
        assert result["usage"]["repairs"] == 1
        assert result["changed_files"] == []
        journal = journal_for(project, result["task_id"])
        assert len([row for row in journal.read() if row["kind"] == "INCOMPLETE_RESPONSE"]) == 2


def test_repair_diagnostic_shares_space_between_all_public_failures():
    from autocoder.v0.verification import diagnostic

    records = []
    for i in range(12):
        records.append(
            {
                "name": f"failure-{i}",
                "execution": {
                    "status": "finished",
                    "exit_code": 1,
                    "truncated": False,
                    "stderr": f"stderr-{i}:" + "x" * 10000,
                    "stdout": f"stdout-{i}:" + "y" * 10000,
                },
            }
        )
    result = diagnostic(records)
    assert len(result) <= 4096
    for i in range(12):
        assert f"Check failure-{i} exited 1" in result
        assert f"stderr-{i}:" in result
        assert f"stdout-{i}:" in result
    records[0]["integrity_changes"] = ["source.py"]
    records[1]["execution"].update(exit_code=0, truncated=True)
    result = diagnostic(records)
    assert "Verification changed tracked inputs: source.py" in result
    assert "Check failure-1 exited 0" in result
    assert "truncated" in result
    assert "Check failure-11 exited 1" in result
    assert len(result) <= 4096
    assert diagnostic([]) == ""
    assert (
        diagnostic(
            [
                {
                    "name": "passing",
                    "execution": {
                        "status": "finished",
                        "exit_code": 0,
                        "truncated": False,
                        "stderr": "passing diagnostics",
                        "stdout": "passing output",
                    },
                }
            ]
        )
        == ""
    )


@pytest.mark.parametrize("shrink", [False, True])
def test_repair_reuses_last_observed_range_with_current_source_and_planned_scope(tmp_path, shrink):
    from autocoder.protocol import digest
    from autocoder.v0.schema import Plan

    helper = "# padding\n" * 154 + "VALUE = 1\n# useful companion\n"
    updated = "VALUE = 2\n" if shrink else helper.replace("VALUE = 1", "VALUE = 2")
    with Fixture({"source.py": "VALUE = 1\n", "helper.py": helper}) as fixture:
        calls = 0

        async def transport(endpoint, model, messages, budget, **options):
            nonlocal calls
            calls += 1
            body = json.loads(messages[1]["content"])
            if calls == 1:
                return answer(
                    {
                        "content": "earlier assistant text must not cross phases",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "read_file_range",
                                    "arguments": {
                                        "path": "helper.py",
                                        "start": 155,
                                        "end": 156,
                                    },
                                },
                            }
                        ],
                    }
                )
            if calls == 2:
                return answer(
                    {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "apply_edit",
                                    "arguments": {
                                        "path": "helper.py",
                                        "old": helper,
                                        "new": updated,
                                        "expected_sha256": digest(helper.encode()),
                                    },
                                }
                            }
                        ]
                    }
                )
            if calls == 3:
                return answer({"content": "verify"})
            assert len(messages) == 2
            assert "earlier assistant text must not cross phases" not in json.dumps(messages)
            files = body["evidence"]["files"]
            if calls == 4:
                frame = files["helper.py"]
                assert frame["start"] == (1 if shrink else 155)
                assert frame["sha256"] == digest(updated.encode())
                assert "VALUE = 2" in frame["source"]
                assert "VALUE = 1" not in frame["source"]
                assert frame["end"] - frame["start"] < 120
                assert len(frame["source"]) <= 4000
                assert body["diagnostic"] == "current failures"
            else:
                assert calls == 5
                assert list(files) == ["source.py"], "Cached ranges must not add unplanned paths"
            return answer({"content": "verify"})

        controller = coordinator_for(fixture.repository, tmp_path, transport, edit_helper=True)
        controller.transition(Phase.REPRODUCE_AND_PLAN)
        controller.transition(Phase.IMPLEMENT)
        plan = Plan(
            base_sha=controller.workspace.base_sha,
            paths=["source.py", "helper.py"],
            steps=["Fix source and companion"],
            checks=["unit"],
        )
        asyncio.run(controller.implement("Fix the source", plan, "original failure"))
        controller.transition(Phase.VERIFY)
        controller.transition(Phase.REPAIR)
        asyncio.run(controller.implement("Fix the source", plan, "current failures"))
        asyncio.run(
            controller.implement(
                "Fix the source",
                plan.model_copy(update={"paths": ["source.py"]}),
                "current failures",
            )
        )
        assert calls == 5


def test_focused_method_context_includes_bounded_constructor_and_setup_without_imports(tmp_path):
    source = (
        'raise RuntimeError("must never import source")\n'
        "class Client:\n"
        "    def __init__(self, config):\n"
        "        self.config = config\n"
        "        self.prompt = None\n"
        "    def ask(self, kind, label):\n"
        "        self.prompt = kind\n"
        "    def consume(self, row):\n"
        "        return row\n"
        "class Unrelated:\n"
        "    def __init__(self, private_config):\n"
        "        self.value = private_config\n"
    )
    with Fixture({"source.py": source, "helper.py": "VALUE = 1\n"}) as fixture:
        controller = coordinator_for(fixture.repository, tmp_path, None)
        evidence = controller.gateway.evidence(["source.py"], request="Fix Client.consume")
        frame = evidence["files"]["source.py"]
        interface = frame["class_interface"]
        assert "def __init__(self, config)" in interface["source"]
        assert "self.prompt = None" in interface["source"]
        assert "def ask(self, kind, label)" in interface["source"]
        assert "self.prompt = kind" in interface["source"]
        assert "private_config" not in interface["source"]
        assert len(interface["source"]) <= 1200
        assert len(frame["source"]) + len(interface["source"]) <= 3000
        assert "def consume" in frame["source"]
        controller.gateway.read("source.py", 1, 1)
        refreshed = controller.gateway.evidence(["helper.py"], request="Fix Client.consume")
        assert "source.py" not in refreshed["files"]
        assert "class_interface" not in refreshed["files"]["helper.py"]
