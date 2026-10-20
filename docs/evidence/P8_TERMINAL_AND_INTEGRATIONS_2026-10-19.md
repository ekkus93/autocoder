# P8 terminal client and optional integration checkpoint

Reviewed implementation: `852b1e8fa8dfa7507021f4eaeb5c61f3773a71f0`.
Recorded 2026-10-19 America/Los_Angeles; final sandbox probe UTC
2026-10-20T00:01:33.365316+00:00. Raw artifacts remain outside Git under
`/home/phil/.local/share/autocoder/stage0/`.

## Verification

| Command | Observed result |
| --- | --- |
| `uv sync --locked` | pass; no additional application dependencies |
| `uv run ruff check .` | pass |
| `uv run ruff format --check .` | 88 Python files formatted |
| `uv run pytest -q` | 77 passed in 18.08 seconds |
| `uv run autocoder sandbox-probe --output <fresh-external-directory>` | VERIFIED_LOCAL; all five negative/positive confinement checks pass |
| `verify_engines(..., benchmarks/v5, c04da250...)` | frozen protocol and engine hashes unchanged |
| `git diff --check` | pass |

Python 3.12.10, uv 0.12.9, pytest 9.1.1, Ruff 0.17.1, httpx 0.28.1,
Pydantic 2.14.1, GitHub CLI 2.45.0. Existing Ollama results remain the earlier
v0 evidence; no new coding benchmark, model comparison, or inference success is
claimed here. The sandbox probe inventories the environment separately.

## P8-01: native terminal client — locally verified

`autocoder-tui` uses standard-library curses and invokes `autocoder-task` as a
subprocess. It reads the existing JSONL events and uses the existing start,
resume, stop, diff, status, and human-decision paths. No second coordinator exists.
The headless evidence command lists journal references or validates and opens an
artifact by SHA-256. See [V0.md](../V0.md#terminal-interface).

Six new tests cover real CLI replay/evidence integrity, explicit typed decisions,
display bounds/control filtering, real PTY attach/resize/exit and terminal mode
restoration, private request-file creation/removal with a real CLI start, and
reader detachment versus explicit cancellation. The start test deliberately has
an empty model inventory and must report BLOCKED_ENVIRONMENT, without inference.
Existing engine tests continue covering successful loops and crash/resume.

Limits: single-line task entry; last 2000 displayed lines; 4096 characters per
line; individual CLI output lines above 64 KiB omitted with a notice. Complete
artifacts remain available outside the display. Diff access waits for the task
lock. UI-owned controllers must settle after stop before quit. External crashes
use existing durable recovery; no claim of manual usability acceptance is made.

## P8-03: public search/fetch evaluation — source and policy review complete

The [SearXNG API](https://github.com/searxng/searxng/blob/640f88c9bd58e58e98a73068d44d69bcc85e31f6/docs/dev/search_api.rst)
supports structured HTTP search, but JSON output must be enabled by the instance.
Inference from that interface: an approved self-hosted endpoint is a reasonable
future adapter target; self-hosting does not make queries private from upstream
engines. No instance was installed or queried during this evaluation.

The [Fetch MCP source documentation](https://github.com/modelcontextprotocol/servers/blob/005e7e6ea55a61300f05bd2e02a02bc0822db0f4/src/fetch/README.md)
describes bounded extraction and public-address checks, while documenting DNS
rebinding/proxy limitations. Inference: this is insufficient alone to establish
this repository's egress policy. Activation needs controller-owned public target
allowlists, redirect/connection checks, explicit query opt-in and output budgets.
Fetched content must remain untrusted data and cannot authorize tools.

Decision: retain offline core execution. Any future search query must be reviewed
or policy-approved public text; never send source snippets, private paths,
credentials, or task transcripts by default. Source metadata review is complete;
service startup, adapter behavior and retrieval benefit remain untested. P8-03
completion records this evaluation, not a qualified or enabled integration.

## P8-04: CI wrapper prepared — live qualification needs assistance

`autocoder-ci` provides reviewed policy, concrete content-addressed dispatch plans,
exact-plan approval, intent-before-POST and no automatic dispatch retries. Reads
have bounded transient retries, time and output. Inspection checks repository,
workflow, run ID, event and task commit before recording remote CI separately.
Four new tests cover ambiguous dispatch, moving refs, policy/identity mismatches,
literal inputs, retry/output bounds and acceptance separation. Fake responses
are unit fixtures, not GitHub CI evidence. See [CI.md](../CI.md).

The owner selected “Prepare a Python lint/test workflow here.” The prepared
[workflow](../../.github/workflows/verify.yml) has manual dispatch only, pinned
checkout without persisted credentials, locked uv setup, sandbox probe, lint,
formatting and the full suite. It requires a qualified self-hosted Linux X64
runner with label `autocoder-sandbox`. Its verification commands pass locally;
the YAML has not executed on GitHub. Head SHA validation alone cannot prove what
arbitrary workflow steps actually tested.

Read-only GitHub API inspection found zero published workflows and zero registered
repository runners. No workflow was published, no runner registered, no dispatch
sent, and no live CI pass recorded. Completing this milestone requires the owner's
runner choice/provisioning and authorization to publish the reviewed workflow.
A concrete dispatch plan can only be prepared after the remote ref and workflow
exist; dispatch approval remains a separate explicit step under SPEC §7.3.

## P8-07: persistence decision — retain JSONL

`scripts/audit_journal_workload.py` revalidated four existing successful task
journals seven times each, checking that their bytes remained unchanged.

| Task | Events | Bytes | Median replay ms | Maximum replay ms |
| --- | ---: | ---: | ---: | ---: |
| Real Rust policy repair | 79 | 79393 | 2.14 | 2.99 |
| Real path repair | 79 | 79384 | 2.18 | 2.33 |
| Controlled Python project | 68 | 48677 | 1.52 | 2.18 |
| Controlled Rust project | 68 | 48775 | 1.51 | 5.53 |

No SQLite migration is justified by this observed workload. Existing tests verify
single-writer locks, tamper detection and replay/recovery. This small cached local
sample does not establish scaling capacity or production concurrency guarantees.
Reconsider storage when actual query/transaction requirements exceed JSONL.

## Conditional work remains pending

- **P8-02:** SPEC §5.3 requires a demonstrated documentation retrieval gap before
  adding a corpus. Current tasks have not established that gap. [Grounded Docs](https://github.com/arabold/docs-mcp-server/blob/651b282b762dec7a66fdda3f10c06621c9bde1dc/README.md)
  remains the candidate; no installation or retrieval/token benchmark was run.
- **P8-05:** no agent-role ablation or success gain has been measured. Preserve the
  single-loop implementation and frozen baseline; any future comparison needs a
  separate registration and equal aggregate budgets. No agents were spawned here.
- **P8-06:** role routing, alternative quantization, extra languages and richer
  memory remain conditional on representative task evidence; none is established
  by the terminal/CI work. No model download or routing change was performed.
- **P1B-05** remains untriggered. **P7-02/P7-04** retain the owner's earlier
  unavailable-server deferral. Neither category is falsely marked as passed.

## Artifact hashes

All paths below are relative to the external artifact root stated above.

| Artifact | SHA-256 |
| --- | --- |
| `p8-final-verification.log` | `54ea18968e2cdca19828da22c67e0892cf4a32a8191b7f1f15d391f5ef9d8a61` |
| `p8-workflow-sandbox-probe/result.json` | `b169fb979e96bffc7b34b90fe101cecc876204ab5656a2729fcbbe9fc76b6f7d` |
| `p8-journal-audit.json` | `e57c0aadb8a3621c3de88af8fa95ec906d9619402966833b18684e946ae0b8fb` |
| `p8-optional-source-review.json` | `2e1e4cb7a47758b9c8931d8f9f878427630e3bee458a7164f2ee54cc902d5d25` |
| `p8-github-workflows.json` | `a251d32568a7a08232ca3304ee97a5e6548146464133182aabeb86f463b3230b` |
| `p8-github-runners.json` | `7a4b58461012c781d3b71d5cba1875eedd2105935140da61c6f5f241c533c21b` |
