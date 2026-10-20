import pytest

from autocoder.v0.ci import Actions, Gh, Policy, task_result_from_rows
from autocoder.v0.journal import Journal, NeedsUser

SHA = "b" * 40


class Backend:
    def __init__(self):
        self.calls = []
        self.ref_sha = SHA
        self.error = None
        self.run = {
            "id": 123,
            "head_sha": SHA,
            "workflow_id": 17,
            "repository": {"full_name": "owner/repo"},
            "event": "workflow_dispatch",
            "status": "completed",
            "conclusion": "success",
        }

    def request(self, endpoint, *, payload=None):
        self.calls.append((endpoint, payload))
        if payload is not None and self.error:
            raise self.error
        return self.run if "/runs/" in endpoint else {"sha": self.ref_sha}


def actions_for(tmp_path):
    journal = Journal(tmp_path / "state", "project", "a" * 32)
    report = {
        "task_commit": SHA,
        "status": "VERIFIED_LOCAL",
        "acceptance": {"remote_ci": "not_run", "human_acceptance": "not_run"},
    }
    journal.emit("FINAL", evidence_ref=journal.artifact(report))
    backend = Backend()
    return Actions(
        Policy(repository="owner/repo", workflow_id=17, ref="reviewed"), journal, backend
    )


def test_ci_requires_exact_plan_approval_and_never_retries_ambiguous_dispatch(tmp_path):
    actions = actions_for(tmp_path)
    key = actions.plan()["plan"]
    with pytest.raises(NeedsUser, match="approval"):
        actions.dispatch(key, "yes")
    assert all(payload is None for _, payload in actions.backend.calls)
    actions.backend.error = TimeoutError("response lost")
    with pytest.raises(TimeoutError):
        actions.dispatch(key, key)
    with pytest.raises(NeedsUser, match="already attempted"):
        actions.dispatch(key, key)
    assert len([p for _, p in actions.backend.calls if p is not None]) == 1
    assert actions.journal.read()[-1]["kind"] == "CI_DISPATCH_UNKNOWN"


def test_ci_rechecks_moving_ref_and_records_only_exact_run_evidence(tmp_path):
    actions = actions_for(tmp_path)
    key = actions.plan()["plan"]
    actions.backend.ref_sha = "c" * 40
    with pytest.raises(NeedsUser, match="Remote ref"):
        actions.dispatch(key, key)
    assert not any(r["kind"] == "CI_DISPATCH_INTENT" for r in actions.journal.read())
    for name, bad in [
        ("head_sha", "c" * 40),
        ("id", 124),
        ("workflow_id", 18),
        ("event", "push"),
        ("repository", {"full_name": "other/repo"}),
    ]:
        previous = actions.backend.run[name]
        actions.backend.run[name] = bad
        with pytest.raises(NeedsUser, match="differs"):
            actions.inspect(123)
        actions.backend.run[name] = previous
    assert task_result_from_rows(actions.journal)["acceptance"]["remote_ci"] == "not_run"
    assert actions.inspect(123)["remote_ci"] == "pass"
    report = task_result_from_rows(actions.journal)
    assert report["acceptance"] == {"remote_ci": "pass", "human_acceptance": "not_run"}
    actions.backend.run["status"] = "in_progress"
    actions.backend.run["conclusion"] = None
    assert actions.inspect(123)["remote_ci"] == "not_run"
    actions.backend.run.update(status="completed", conclusion="cancelled")
    assert actions.inspect(123)["remote_ci"] == "fail"
    actions.journal.emit("EDIT_INTENT")
    with pytest.raises(NeedsUser, match="unfinished"):
        actions.plan()


def test_gh_transport_bounds_output_and_retries_only_reads(tmp_path, monkeypatch):
    executable = tmp_path / "gh"
    counter = tmp_path / "counter"
    executable.write_text(
        "#!/usr/bin/python3\nimport pathlib, sys, json, os\n"
        f"p = pathlib.Path({str(counter)!r})\n"
        "n = int(p.read_text()) if p.exists() else 0\np.write_text(str(n+1))\n"
        "assert os.environ.get('GH_DEBUG') is None\n"
        "if n == 0:\n print('HTTP 503'); sys.exit(1)\n"
        "print(json.dumps({'ok': True}))\n"
    )
    executable.chmod(0o700)
    monkeypatch.setenv("GH_DEBUG", "api")
    client = Gh(str(executable))
    assert client.request("repos/owner/repo/actions/runs/1") == {"ok": True}
    assert counter.read_text() == "2"
    counter.unlink()
    with pytest.raises(NeedsUser):
        client.request("repos/owner/repo/actions/workflows/17/dispatches", payload={"ref": "x"})
    assert counter.read_text() == "1"
    executable.write_text("#!/usr/bin/python3\nprint('x' * 300000)\n")
    with pytest.raises(NeedsUser, match="bound"):
        client.request("repos/owner/repo/actions/runs/1")
    executable.write_text(
        "#!/usr/bin/python3\nimport json, sys\n"
        "assert sys.argv[-2:] == ['--input', '-']\n"
        "value = json.load(sys.stdin)\n"
        "assert value['inputs']['text'] == '@secret; $(whoami)'\n"
        "print(json.dumps({'literal': True}))\n"
    )
    assert client.request(
        "repos/owner/repo/actions/workflows/17/dispatches",
        payload={"ref": "x", "inputs": {"text": "@secret; $(whoami)"}},
    ) == {"literal": True}


def test_successful_dispatch_is_not_ci_acceptance_and_changed_policy_is_refused(tmp_path):
    actions = actions_for(tmp_path)
    key = actions.plan()["plan"]
    previous = actions.policy
    actions.policy = previous.model_copy(update={"ref": "different"})
    with pytest.raises(NeedsUser, match="differs"):
        actions.dispatch(key, key)
    assert not any(payload is not None for _, payload in actions.backend.calls)
    actions.policy = previous
    assert actions.dispatch(key, key)["remote_ci"] == "not_run"
    assert task_result_from_rows(actions.journal)["acceptance"]["remote_ci"] == "not_run"
    with pytest.raises(NeedsUser, match="already attempted"):
        actions.dispatch(key, key)
