"""Publish local v0 evidence, retaining failed attempts and unverified acceptance gates."""


# Wide Markdown report tables are intentional.
# ruff: noqa: E501

import json
import re
import statistics
from pathlib import Path

from autocoder.protocol import digest, utc_now

ROOT = Path(__file__).resolve().parents[1]
RAW = Path.home() / ".local/share/autocoder/stage0"
CODE = "3b035ac9fa089b3e05058f93ce70a1b5f4910e39"


def read(name, file="result.json"):
    return json.loads((RAW / name / file).read_text())


def main():
    log = RAW / "v0-final-verification.log"
    counts = re.findall(r"(\d+) passed", log.read_text())
    text = f"""# Persistent v0 implementation evidence

Recorded: {utc_now()}. Reviewed controller revision: `{CODE}`.

**Core implementation verified locally; full v0 acceptance is still open.** The
owner approved custom v0 for compact contexts and reliable recovery. The owner
also confirmed only one Ollama endpoint is available. The required independent
server scenario has not been replaced by URL aliases, proxies or a simulated
second Ollama server. TUI and post-v0 integrations remain behind that gate.

## Implemented workflow and local gates

- `autocoder-task` provides start/resume/status/diff/events/cancel and explicit user
  approve/refuse/integration recording. It never merges, pushes or dispatches CI.
- One deterministic coordinator uses fresh contexts across phases and bounded native
  assistant/tool history within phases. At 75% context pressure it resets to current
  source, typed plan and bounded operation summaries. Actual input/schema/output
  accounting is saved per inference. Source reads are scoped and bounded.
- Branch/worktree creation, source hash checks and task locks preserve the original
  checkout. Atomic edits record expected/proposed hashes before replacement and
  actual observed hashes afterward. JSONL records are fsynced and hash-chained;
  evidence is content-addressed outside Git. Torn tails/unknown changes fail closed.
- Tests cover real SIGKILL after replacement and full-loop restart, interrupted
  commits, reconciliation without duplicate mutation, stale hashes, path escapes,
  protected files/embedded tests, private failure without private repair feedback,
  phase/duplicate/context limits, strict handoffs and a single bounded replan.
- Named Python/Rust checks use disposable tracked-file snapshots in qualified
  offline namespaces/cgroups. Snapshot input tampering cannot turn a check into
  acceptance. No unconfined host fallback is provided.
- Dependency downloads are inert, bounded and digest-pinned. Install/build hooks
  run offline with read-only declared artifacts. Prepared regular-file outputs are
  hashed, durably published per task and mounted read-only for checks. Negative
  tests cover host secret reads, outside writes, network and artifact/output writes.

Full suite: **{counts[-1]} passed** using `uv run pytest`. Ruff lint/format and
`git diff --check` pass. Raw suite log: `{log}`
(SHA-256 `{digest(log.read_bytes())}`). This is local verification, not CI.

## Model/runtime and policies

All live tasks use `qwen3.5:9b`, digest
`6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`,
GGUF Q4_K_M (server-reported 9.7B), with native Ollama at 32K, thinking disabled,
temperature 0 and seed 42. The recorded server reports 0.40.5. Controller Python is
3.12.10; sandbox Python and the independent navigation runtime use system 3.12.3.
Host telemetry identifies the controller; physical inference-backend hardware is
not independently accepted. Full template/license/toolchain/OS/package provenance
is in each task's manifest and source/runtime bindings.

V0 defaults are 600 seconds, 49,152 input tokens, 8,192 output tokens, 60 task tool
calls, 20 per phase and three repairs, with one restart/replan. These are application
settings, not revised Stage 0 benchmark limits. Task creation freezes policy and
private-asset hashes. Generic provenance retains the old Stage 0 inventory scaffold;
actual v0 tool schemas and per-phase byte/token measurements are preserved in
MODEL_REQUEST artifacts and the frozen task policies.

## Live real-repository repairs

Both tasks target genuine policy bugs found in this repository during implementation.
They are small application-infrastructure repairs, not broad real-project coding
coverage. Each task reproduces its public failure on the base, applies guarded
source edits, runs deterministic public verification and passes external private
acceptance. Their worktrees/commits are retained for inspection; no generated task
branch was automatically integrated. The primary implementation subsequently
incorporated reviewed fixes and regression coverage as ordinary development.

| Task | Base revision | Status | Seconds | Input/output tokens | Tool calls | Original status unchanged |
| --- | --- | --- | ---: | --- | ---: | --- |
"""
    for name, description in [
        ("v0-real-policy-05", "Rust test-file protection"),
        ("v0-real-path-01", "ASCII DEL path rejection"),
    ]:
        record = read(name)
        task = record["task"]
        usage = task["usage"]
        text += (
            f"| {description} | `{task['base_sha']}` | {task['status']} | "
            f"{usage['elapsed_seconds']:.2f} | {usage['request_tokens']}/{usage['output_tokens']} | "
            f"{usage['tool_calls']} | {record['original_status_unchanged']} |\n"
        )
    text += """
Public and private checks pass for these runs. Human acceptance, remote CI and
physical hardware acceptance remain `not_run`. Private cases are stored outside
the repository; the corrected runner accepts external case data rather than
embedding it in source that the task could inspect. Private Python imports prefer
the candidate over dependency packages, verified by a deliberate shadowing test.

## Two native projects on the available endpoint

`v0-projects-02` launches Python and Rust clients concurrently with independent
repositories, state roots, worktrees, task IDs, journals and Serena processes.
Both connect to the same real `http://127.0.0.1:11434` endpoint. This validates
sharing one backend; it does not validate independent servers.

| Project | Status | Seconds including queue/startup | Input/output tokens | Check/private status | Navigation PID |
| --- | --- | ---: | --- | --- | ---: |
"""
    projects = read("v0-projects-02", "summary.json")
    for record in projects["records"]:
        task = record["task"]
        usage = task["usage"]
        text += (
            f"| {record['project']} | {task['status']} | {usage['elapsed_seconds']:.2f} | "
            f"{usage['request_tokens']}/{usage['output_tokens']} | tests pass / held-out pass | "
            f"{record['navigation_pids'][0]} |\n"
        )
    text += (
        f"\nThe {len(projects['inference_intervals'])} recorded inference-lock intervals do not "
        f"overlap: `{projects['inference_serialized']}`. Cross-project read refused: "
        f"`{projects['cross_project_read_blocked']}`. Both original repositories remain clean.\n"
    )
    text += (
        "\nRecorded public check timings on fresh snapshots (startup plus compile/test work):\n\n"
    )
    text += "| Project | Invocations | Mean execution seconds |\n| --- | ---: | ---: |\n"
    for record in projects["records"]:
        folder = Path(record["task"]["evidence_directory"])
        rows = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines()]
        times = []
        for row in rows:
            if row["kind"] == "CHECK":
                value = json.loads(
                    (folder / "evidence" / (row["evidence_ref"] + ".json")).read_text()
                )
                times.append(value["execution"]["elapsed_seconds"])
        text += f"| {record['project']} | {len(times)} | {statistics.mean(times):.3f} |\n"
    text += """
Captured live stdout agrees with journal replay for all 68 events from each project;
`v0-projects-02/event-replay-audit.json` records that read-only comparison.

The lock is per user/origin, so projects with different state directories still
serialize one backend. File locks are local to this host; aliases and other hosts
are not a distributed scheduler. One project's independent-server outage and secure
remote-channel acceptance remain unverified because no second endpoint is available.

## Confined navigation and cache policy

The independent runtime pins Serena `d9e4c796fae0207ba6848d1df4b331122a5567b5`,
Pyright 1.1.403 and 76 installed package versions matching `experiments/serena/uv.lock`.
It uses system Python 3.12.3; the controller uses its locked uv Python environment.
No Serena package is imported into the application. A reviewed installed Node
binary is copied by the runtime helper; runtime hashes bind the actual files.

The measured process sees only an approved-source mirror, read-only runtime/toolchain
and ephemeral cache/home. Its MCP allowlist excludes shell/project switching and
writes. Source changes restart the index. Returned paths/line ranges are validated
against actual current source; invalid location metadata is flagged. Python
AST/rg/reads provide explicit fallback where valid, without claiming semantic recall.

| Language | Cold lookup seconds | Warm references seconds | Edit invalidates process | Forbidden tool blocked |
| --- | ---: | ---: | --- | --- |
"""
    for row in read("v0-navigation-04", "summary.json")["results"]:
        text += (
            f"| {row['language']} | {row['cold_seconds']:.2f} | {row['warm_query_seconds']:.2f} | "
            f"{row['restart_pid_changed']} | {row['unapproved_tool_blocked']} |\n"
        )
    text += """
These tiny files do not measure large-workspace indexing. Warm timings include
validation and MCP query costs. Rust references failed under the initial 2 GB
virtual-address limit; the qualified navigation policy permits 8 GB virtual space
while retaining 2 GB resident memory, 64 tasks and two CPUs. No shared writable
compiler/LSP cache is qualified. Compiler/test snapshots are rebuilt per check;
trusted runtime packages and verified artifact bytes may be shared read-only.

The documented runtime bootstrap was exercised at
`/home/phil/.local/share/autocoder/serena-runtime-locked`; it installed the 76 pinned
packages and copied the reviewed Node binary. Its inventory and runtime digest are
saved there. Runtime paths/metadata affect content hashes; do not reuse another
machine's digest without verifying its actual directory.

## Failed attempts and corrected fixture

- Navigation probes 01–03 retain missing-config, grouped-reference parsing and Rust
  language-server failures. Probe 04 verifies Python/Rust symbols, references,
  forbidden-tool refusal and source-change restart.
- Real-policy 01 stopped duplicate reads. Run 02 rejected a plan because exact
  required check names were missing from the coordinator's model input. Run 03
  stopped repeated reads caused by resetting context after each tool call. These
  failures led to focused source retrieval, grounded check enums and native
  within-phase tool history; thresholds and task contracts were not weakened.
- Real-policy 04 produced a valid fix but failed an incorrect private expectation
  that contradicted preserved base behavior. Its original `FAILED_VERIFICATION`
  result remains unchanged. The first fixture generator also embedded private
  literals in target-repository source and therefore is not acceptance evidence
  for private isolation. Version 2 moves case data outside the repository and
  corrects that expectation before run 05. Run 04's original-status check is false
  because the primary agent edited a tracked test concurrently; run 05 holds the
  original checkout stable and passes that check.
- Projects 01 retains a Python duplicate-read stop and a Rust missing-linker baseline
  failure. Projects 02 uses native tool history and a resolved system compiler path,
  rather than an `/etc/alternatives` link absent from the namespace.

These are engineering qualification attempts, not a new comparative benchmark or
an unbiased coding-success estimate. All original Stage 0 results remain in their
frozen registrations. No superiority claim follows from four successful v0 tasks.

## Specification acceptance matrix (§12)

| Criterion | Evidence | State |
| --- | --- | --- |
| Full controlled loop | two real repairs and both controlled projects | local pass |
| Fresh phase contexts and accounting | recorded MODEL_REQUEST/HANDOFF traces; native-history regression test | local pass |
| Guarded edits and reconciliation | SIGKILL/commit tests, duplicate/stale/path guards | local pass |
| Protected tests and inaccessible private files | tamper/shadowing tests; corrected external private fixtures | local pass on tested scopes |
| Qualified confinement | actual namespace/cgroup checks and hostile preparation hook | local pass |
| Durable restart | real process kill and resume without duplicate edits | local pass |
| Retained branches/original preservation | successful task records, clean original project checks | local pass |
| Two projects against two different endpoints | only shared-endpoint demonstration available | **not verified** |
| Headless events, diffs and outcomes | live CLI stdout, journals, status and replay | local pass |
| No mandatory paid API/containers/IDE bridge | native uv/Git/bwrap/systemd and supplied Ollama | local pass |
| Versions, budgets and limitations | manifests, frozen policies, this report | local pass |

P6-07/P7-05 full acceptance remains open. P7-02/P7-04 need the independent-server
scenario, or an explicit owner-approved specification revision deferring it.
P8 work has not started. No silent gate change has been made.

## Reproduction and artifact inventory

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run autocoder-task --help
```

See [the task guide](../V0.md) for policy, task commands and runtime preparation.
For old bug reproductions use the recorded base/controller revision; the current
source includes the fixes, so those public reproducers correctly pass on the base
and are now inconclusive as new bug-fix requests. Raw artifacts remain outside Git.

| Run/artifact | SHA-256 |
| --- | --- |
"""
    names = [
        "v0-navigation-01",
        "v0-navigation-02",
        "v0-navigation-03",
        "v0-navigation-04",
        "v0-real-policy-01",
        "v0-real-policy-02",
        "v0-real-policy-03",
        "v0-real-policy-04",
        "v0-real-policy-05",
        "v0-real-path-01",
        "v0-projects-01",
        "v0-projects-02",
    ]
    for name in names:
        folder = RAW / name
        path = folder / ("summary.json" if (folder / "summary.json").exists() else "result.json")
        text += f"| `{path}` | `{digest(path.read_bytes())}` |\n"
    (ROOT / "docs/evidence/V0_IMPLEMENTATION_2026-10-19.md").write_text(text)


if __name__ == "__main__":
    main()
