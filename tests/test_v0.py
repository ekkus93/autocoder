import asyncio
import json
from pathlib import Path

import pytest

from autocoder.budget import Budget, BudgetExhausted
from autocoder.fixtures import Fixture
from autocoder.protocol import digest
from autocoder.tool_schema import Edit
from autocoder.v0.cli import directory, journal_for, policy_binding, start
from autocoder.v0.coordinator import Coordinator
from autocoder.v0.gateway import ToolGateway
from autocoder.v0.journal import Journal, NeedsUser
from autocoder.v0.model import ModelBackend, TaskBudget
from autocoder.v0.schema import Check, Oracle, Phase, Project
from autocoder.v0.verification import VerificationRunner
from autocoder.v0.workspace import Workspace, git

SOURCE = 'def greet(name):\n    return "Hello!"\n'
FIXED = 'def greet(name):\n    return "Hello, " + name + "!"\n'
PUBLIC = (
    'import sys; sys.path.insert(0,"/work"); from greeting import greet; '
    'assert greet("Ada") == "Hello, Ada!", "greeting regression"'
)


def project_for(repository, temporary, **overrides):
    fields = dict(
        repository=repository,
        state_dir=temporary / "state",
        readable_paths=["greeting.py"],
        editable_paths=["greeting.py"],
        checks=[
            Check(
                name="greeting",
                command=["/usr/bin/python3", "-I", "-c", PUBLIC],
                regression_pattern="greeting regression",
            )
        ],
    )
    fields.update(overrides)
    return Project(**fields)


def task(project, task_id="a" * 32):
    journal = journal_for(project, task_id, create=True)
    journal.emit(
        "CREATED",
        evidence_ref=journal.artifact(
            {"binding": policy_binding(project), "request": "Fix greeting"}
        ),
    )
    workspace = Workspace(project, journal)
    workspace.create()
    return journal, workspace


class PowerLoss(BaseException):
    pass


def test_atomic_edit_crash_reconciles_without_duplicate_mutation(tmp_path):
    with Fixture({"greeting.py": SOURCE}) as fixture:
        project = project_for(fixture.repository, tmp_path)
        journal, workspace = task(project)
        edit = Edit(
            path="greeting.py",
            old='"Hello!"',
            new='"Hello, " + name + "!"',
            expected_sha256=digest(SOURCE.encode()),
        )

        def crash():
            raise PowerLoss

        with pytest.raises(PowerLoss):
            workspace.edit(edit, after_replace=crash)
        assert not any(r["kind"] == "EDIT_OUTCOME" for r in journal.read())
        restored = Workspace(project, journal)
        restored.restore()
        assert (restored.root / "greeting.py").read_text() == FIXED
        outcomes = [r for r in journal.read() if r["kind"] == "EDIT_OUTCOME"]
        assert len(outcomes) == 1 and outcomes[0]["status"] == "reconciled_applied"
        restored.restore()
        assert len([r for r in journal.read() if r["kind"] == "EDIT_OUTCOME"]) == 1
        assert (fixture.repository / "greeting.py").read_text() == SOURCE
        assert "Hello" not in journal.path.read_text()


def test_commit_crash_is_observed_instead_of_committed_twice(tmp_path, monkeypatch):
    with Fixture({"greeting.py": SOURCE}) as fixture:
        project = project_for(fixture.repository, tmp_path)
        journal, workspace = task(project)
        workspace.edit(
            Edit(path="greeting.py", old=SOURCE, new=FIXED, expected_sha256=digest(SOURCE.encode()))
        )
        emit = journal.emit

        def interrupted(kind, **kwargs):
            if kind == "COMMIT_OUTCOME":
                raise PowerLoss
            return emit(kind, **kwargs)

        monkeypatch.setattr(journal, "emit", interrupted)
        with pytest.raises(PowerLoss):
            workspace.checkpoint()
        sha = git(workspace.root, "rev-parse", "HEAD")
        monkeypatch.setattr(journal, "emit", emit)
        restored = Workspace(project, journal)
        restored.restore()
        assert git(restored.root, "rev-parse", "HEAD") == sha
        assert journal.read()[-1]["kind"] == "COMMIT_OUTCOME"
        assert journal.read()[-1]["status"] == "reconciled"


def test_journal_lock_corruption_and_evidence_integrity(tmp_path):
    journal = Journal(tmp_path / "journal", "project", "task")
    key = journal.artifact({"a": 1})
    with journal.lock():
        with pytest.raises(NeedsUser, match="locked"):
            with journal.lock():
                pass
    journal.emit("TEST", evidence_ref=key)
    assert journal.load(key) == {"a": 1}
    path = journal.directory / "evidence" / (key + ".json")
    path.write_text("{}")
    with pytest.raises(NeedsUser, match="changed"):
        journal.load(key)
    with journal.path.open("ab") as handle:
        handle.write(b'{"torn":')
    with pytest.raises(NeedsUser, match="Torn"):
        journal.read()


def test_paths_protected_content_and_concurrent_writer_are_rejected(tmp_path):
    with Fixture({"greeting.py": SOURCE, "tests/test_greet.py": "assert True\n"}) as fixture:
        with pytest.raises(ValueError, match="approval"):
            project_for(
                fixture.repository,
                tmp_path,
                editable_paths=["tests/test_greet.py"],
                readable_paths=["tests/test_greet.py"],
            )
        project = project_for(fixture.repository, tmp_path)
        journal, workspace = task(project)
        for path in ("../other.py", "/tmp/other.py", ".git/config", "x/../greeting.py"):
            with pytest.raises(ValueError):
                workspace.edit(
                    Edit(path=path, old=SOURCE, new=FIXED, expected_sha256=digest(SOURCE.encode()))
                )
        original = workspace.root / "greeting.py"
        original.unlink()
        original.symlink_to(fixture.repository / "greeting.py")
        with pytest.raises(NeedsUser, match="Symlink"):
            workspace.restore()
        original.unlink()
        original.write_text(SOURCE)
        (workspace.root / "tests/test_greet.py").write_text("pass\n")
        with pytest.raises(NeedsUser, match="outside recorded"):
            workspace.assert_expected()
        assert (fixture.repository / "tests/test_greet.py").read_text() == "assert True\n"


def test_gateway_phase_scope_hash_and_repetition_limits(tmp_path):
    with Fixture({"greeting.py": SOURCE}) as fixture:
        project = project_for(fixture.repository, tmp_path)
        journal, workspace = task(project)
        budget = Budget(project.limits)
        gateway = ToolGateway(workspace, budget, VerificationRunner(workspace, budget))
        with pytest.raises(ValueError, match="phase"):
            gateway.dispatch("apply_edit", {})
        gateway.enter(Phase.IMPLEMENT, ["greeting.py"])
        result = gateway.dispatch(
            "apply_edit",
            {"path": "greeting.py", "old": SOURCE, "new": FIXED, "expected_sha256": "0" * 64},
        )
        assert "Stale" in result["error"]
        with pytest.raises(BudgetExhausted, match="duplicate"):
            gateway.dispatch(
                "apply_edit",
                {"path": "greeting.py", "old": SOURCE, "new": FIXED, "expected_sha256": "0" * 64},
            )
        assert (workspace.root / "greeting.py").read_text() == SOURCE
        with pytest.raises(ValueError):
            gateway.read("../secret", 1, 3)


def test_usage_reservations_survive_restart_and_cancellation(tmp_path):
    with Fixture({"greeting.py": SOURCE}) as fixture:
        project = project_for(
            fixture.repository, tmp_path, endpoint="http://reservation-test.invalid"
        )
        journal, workspace = task(project)
        budget = TaskBudget(project.limits, journal)
        budget.consume(request_tokens=100, output_tokens=50)
        restored = TaskBudget(project.limits, journal)
        assert restored.snapshot().request_tokens == 100
        assert restored.snapshot().output_tokens == 50

        async def stalled(endpoint, model, messages, budget, **kwargs):
            budget.consume(request_tokens=100, output_tokens=50)
            await asyncio.sleep(30)

        backend = ModelBackend(project, journal, restored, transport=stalled)

        async def cancel():
            job = asyncio.create_task(backend.request([{"role": "user", "content": "hello"}]))
            await asyncio.sleep(0.05)
            (journal.directory / "cancel").touch()
            with pytest.raises(asyncio.CancelledError):
                await job

        asyncio.run(cancel())
        assert TaskBudget(project.limits, journal).snapshot().request_tokens == 200


def fake_model(seen, *, malicious=False):
    async def transport(endpoint, model, messages, budget, **options):
        seen.append(messages)
        budget.consume(request_tokens=10, output_tokens=10)
        body = json.loads(messages[1]["content"])
        evidence = body["evidence"]
        phase = body["phase"]
        if phase == "ORIENT":
            source = evidence["files"]["greeting.py"]
            value = {
                "base_sha": evidence["base_sha"],
                "findings": [
                    {
                        "path": "greeting.py",
                        "sha256": source["sha256"],
                        "start": 1,
                        "end": 2,
                        "summary": "greet ignores its argument",
                    }
                ],
            }
            message = {"content": json.dumps(value)}
        elif phase == "REPRODUCE_AND_PLAN":
            value = {
                "base_sha": evidence["base_sha"],
                "paths": ["greeting.py"],
                "steps": ["Include the name"],
                "checks": ["greeting"],
            }
            message = {"content": json.dumps(value)}
        elif any(m["role"] == "tool" for m in messages):
            message = {"content": "Ready for deterministic verification"}
        elif evidence["files"]["greeting.py"]["sha256"] == digest(SOURCE.encode()):
            new = 'def greet(name):\n    return "Hello, Ada!"\n' if malicious else FIXED
            message = {
                "tool_calls": [
                    {
                        "function": {
                            "name": "apply_edit",
                            "arguments": {
                                "path": "greeting.py",
                                "old": SOURCE,
                                "new": new,
                                "expected_sha256": digest(SOURCE.encode()),
                            },
                        }
                    }
                ]
            }
        else:
            message = {"content": "Ready for deterministic verification"}
        return {
            "message": message,
            "prompt_tokens": 10,
            "output_tokens": 10,
            "finished": True,
            "truncated": False,
        }

    return transport


def test_full_loop_keeps_private_cases_out_of_prompts_and_original_checkout(tmp_path):
    with Fixture({"greeting.py": SOURCE, "tests/test_original.py": "assert True\n"}) as fixture:
        private = tmp_path / "private.json"
        private.write_text(
            json.dumps([{"args": ["PrivateToken731"], "expected": "Hello, PrivateToken731!"}])
        )
        project = project_for(
            fixture.repository,
            tmp_path,
            oracles=[Oracle(language="python", entry="greeting.greet", cases_file=private)],
        )
        seen = []
        result = start(
            project, "Fix greeting to include the name", transport=fake_model(seen), metadata=False
        )
        assert result["status"] == "VERIFIED_LOCAL", result
        assert result["acceptance"]["tests"] == "pass"
        assert result["acceptance"]["human_acceptance"] == "not_run"
        assert "PrivateToken731" not in json.dumps(seen)
        assert [len(messages) for messages in seen] == [2, 2, 2, 4]
        assert [json.loads(m[1]["content"])["phase"] for m in seen] == [
            "ORIENT",
            "REPRODUCE_AND_PLAN",
            "IMPLEMENT",
            "IMPLEMENT",
        ]
        assert (fixture.repository / "greeting.py").read_text() == SOURCE
        assert Path(result["worktree"]).exists()
        assert git(Path(result["worktree"]), "symbolic-ref", "--short", "HEAD") == result["branch"]
        assert result["task_commit"] != result["base_sha"]


def test_public_only_solution_fails_private_without_private_repair(tmp_path):
    with Fixture({"greeting.py": SOURCE}) as fixture:
        private = tmp_path / "private.json"
        private.write_text(
            json.dumps([{"args": ["RareInput918"], "expected": "Hello, RareInput918!"}])
        )
        project = project_for(
            fixture.repository,
            tmp_path,
            oracles=[Oracle(language="python", entry="greeting.greet", cases_file=private)],
        )
        seen = []
        result = start(
            project, "Fix greeting", transport=fake_model(seen, malicious=True), metadata=False
        )
        assert result["status"] == "FAILED_VERIFICATION", result
        assert "RareInput918" not in json.dumps(seen)
        assert len(seen) == 4
        assert result["task_commit"] == result["base_sha"]


def test_inconclusive_reproduction_and_invalid_transition_stop_before_model(tmp_path):
    with Fixture({"greeting.py": FIXED}) as fixture:
        project = project_for(fixture.repository, tmp_path)
        seen = []
        result = start(project, "Fix greeting", transport=fake_model(seen), metadata=False)
        assert result["status"] == "NEEDS_USER"
        assert not seen
        journal = journal_for(project, result["task_id"])
        coordinator = Coordinator(project, journal)
        with pytest.raises(ValueError, match="Invalid transition"):
            coordinator.transition(Phase.VERIFY)


def test_project_identity_separates_paths_and_journals(tmp_path):
    with Fixture({"greeting.py": SOURCE}) as a, Fixture({"greeting.py": SOURCE}) as b:
        pa, pb = project_for(a.repository, tmp_path), project_for(b.repository, tmp_path)
        ja, wa = task(pa)
        jb, wb = task(pb)
        assert ja.project_id != jb.project_id
        assert directory(pa, "a" * 32) != directory(pb, "a" * 32)
        ga = ToolGateway(wa, Budget(pa.limits), None)
        with pytest.raises(ValueError):
            ga.read(str(wb.root / "greeting.py"))
        assert not set(ja.read()[0]) - set(jb.read()[0])


def test_real_sigkill_after_replace_releases_lock_and_reconciles(tmp_path):
    import multiprocessing
    import os
    import signal

    with Fixture({"greeting.py": SOURCE}) as fixture:
        project = project_for(fixture.repository, tmp_path)
        journal, workspace = task(project)

        def child():
            with journal.lock():
                workspace.edit(
                    Edit(
                        path="greeting.py",
                        old=SOURCE,
                        new=FIXED,
                        expected_sha256=digest(SOURCE.encode()),
                    ),
                    after_replace=lambda: os.kill(os.getpid(), signal.SIGKILL),
                )

        process = multiprocessing.get_context("fork").Process(target=child)
        process.start()
        process.join(timeout=5)
        assert process.exitcode == -signal.SIGKILL
        with journal.lock():
            restored = Workspace(project, journal)
            restored.restore()
            assert (restored.root / "greeting.py").read_text() == FIXED
            assert len([r for r in journal.read() if r["kind"] == "EDIT_OUTCOME"]) == 1


def test_check_cannot_silently_modify_protected_snapshot_inputs(tmp_path):
    from autocoder.v0.verification import passed

    with Fixture({"greeting.py": SOURCE, "tests/test_original.py": "assert False\n"}) as fixture:
        hostile = Check(
            name="tamper",
            command=[
                "/usr/bin/python3",
                "-I",
                "-c",
                'from pathlib import Path; Path("tests/test_original.py").write_text("pass\\n")',
            ],
        )
        project = project_for(fixture.repository, tmp_path, checks=[hostile])
        journal, workspace = task(project)
        runner = VerificationRunner(workspace, Budget(project.limits))
        record = runner.run(hostile, "candidate")
        assert record["execution"]["exit_code"] == 0
        assert record["integrity_changes"] == ["tests/test_original.py"]
        assert not passed([record])
        assert (workspace.root / "tests/test_original.py").read_text() == "assert False\n"


def test_resume_rejects_changed_acceptance_assets_and_keeps_budget(tmp_path):
    from autocoder.v0.cli import resume

    with Fixture({"greeting.py": SOURCE}) as fixture:
        private = tmp_path / "cases.json"
        private.write_text('[{"args":["Z"],"expected":"Hello, Z!"}]')
        project = project_for(
            fixture.repository,
            tmp_path,
            oracles=[Oracle(language="python", entry="greeting.greet", cases_file=private)],
        )
        journal, workspace = task(project)
        TaskBudget(project.limits, journal).consume(request_tokens=123)
        private.write_text("[]")
        with pytest.raises(NeedsUser, match="acceptance assets changed"):
            resume(project, journal.task_id, metadata=False)
        assert TaskBudget(project.limits, journal).snapshot().request_tokens == 123


def test_phase_cap_and_context_reserve_stop_without_transport(tmp_path):
    with Fixture({"greeting.py": SOURCE}) as fixture:
        project = project_for(fixture.repository, tmp_path, phase_tool_calls=1)
        journal, workspace = task(project)
        budget = Budget(project.limits)
        gateway = ToolGateway(workspace, budget, None)
        gateway.dispatch("read_file_range", {"path": "greeting.py", "start": 1, "end": 2})
        with pytest.raises(BudgetExhausted, match="phase_tool_calls"):
            gateway.dispatch("read_file_range", {"path": "greeting.py", "start": 1, "end": 1})

        async def forbidden(*args, **kwargs):
            raise AssertionError("Must stop before transport")

        model = ModelBackend(project, journal, budget, transport=forbidden)
        with pytest.raises(BudgetExhausted, match="context reserve"):
            asyncio.run(model.request([{"role": "user", "content": "x" * 30000}]))


def test_full_loop_resume_after_sigkill_preserves_baseline_and_does_not_repeat_edit(tmp_path):
    import multiprocessing
    import os
    import signal

    from autocoder.v0.cli import resume

    with Fixture({"greeting.py": SOURCE}) as fixture:
        project = project_for(fixture.repository, tmp_path)

        def child():
            original = Workspace.edit

            def interrupted(self, edit, **kwargs):
                return original(
                    self, edit, after_replace=lambda: os.kill(os.getpid(), signal.SIGKILL)
                )

            Workspace.edit = interrupted
            start(project, "Fix greeting", transport=fake_model([]), metadata=False)

        process = multiprocessing.get_context("fork").Process(target=child)
        process.start()
        process.join(timeout=10)
        assert process.exitcode == -signal.SIGKILL
        tasks = list((project.state_dir / "projects" / project.project_id).iterdir())
        assert len(tasks) == 1
        result = resume(project, tasks[0].name, transport=fake_model([]), metadata=False)
        assert result["status"] == "VERIFIED_LOCAL", result
        journal = journal_for(project, result["task_id"])
        rows = journal.read()
        assert len([r for r in rows if r["kind"] == "EDIT_INTENT"]) == 1
        assert len([r for r in rows if r["kind"] == "EDIT_OUTCOME"]) == 1
        assert len([r for r in rows if r["kind"] == "COMMIT_OUTCOME"]) == 1
        assert result["usage"]["request_tokens"] >= 50
        assert (
            resume(project, result["task_id"], transport=fake_model([]), metadata=False) == result
        )


def test_inline_rust_tests_are_preserved_without_extra_file_approval(tmp_path):
    source = (
        "pub fn value() -> i32 { 1 }\n#[cfg(test)]\n"
        "mod tests { #[test] fn correct() { assert_eq!(super::value(), 2); } }\n"
    )
    with Fixture({"lib.rs": source}) as fixture:
        project = project_for(
            fixture.repository, tmp_path, readable_paths=["lib.rs"], editable_paths=["lib.rs"]
        )
        journal, workspace = task(project)
        with pytest.raises(ValueError, match="Embedded tests"):
            workspace.edit(
                Edit(
                    path="lib.rs",
                    old="assert_eq!(super::value(), 2)",
                    new="assert!(true)",
                    expected_sha256=digest(source.encode()),
                )
            )
        workspace.edit(
            Edit(path="lib.rs", old="{ 1 }", new="{ 2 }", expected_sha256=digest(source.encode()))
        )
        assert "#[test]" in (workspace.root / "lib.rs").read_text()


def test_focused_retrieval_anchors_a_named_function_beyond_the_prefix(tmp_path):
    source = "# padding\n" * 180 + SOURCE
    with Fixture({"greeting.py": source}) as fixture:
        project = project_for(fixture.repository, tmp_path)
        journal, workspace = task(project)
        gateway = ToolGateway(workspace, Budget(project.limits), None)
        evidence = gateway.evidence(request="Fix greet to include the name")
        excerpt = evidence["files"]["greeting.py"]
        assert excerpt["start"] == 181 and excerpt["end"] == 182
        assert excerpt["source"].startswith("def greet")
        assert excerpt["focused_symbol"] and not excerpt["truncated"]
        assert gateway.reads["greeting.py"] == [(181, 182, digest(source.encode()))]


def test_one_fresh_replan_after_two_public_failures(tmp_path):
    with Fixture({"greeting.py": SOURCE}) as fixture:
        project = project_for(fixture.repository, tmp_path)
        seen = []
        ordinary = fake_model(seen)

        async def transport(endpoint, model, messages, budget, **kwargs):
            body = json.loads(messages[1]["content"])
            phase = body["phase"]
            if phase in {"IMPLEMENT", "REPAIR"}:
                source = body["evidence"]["files"]["greeting.py"]
                old = source["source"]
                replacement = None
                if any(m["role"] == "tool" for m in messages):
                    replacement = None
                elif old == SOURCE.rstrip():
                    replacement = 'def greet(name):\n    return "Hello, Bob!"\n'
                elif phase == "REPAIR" and "Bob" in old:
                    replacement = 'def greet(name):\n    return "Hello, Carol!"\n'
                elif phase == "IMPLEMENT" and "Carol" in old:
                    replacement = FIXED
                message = {"content": "Ready"}
                if replacement:
                    message = {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "apply_edit",
                                    "arguments": {
                                        "path": "greeting.py",
                                        "old": old,
                                        "new": replacement,
                                        "expected_sha256": source["sha256"],
                                    },
                                }
                            }
                        ]
                    }
                return {
                    "message": message,
                    "prompt_tokens": 0,
                    "output_tokens": 0,
                    "finished": True,
                    "truncated": False,
                }
            return await ordinary(endpoint, model, messages, budget, **kwargs)

        result = start(project, "Fix greet", transport=transport, metadata=False)
        assert result["status"] == "VERIFIED_LOCAL", result
        rows = journal_for(project, result["task_id"]).read()
        assert len([r for r in rows if r["kind"] == "REPLAN"]) == 1
        assert result["usage"]["repairs"] == 2


def test_native_tool_observations_remain_in_phase_without_cross_phase_transcripts(tmp_path):
    with Fixture({"greeting.py": SOURCE}) as fixture:
        project = project_for(fixture.repository, tmp_path)
        seen = []
        base = fake_model(seen)
        stages = []

        async def transport(endpoint, model, messages, budget, **kwargs):
            body = json.loads(messages[1]["content"])
            if body["phase"] != "IMPLEMENT":
                assert len(messages) == 2
                return await base(endpoint, model, messages, budget, **kwargs)
            stages.append([m["role"] for m in messages])
            tools = [m for m in messages if m["role"] == "tool"]
            if not tools:
                name = "read_file_range"
                args = {"path": "greeting.py", "start": 1, "end": 2}
            elif len(tools) == 1:
                assert tools[0]["tool_name"] == "read_file_range"
                source = json.loads(tools[0]["content"])
                name = "apply_edit"
                args = {
                    "path": "greeting.py",
                    "old": SOURCE.rstrip(),
                    "new": FIXED.rstrip(),
                    "expected_sha256": source["sha256"],
                }
            else:
                assert tools[-1]["tool_name"] == "apply_edit"
                return {
                    "message": {"content": "Ready"},
                    "prompt_tokens": 0,
                    "output_tokens": 0,
                    "finished": True,
                    "truncated": False,
                }
            return {
                "message": {"tool_calls": [{"function": {"name": name, "arguments": args}}]},
                "prompt_tokens": 0,
                "output_tokens": 0,
                "finished": True,
                "truncated": False,
            }

        result = start(project, "Fix greet", transport=transport, metadata=False)
        assert result["status"] == "VERIFIED_LOCAL", result
        assert stages == [
            ["system", "user"],
            ["system", "user", "assistant", "tool"],
            ["system", "user", "assistant", "tool", "assistant", "tool"],
        ]


def test_policy_protects_rust_tests_configuration_and_explicit_protected_paths(tmp_path):
    from autocoder.v0.schema import protected

    for name in ("src/widget_test.rs", "src/tests.rs", "ruff.toml", "custom.yaml", "check.cfg"):
        assert protected(name)
    assert not protected("src/lib.rs")
    with Fixture({"greeting.py": SOURCE}) as fixture:
        with pytest.raises(ValueError, match="approval"):
            project_for(fixture.repository, tmp_path, protected_paths=["greeting.py"])
        project_for(
            fixture.repository,
            tmp_path,
            protected_paths=["greeting.py"],
            approved_test_paths=["greeting.py"],
        )


def test_private_oracle_imports_candidate_before_approved_runtime(tmp_path):
    from autocoder.v0.verification import directory_digest

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "greeting.py").write_text('def greet(name):\n    return "SHADOW"\n')
    private = tmp_path / "private.json"
    private.write_text('[{"args":["Q"],"expected":"Hello, Q!"}]')
    with Fixture({"greeting.py": FIXED}) as fixture:
        project = project_for(
            fixture.repository,
            tmp_path,
            oracles=[
                Oracle(
                    language="python",
                    entry="greeting.greet",
                    cases_file=private,
                    runtime=runtime,
                    runtime_sha256=directory_digest(runtime),
                )
            ],
        )
        journal, workspace = task(project)
        records = VerificationRunner(workspace, Budget(project.limits)).held_out()
        assert records and all(r["pass"] for r in records)
        with pytest.raises(ValueError, match="expose"):
            project_for(
                fixture.repository,
                tmp_path,
                oracles=[
                    Oracle(
                        language="python",
                        entry="greeting.greet",
                        cases_file=private,
                        runtime=tmp_path,
                        runtime_sha256="0" * 64,
                    )
                ],
            )


def test_control_character_paths_and_coerced_orientation_fields_are_rejected():
    from autocoder.v0.schema import Orientation, relative

    for code in [0, 1, 31, 127]:
        with pytest.raises(ValueError):
            relative("src/a" + chr(code) + "b.py")
    assert relative("src/模型.py") == "src/模型.py"
    value = {
        "base_sha": "a" * 40,
        "findings": [
            {"path": "module.py", "sha256": "b" * 64, "start": "1", "end": 2, "summary": "source"}
        ],
    }
    with pytest.raises(ValueError):
        Orientation.model_validate_json(json.dumps(value))
