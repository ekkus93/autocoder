# GitHub Actions CI

## Automatic verification

[`.github/workflows/verify.yml`](../.github/workflows/verify.yml) runs on branch
pushes, pull requests, version tags (`v*`), and manual dispatch. It uses GitHub-hosted
Ubuntu 24.04; no self-hosted runner is required.

The workflow installs pinned uv/Python versions, creates the locked environment,
prepares bubblewrap and a systemd user session, and qualifies the actual sandbox
before running lint, formatting and the complete Python/Rust test suite. Runner
setup grants `/usr/bin/bwrap` scoped AppArmor user-namespace access when required;
it does not change the global user-namespace restriction. Confinement failures
fail CI. No local Ollama server or model inference is required by these tests.

### Artifact retention

Only a **successful push of a `v*` release tag** builds distributions and uploads
artifacts. The upload contains the wheel/source archive, JUnit results, and sandbox
qualification JSON, retained for 14 days. Branch, pull-request and manual runs
upload no artifacts, including on failures. Dependency cache saving is disabled.
GitHub's ordinary job logs still exist according to repository log retention.

Third-party actions are pinned to commits. Jobs use read-only repository access,
checkout does not persist credentials, and newer runs supersede older runs for
the same branch without cancelling release-tag runs.

## Optional operator client

`autocoder-ci` is an operator CLI, separate from the model's tool gateway. It can
prepare a dispatch plan, send one explicitly approved dispatch, and inspect an
existing run. It cannot push, merge, create branches, edit workflows, or manage
secrets. Local verification and human acceptance remain separate from remote CI.

## Configuration

Keep a reviewed policy outside tracked source:

```json
{
  "repository": "OWNER/REPOSITORY",
  "workflow_id": 123456,
  "ref": "reviewed-task-branch",
  "inputs": {}
}
```

Use `/usr/bin/gh` authenticated for github.com. Supply secrets through GitHub's
existing secret configuration; workflow inputs appear in the local review plan.
The workflow must support `workflow_dispatch`. Its configured branch or tag must
already point to the locally verified task's exact commit. Publishing that commit
is a separate user-controlled operation.

## Review and dispatch

```sh
uv run autocoder-ci --config /path/project.json --policy /path/ci.json \
  --task-id TASK_ID plan
```

Inspect the returned repository, workflow ID, ref, inputs, and exact commit before
approving the concrete plan. Then an operator can run:

```sh
uv run autocoder-ci --config /path/project.json --policy /path/ci.json \
  --task-id TASK_ID dispatch --plan PLAN_SHA256 --approve PLAN_SHA256
```

The client rechecks the remote ref immediately before dispatch. A durable intent
precedes the POST, and that plan cannot be dispatched twice. If the response is
lost, inspect GitHub to determine what happened. Dispatches are never automatically
retried. Read requests retry transient HTTP 429/502/503/504 errors at most twice.
Each request has a 15-second deadline and 256 KiB output bound.

## Inspect a run

```sh
uv run autocoder-ci --config /path/project.json --policy /path/ci.json \
  --task-id TASK_ID inspect RUN_ID
```

Inspection validates run ID, repository, workflow ID, `workflow_dispatch` event,
and exact head SHA. Only a completed successful matching run records `remote_ci:
pass`; pending runs record `not_run`, and other completed conclusions record
`fail`. Evidence is content-addressed in the task journal. Local and human outcomes
are preserved. A ref can move between checking and dispatching, so a successful
POST alone never establishes CI acceptance.

Head SHA proves the run's GitHub identity, not what arbitrary workflow steps
actually checked out or tested. Review the selected workflow before use.

## Verification status

The operator client has local tests for approval, ambiguous dispatches, moving
refs, mismatched runs, output bounds, literal JSON inputs and read-only retries.
Automatic branch/PR CI is independent of the client's explicitly approved
`workflow_dispatch` path. Live run results and exact revisions are recorded in
the [CI evidence checkpoint](evidence/GITHUB_ACTIONS_2026-10-19.md).

Command behavior follows the official [workflow dispatch manual](https://cli.github.com/manual/gh_workflow_run)
and [GitHub Actions REST API](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run).
