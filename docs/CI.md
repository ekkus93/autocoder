# Optional GitHub Actions client

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

Local tests cover approval, ambiguous dispatches, moving refs, mismatched runs,
output bounds, literal JSON inputs, and read-only retries. No live dispatch or CI
pass has been claimed. The repository had no Actions workflows during inspection;
a target workflow and an approved plan are needed for live qualification.

A local draft, [`.github/workflows/verify.yml`](../.github/workflows/verify.yml),
provides manual dispatch only, a sandbox probe, locked `uv` setup, lint, formatting,
and the complete suite. It requires a self-hosted Linux X64 runner labeled
`autocoder-sandbox`, with `uv`, Python and the qualified native sandbox prerequisites
already installed. This avoids assuming hosted runners provide the required
user namespaces/cgroups/systemd user session. The checkout action is pinned to
commit `11d5960a326750d5838078e36cf38b85af677262` (resolved from its official `v4`
ref during preparation), with credential persistence disabled. Publishing this
workflow, provisioning a runner, and approving a live dispatch remain operator
steps; no CI runtime result is inferred from this draft.

Command behavior follows the official [workflow dispatch manual](https://cli.github.com/manual/gh_workflow_run)
and [GitHub Actions REST API](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run).
