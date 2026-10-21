import asyncio
import json
from pathlib import Path

import pytest

from autocoder.fixtures import Fixture
from autocoder.v0.cli import journal_for
from autocoder.v0.coordinator import Coordinator
from autocoder.v0.gateway import ToolGateway
from autocoder.v0.schema import Check, Orientation, Phase, Project


def test_empty_file_read_range(tmp_path):
    from autocoder.protocol import digest

    normal = "VALUE = 1\nVALUE = 2\n"
    with Fixture({"source.py": "", "helper.py": normal}) as fixture:
        controller = coordinator_for(fixture.repository, tmp_path, None)
        gateway = controller.gateway
        for end in (1, 2, 120):
            result = gateway.read("source.py", start=1, end=end)
            assert result["start"] == result["end"] == 1
            assert result["total_lines"] == 0
            assert result["source"] == ""
            assert result["sha256"] == digest(b"")
            assert result["base_sha"] == controller.workspace.base_sha
            assert not result["truncated"]

        for start, end in ((2, 2), (100, 100), (0, 1), (1, 121), (2, 1)):
            with pytest.raises(ValueError, match="Read range must be at most 120"):
                gateway.read("source.py", start=start, end=end)

        result = gateway.read("helper.py", start=1, end=120)
        assert result["source"] == normal.rstrip("\n")
        assert result["start"] == 1 and result["end"] == result["total_lines"] == 2
        assert result["sha256"] == digest(normal.encode())
        assert gateway.read("helper.py", start=2, end=2)["source"] == "VALUE = 2"
        with pytest.raises(ValueError, match="Read range must be at most 120"):
            gateway.read("helper.py", start=3, end=3)
        with pytest.raises(ValueError, match="Path is not approved"):
            gateway.read("unapproved.py")


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
                            "findings": [
                                {
                                    "path": "source.py",
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
        assert artifact.base_sha == controller.workspace.base_sha
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
                            "findings": [
                                {
                                    "path": "source.py",
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
            allowed = {"source.py", "helper.py"} if observed_companion else {"source.py"}
            assert set(options["schema"]["properties"]["paths"]["items"]["enum"]) == allowed
            return answer(
                {
                    "content": json.dumps(
                        {
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
            return answer(
                {
                    "content": json.dumps(
                        {
                            "findings": [
                                {
                                    "path": "source.py",
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


def test_setup_examples_use_approved_baseline_and_survive_refreshed_source(tmp_path):
    from autocoder.tool_schema import Edit

    test_source = (
        "\n\ndef helper(repository, temporary):\n    pass\n"
        + "# padding\n" * 150
        + """
def test_existing(tmp_path):
    with Fixture({"source.py": "VALUE = 1"}) as fixture:
        controller = helper(fixture.repository, tmp_path)
        assert controller
"""
    )
    with Fixture({"source.py": "VALUE = 1\n", "tests/test_sample.py": test_source}) as fixture:
        project = Project(
            repository=fixture.repository,
            state_dir=tmp_path / "state",
            readable_paths=["source.py", "tests/test_sample.py"],
            editable_paths=["tests/test_sample.py"],
            approved_test_paths=["tests/test_sample.py"],
            checks=[Check(name="unit", command=["/usr/bin/true"])],
        )
        journal = journal_for(project, "d" * 32, create=True)
        controller = Coordinator(project, journal)
        controller.workspace.create()
        controller.gateway = ToolGateway(controller.workspace, controller.budget, None)
        evidence = controller.implementation_evidence(["tests/test_sample.py"], "Add a test")
        frame = evidence["files"]["tests/test_sample.py"]
        example = frame["test_setup_example"]
        assert "helper(fixture.repository, tmp_path)" in example["source"]
        assert example["base_sha"] == controller.workspace.base_sha
        assert len(frame["source"]) + len(example["source"]) <= 3000
        assert example["start"] > 120
        controller.workspace.edit(
            Edit(
                path="tests/test_sample.py",
                old="        assert controller",
                new=(
                    "        assert controller\n\ndef test_bad(tmp_path):\n"
                    "    with Fixture({}) as wrong:\n        helper(tmp_path, tmp_path)\n"
                ),
                expected_sha256=frame["sha256"],
            )
        )
        controller.source_ranges["tests/test_sample.py"] = (1, 10)
        controller.gateway = ToolGateway(controller.workspace, controller.budget, None)
        refreshed = controller.implementation_evidence(["tests/test_sample.py"], "Add a test")
        assert refreshed["files"]["tests/test_sample.py"]["test_setup_example"] == example
        assert "wrong" not in example["source"]
        assert list(controller.implementation_evidence(["source.py"], "Fix source")["files"]) == [
            "source.py"
        ]


def test_test_edit_returns_to_verification_before_another_inference(tmp_path):
    from autocoder.protocol import digest
    from autocoder.v0.schema import Plan

    with Fixture(
        {"source.py": "VALUE = 1\n", "tests/test_sample.py": "# new test here\n"}
    ) as fixture:
        project = Project(
            repository=fixture.repository,
            state_dir=tmp_path / "state",
            readable_paths=["source.py", "tests/test_sample.py"],
            editable_paths=["tests/test_sample.py"],
            approved_test_paths=["tests/test_sample.py"],
            checks=[Check(name="unit", command=["/usr/bin/true"])],
        )
        journal = journal_for(project, "e" * 32, create=True)
        calls = 0

        async def transport(*args, **kwargs):
            nonlocal calls
            calls += 1
            assert calls == 1, "Tests must be checked before another inference"
            return answer(
                {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "apply_edit",
                                "arguments": {
                                    "path": "tests/test_sample.py",
                                    "old": "# new test here",
                                    "new": "def test_new():\n    assert True",
                                    "expected_sha256": digest(b"# new test here\n"),
                                },
                            }
                        }
                    ]
                }
            )

        controller = Coordinator(project, journal, transport=transport)
        controller.workspace.create()
        controller.gateway = ToolGateway(controller.workspace, controller.budget, None)
        controller.phase = Phase.IMPLEMENT
        plan = Plan(
            base_sha=controller.workspace.base_sha,
            paths=["tests/test_sample.py"],
            steps=["Add test"],
            checks=["unit"],
        )
        asyncio.run(controller.implement("Add regression", plan, "old failure"))
        assert calls == 1
        assert any(r["kind"] == "EARLY_TEST_VERIFICATION" for r in journal.read())


def test_changed_public_failure_gets_focused_repair_before_replan(tmp_path):
    from test_v0 import FIXED, SOURCE, fake_model, project_for

    from autocoder.v0.cli import start

    with Fixture({"greeting.py": SOURCE}) as fixture:
        project = project_for(fixture.repository, tmp_path)
        check = project.checks[0].model_copy(
            update={
                "command": [
                    "/usr/bin/python3",
                    "-I",
                    "-c",
                    'import sys; sys.path.insert(0,"/work"); from greeting import greet; '
                    'value=greet("Ada"); '
                    'assert value=="Hello, Ada!", "greeting regression: "+value',
                ]
            }
        )
        project = project.model_copy(update={"checks": [check]})
        base = fake_model([])
        attempts = 0

        async def transport(endpoint, model, messages, budget, **options):
            nonlocal attempts
            body = json.loads(messages[1]["content"])
            if body["phase"] in {"IMPLEMENT", "REPAIR"}:
                if any(m["role"] == "tool" for m in messages):
                    return answer({"content": "verify"})
                attempts += 1
                frame = body["evidence"]["files"]["greeting.py"]
                new = (
                    FIXED if attempts == 3 else f'def greet(name):\n    return "wrong {attempts}"\n'
                )
                return answer(
                    {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "apply_edit",
                                    "arguments": {
                                        "path": "greeting.py",
                                        "old": frame["source"],
                                        "new": new.rstrip("\n"),
                                        "expected_sha256": frame["sha256"],
                                    },
                                }
                            }
                        ]
                    }
                )
            assert attempts == 0, "Changed diagnostics should not restart orientation"
            return await base(endpoint, model, messages, budget, **options)

        result = start(project, "Fix greet", transport=transport, metadata=False)
        assert result["status"] == "VERIFIED_LOCAL", result
        assert result["usage"]["repairs"] == 2
        journal = journal_for(project, result["task_id"])
        assert not any(r["kind"] == "REPLAN" for r in journal.read())


@pytest.mark.parametrize("citation", ["valid", "unread_range", "unknown_file"])
def test_truncated_discovery_discards_calls_and_builds_validated_handoff(tmp_path, citation):
    from autocoder.protocol import digest

    source = "".join(f"# line {i}\n" for i in range(160))
    with Fixture({"source.py": source, "helper.py": source}) as fixture:
        discovery_calls = 0
        diagnostics = []

        async def transport(endpoint, model, messages, budget, **options):
            nonlocal discovery_calls
            if options.get("tools"):
                discovery_calls += 1
                assert discovery_calls <= 2
                result = answer(
                    {
                        "content": "incomplete discovery" if discovery_calls == 2 else "read",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "read_file_range",
                                    "arguments": {
                                        "path": "helper.py"
                                        if discovery_calls == 2
                                        else "source.py",
                                        "start": 140,
                                        "end": 141,
                                    },
                                }
                            }
                        ],
                    }
                )
                result["truncated"] = discovery_calls == 2
                return result
            assert len(messages) == 2
            assert "incomplete discovery" not in json.dumps(messages)
            evidence = json.loads(messages[1]["content"])["evidence"]
            frame = evidence["files"]["source.py"]
            assert frame["start"] == 140
            assert evidence["files"]["helper.py"]["start"] == 1
            diagnostics.append(json.loads(messages[1]["content"]).get("diagnostic"))
            return answer(
                {
                    "content": json.dumps(
                        {
                            "findings": [
                                {
                                    "path": "other.py"
                                    if citation == "unknown_file"
                                    else "source.py",
                                    "start": 150 if citation == "unread_range" else 140,
                                    "end": 151 if citation == "unread_range" else 141,
                                    "summary": "Observed source",
                                }
                            ],
                        }
                    )
                }
            )

        controller = coordinator_for(fixture.repository, tmp_path, transport)
        if citation != "valid":
            with pytest.raises(ValueError, match="Invalid phase artifact"):
                asyncio.run(controller.orient("Locate the defect"))
            # The single repair attempt is told the real line count and the shown ranges.
            assert diagnostics[0] is None and len(diagnostics) == 2
            assert "repeat every other finding unchanged" in diagnostics[1]
            if citation == "unread_range":
                for expected in ("source.py lines 150-151", "the file has 160 lines", "140-141"):
                    assert expected in diagnostics[1], diagnostics[1]
            else:
                assert "other.py was not observed" in diagnostics[1], diagnostics[1]
                assert "source.py" in diagnostics[1]
        else:
            findings = asyncio.run(controller.orient("Locate the defect"))
            assert findings.findings[0].start == 140
            # The coordinator supplies the digest from the file it observed.
            assert findings.findings[0].sha256 == digest(source.encode())
        rows = controller.journal.read()
        assert len([r for r in rows if r["kind"] == "TOOL_CALL"]) == 1
        assert len([r for r in rows if r["kind"] == "INCOMPLETE_RESPONSE"]) == 1


def test_style_only_failures_stay_in_focused_repair(tmp_path):
    from test_v0 import FIXED, SOURCE, fake_model, project_for

    from autocoder.v0.cli import start

    long_comment = "# " + "x" * 110
    with Fixture({"greeting.py": SOURCE}) as fixture:
        project = project_for(fixture.repository, tmp_path)
        lint = Check(
            name="style",
            kind="lint",
            command=[
                "/usr/bin/python3",
                "-I",
                "-c",
                "from pathlib import Path; "
                "lines = Path('/work/greeting.py').read_text().splitlines(); "
                "assert all(len(line)<=100 for line in lines), 'style regression'",
            ],
        )
        project = project.model_copy(update={"checks": [*project.checks, lint]})
        base = fake_model([])
        repair_attempts = 0
        implementation_started = False

        async def transport(endpoint, model, messages, budget, **options):
            nonlocal repair_attempts, implementation_started
            body = json.loads(messages[1]["content"])
            if body["phase"] in {"IMPLEMENT", "REPAIR"}:
                if any(m["role"] == "tool" for m in messages):
                    return answer({"content": "verify"})
                frame = body["evidence"]["files"]["greeting.py"]
                if body["phase"] == "IMPLEMENT":
                    implementation_started = True
                    old, new = frame["source"], (FIXED + long_comment).rstrip("\n")
                else:
                    repair_attempts += 1
                    if repair_attempts == 1:
                        return answer({"content": "verify"})
                    old, new = long_comment, "# concise"
                return answer(
                    {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "apply_edit",
                                    "arguments": {
                                        "path": "greeting.py",
                                        "old": old,
                                        "new": new,
                                        "expected_sha256": frame["sha256"],
                                    },
                                }
                            }
                        ]
                    }
                )
            assert not implementation_started, "Style failures must not restart orientation"
            response = await base(endpoint, model, messages, budget, **options)
            if body["phase"] == "REPRODUCE_AND_PLAN":
                plan = json.loads(response["message"]["content"])
                plan["checks"] = ["greeting", "style"]
                response["message"]["content"] = json.dumps(plan)
            return response

        result = start(project, "Fix greet", transport=transport, metadata=False)
        assert result["status"] == "VERIFIED_LOCAL", result
        assert result["usage"]["repairs"] == 2
        assert repair_attempts == 2
        assert not any(
            r["kind"] == "REPLAN" for r in journal_for(project, result["task_id"]).read()
        )
