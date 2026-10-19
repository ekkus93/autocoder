# Local AI Coder — Implementation TODO

**Status:** Foundation in progress; sandbox qualification blocked by host AppArmor policy
**Date:** 2026-10-19  
**Authority:** [`SPEC.md`](SPEC.md)  
**Primary goal:** Build a local-first autonomous coding system that makes small LLMs substantially more useful by improving context management, code retrieval, tool execution, and verification.

> **Rules for execution:** Work dependency-first. Never mark an item complete merely because code exists or a model reports success. Add commit SHA, pinned version, test command/result and evidence path for every completed milestone. Do not claim real hardware/CI/human acceptance without real evidence. Stage 0 is a hard gate; do not build the full v0 or TUI before viability is established. Microsoft Agent Framework is optional; Ralph Bridge, paid API dependencies, VS Code integration and mandatory Docker/Podman are excluded.

## Current execution checkpoint

Completed P0-01–P0-03 and the P1D-01 host diagnostic. P0-04–P0-08 have partial foundation support and remain unchecked. Host AppArmor denies bubblewrap namespace setup; assistance is needed before sandbox qualification and candidate scoring. See the [evidence report](evidence/STAGE0_FOUNDATION_2026-10-19.md) for exact revisions, commands, artifacts, and the resumption steps. Full v0 development remains behind Stage 0.

## How to use this checklist

- `[ ]` = not objectively complete; `[x]` = evidence verified and recorded.
- IDs are stable references; do not remove unfinished or blocked tasks.
- Where a task says **gate**, stop dependent development until the gate has evidence. Ordinary failed experiments should be diagnosed, not papered over.
- Record a concise evidence line beneath checked tasks: `Evidence: <commit SHA> | <command/job> | <result> | <artifact path> | <UTC>`.
- Spec changes or revised benchmark gates require recorded rationale and a new benchmark/spec revision before scored evaluation.

---

## P0 — Foundation and benchmark protocol (must precede scored experiments)

- [x] **P0-01** Create the Python/`uv` repository skeleton, lint/test configuration, permissive application license selected deliberately, README, and runnable smoke test. **Accept:** native Ubuntu installation without Docker/Podman; CI/local smoke test documented.
  Evidence: `3162163b25c460842f8d6b599aa4ad8cad26b4fc` | `uv run pytest; uv run autocoder smoke` | pass; 17 tests and native smoke verified | [checkpoint](evidence/STAGE0_FOUNDATION_2026-10-19.md) | 2026-10-19T11:15:32.717543+00:00
- [x] **P0-02** Implement a headless experiment CLI and versioned JSON/JSONL result format; TUI is not a dependency. **Accept:** one command runs a fixture and writes reproducible machine-readable results.
  Evidence: `3162163b25c460842f8d6b599aa4ad8cad26b4fc` | `uv run pytest; uv run autocoder smoke` | pass; 17 tests and native smoke verified | [checkpoint](evidence/STAGE0_FOUNDATION_2026-10-19.md) | 2026-10-19T11:15:32.717543+00:00
- [x] **P0-03** Build fixture manager using throwaway Git repositories/worktrees with safe cleanup and pinned base SHAs. **Accept:** identical fixture can be restored for repeated arms without contaminating the original repository.
  Evidence: `3162163b25c460842f8d6b599aa4ad8cad26b4fc` | `uv run pytest; uv run autocoder smoke` | pass; 17 tests and native smoke verified | [checkpoint](evidence/STAGE0_FOUNDATION_2026-10-19.md) | 2026-10-19T11:15:32.717543+00:00
- [ ] **P0-04** Record exact model names/digests, quantization, chat templates, Ollama and client builds, Python/Serena versions, host/GPU details, tool inventories and licenses. **Accept:** reproducibility manifest emitted before every run.
- [ ] **P0-05** Pre-register **five micro-experiment families** and **eight end-to-end tasks** (4 Python, 4 Rust) with fixed task prompts, protected oracles, scoring scripts, model settings, allowed tools and resource caps. **Accept:** immutable versioned benchmark manifest with checksums.
- [ ] **P0-06** Set and freeze provisional Stage 0 thresholds from `SPEC.md` §11.4 *before* scored evaluation; provide an explicit change-control process. **Accept:** scored suite will refuse an unversioned changed threshold/budget.
- [ ] **P0-07** Implement baseline/hidden-oracle scoring and test-tamper detection. **Accept:** held-out checks are unreadable from candidate worktrees; a deliberate agent-side attempt to weaken tests is flagged.
- [ ] **P0-08** Select fixed task budget defaults (wall time, request tokens, output tokens, tool calls, repairs) and capture per-run usage. **Accept:** hard limits are enforced and produce `BUDGET_EXHAUSTED`, never false success.

## P1 — Stage 0 micro-gates (do not start full v0 before decision)

### P1A. Runtime and context feasibility

- [ ] **P1A-01** Probe Qwen3.5-9B on Ollama at 16K/32K/64K, and 128K only if practical. Record requested vs observed context, model residency, memory, prefill/generation throughput, failures and context quality. **Accept:** reproducible table with actual measurements.
- [ ] **P1A-02** Compare thinking enabled/disabled for relevant tasks, including output-budget and tool-use impact. **Accept:** phase-level metrics; no unsupported “thinking is always better” claim.
- [ ] **P1A-03** Test remote Ollama connectivity/timeout/retry and non-ambiguous inference recovery. **Accept:** endpoint failure produces auditable error without modifying source or losing state.

### P1B. Tool calling and prompt/cache behavior

- [ ] **P1B-01** Test Ollama native tool and structured-output calls versus its OpenAI-compatible API using the actual model/chat template. **Accept:** first-try schema, semantic correctness, and recovered/unrecoverable failure rates are distinct.
- [ ] **P1B-02** Compare 4-, 6- and 12+-tool schema inventories over at least 40 representative tool-selection/argument trials. **Accept:** recorded schema-token cost and tool-choice correctness, including difficult negative cases.
- [ ] **P1B-03** Compare stable fixed 5–6 tool definitions with per-phase subsets for correctness, prompt-cache reuse and latency. Keep `num_ctx` fixed within each arm. **Accept:** chosen approach justified by measurements.
- [ ] **P1B-04** Check Pydantic/JSON Schema handoff decoding and bounded recovery of malformed responses. **Accept:** invalid outputs never silently enter the coordinator state.
- [ ] **P1B-05** If tool parsing is a persistent blocker, run a small diagnostic using llama.cpp server and/or another quantization to identify the failure layer. **Accept:** documented root-cause hypothesis and tested mitigation or a clear no-go.

### P1C. Code edits and retrieval

- [ ] **P1C-01** Build the same edit fixtures for unique exact search/replace, Serena symbol edits, and unified diffs; include stale hashes, ambiguous matches, multiline replacements, and wrong files. **Accept:** fixtures and expected outcomes are versioned.
- [ ] **P1C-02** Run at least 30 measured edit attempts; score format validity, correct target, clean apply, functional correctness and successful recovery separately. **Accept:** one v0 edit primitive selected on evidence, with a fallback/stop policy.
- [ ] **P1C-03** Compare `rg` + bounded reads to Serena navigation for locating relevant symbols and tests; measure indexing overhead and tool output sizes. **Accept:** source-anchored recall/precision and latency report.
- [ ] **P1C-04** Examine Aider's repo map as a measured optional retrieval feature rather than implementing one automatically. **Accept:** retain/defer decision based on baseline or targeted evaluation.

### P1D. Security and sandbox feasibility

- [x] **P1D-01** Test bubblewrap on target Ubuntu host with real AppArmor/user-namespace settings. **Accept:** startup result, mount/network isolation settings and repeatable probe.
  Evidence: `3162163b25c460842f8d6b599aa4ad8cad26b4fc` | `uv run autocoder sandbox-probe` | observed BLOCKED_ENVIRONMENT; isolation gate remains closed | [checkpoint](evidence/STAGE0_FOUNDATION_2026-10-19.md) | 2026-10-19T11:15:32.717543+00:00
- [ ] **P1D-02** Prove the configured sandbox blocks reads of secret sentinels, writes outside worktree and disallowed network calls. **Accept:** all negative tests fail as expected, with logs.
- [ ] **P1D-03** Define controlled dependency preparation (download/cache vs executable installation/build hooks). **Accept:** no untrusted setup hook is executed unrestricted outside isolation.
- [ ] **P1D-04** Document a validated alternative if bubblewrap is unavailable, or explicitly constrain the product to supervised mode. **Gate:** no unattended tests/builds without proven isolation; do not bypass host security controls.

### P1E. Microsoft Agent Framework spike

- [ ] **P1E-01** Implement only a tiny MAF spike: remote/local Ollama, tool calls, Serena MCP, fresh contexts and structured outputs. **Accept:** actual run artifacts, current API/version pins and known workarounds.
- [ ] **P1E-02** Compare that tiny spike to direct Python `asyncio` + Ollama/MCP on complexity, reliability and observability; decide **use MAF** or **do not use MAF**. **Gate:** no full second backend or ambiguous mandatory framework dependency.

## P2 — End-to-end Stage 0 gate

- [ ] **P2-01** Prepare optimized OpenCode baseline with corrected Ollama context/tooling and the same model digest as our runner. **Accept:** recorded commands, config and fairness limitations.
- [ ] **P2-02** Prepare Aider baseline with matching model and comparable allowed context, tokens, time and test access. **Accept:** reproducible configuration and fairness limitations.
- [ ] **P2-03** Build the minimal test harness to run orient → plan → edit → check on clean fixture copies with strict caps; this is not yet the general application. **Accept:** headless execution produces trace, diff and check result.
- [ ] **P2-04** Run the eight pre-registered Python/Rust tasks against baselines and our harness, with held-out oracles and independent workspaces. **Accept:** no task swaps after results and no oracle exposure.
- [ ] **P2-05** Repeat the preselected subset, classify failures and report task-level unrecoverable error rates, regressions, time/tokens and context/caching effects. **Accept:** raw outputs, summary and clear small-sample uncertainty.
- [ ] **P2-06** **STAGE 0 GO/NO-GO DECISION.** Apply frozen policy in `SPEC.md` §11.4. **Accept:** signed-off proceed/change-model/change-tools/stop decision with evidence; no claim of superiority from a tiny sample.

## P3 — v0 deterministic coordinator and model interface (depends on P2-06 go)

- [ ] **P3-01** Implement task/phase state machine and outcome vocabulary from `SPEC.md` §3, §10, with deterministic transitions and unit tests.
- [ ] **P3-02** Implement chosen `ModelBackend` with endpoint override, model ID, timeout/cancel, usage metrics, bounded retries for inference-only calls, and pinned request context.
- [ ] **P3-03** Implement fresh-context phase builder with stable prefixes, token/schema accounting, compact structured evidence, context reserves, and no inherited prior phase transcript.
- [ ] **P3-04** Implement schema-validated orient/plan/implementation artifacts with grounding to paths, hashes and actual source revisions; reject invalid/stale handoffs.
- [ ] **P3-05** Implement in-phase tool/step cap, duplicate tool-call fingerprint detection, observation truncation, task token/time cap, one replan and bounded repairs. **Accept:** seeded looping agent stops safely and reports exact reason.
- [ ] **P3-06** Implement versioned event emitter and headless CLI consuming/printing task status, diff and approvals. **Accept:** batch mode and live event subscriber receive consistent state; no TUI prerequisite.

## P4 — v0 tool gateway, Serena and source edits (depends on P3)

- [ ] **P4-01** Implement scoped `search_text`, `read_file_range`/`read_symbol`, `find_references`, `apply_edit`, and `run_named_check` contracts using typed inputs/outputs and bounded responses.
- [ ] **P4-02** Enforce canonical root, symlink, role/phase permissions, protected-path policy, timeout and output caps **in gateway code**. **Accept:** negative tests block cross-repo writes and unauthorized commands.
- [ ] **P4-03** Supervise one Serena MCP server per active task worktree; verify active root and handle cold startup/restart/timeout; provide safe `rg` fallback where valid.
- [ ] **P4-04** Implement the Stage 0-selected edit primitive with unique targets, expected hashes, atomic/rollback-aware application and actual-diff inspection. **Accept:** ambiguous/stale/partial cases cannot be silently accepted.
- [ ] **P4-05** Capture source provenance, tested revision, relevant symbol refs and bounded evidence snippets; invalidate stale references after edits.

## P5 — v0 Git lifecycle and durable side effects (depends on P3–P4)

- [ ] **P5-01** Create collision-checked local task branch and isolated Git worktree from recorded exact base SHA; protect original checkout and pre-existing dirty files.
- [ ] **P5-02** Implement per-worktree lock and write precondition checks; reject unauthorized path/symlink escapes and concurrently changed files.
- [ ] **P5-03** Implement project-scoped append-only JSONL event journal and content-hashed evidence files outside the Git repo. **Accept:** events have task/operation IDs, UTC times, expected and observed state; secrets and source dumps excluded.
- [ ] **P5-04** Journal intent → execution → observed outcome for edits and Git side effects. **Accept:** seeded crash between edit and outcome results in reconciliation without duplicate mutation.
- [ ] **P5-05** Implement safe restart/resume after killed process, validating worktree identity, branch, hashes, journal tail and unresolved intents before further action.
- [ ] **P5-06** Surface real diff, changed files, protected-test/config changes, and explicit **user-controlled** integration. **Accept:** no unexpected push, PR, merge, or main-branch mutation.
- [ ] **P5-07** Measure Serena/LSP and Rust/Python cache startup in task worktrees; use only validated cache-sharing strategies.

## P6 — v0 sandboxed checks, test integrity and repair (depends on P3–P5; P1D gate)

- [ ] **P6-01** Implement configured named checks for Python and Rust; record baseline and candidate exit codes, timestamps, exact revision and artifacts.
- [ ] **P6-02** Execute unattended compilation/tests only inside the validated confinement backend. **Accept:** disabling/unavailable isolation results in fail-closed state, not host execution.
- [ ] **P6-03** Implement safe dependency preparation/caching and offline check execution; verify build hooks cannot bypass the sandbox boundary.
- [ ] **P6-04** Enforce protected existing tests/config/CI paths and review of explicit requested test modifications. **Accept:** a malicious/vacuous test change cannot obtain completion by itself.
- [ ] **P6-05** Implement reproduce-first checks: bug regression fails on base for expected reason and passes on candidate; report inconclusive reproduction rather than pretending success.
- [ ] **P6-06** Implement deterministic verification matrix and repair cycle with bounded diagnostics and independent held-out acceptance checks. **Accept:** failing checks never become pass via model assertion.
- [ ] **P6-07** Run end-to-end v0 on real representative tasks; independently inspect diffs, tests, recovery and task statuses. **Accept:** every `SPEC.md` §12 criterion has a linked evidence artifact.

## P7 — Native multi-project / multi-Ollama v0 acceptance

- [ ] **P7-01** Implement per-project configuration for canonical repository path, Ollama URL/model, permissions, task workspace and evidence directory; store secrets outside tracked config.
- [ ] **P7-02** Run two separate headless AI-coder processes on one host: Project A → remote/local Ollama A and Project B → remote/local Ollama B. **Accept:** both run concurrently without Docker/Podman.
- [ ] **P7-03** Prove separate worktrees, Serena processes, task IDs, journals and allowed path roots. **Accept:** deliberate cross-project file/tool requests are refused.
- [ ] **P7-04** Verify secure remote inference options (SSH tunnel/VPN/approved LAN), connection errors, and isolation when one server goes offline. **Accept:** other project's task state remains intact.
- [ ] **P7-05** Publish an end-to-end evidence report: model/runtime matrix, benchmark results, open limitations, and honest local-vs-CI-vs-human acceptance state. **Gate:** v0 declared complete only if `SPEC.md` §12 passes.

---

## P8 — After v0: terminal experience and optional integrations (not gate for v0)

- [ ] **P8-01** Build a native TUI as a client of the existing event stream: task prompt, phase/tool status, diff/evidence, approve/reject, stop, and resume.
- [ ] **P8-02** Add Grounded Docs (local/self-hosted documentation MCP) against one controlled corpus; benchmark retrieval benefit and token cost before expanding sources.
- [ ] **P8-03** Evaluate SearXNG and Fetch MCP for optional public search with explicit privacy/network policy; no paid API dependency.
- [ ] **P8-04** Add `gh` wrapper for approved GitHub Actions dispatch and exact-commit CI inspection, with retries, output bounds and no uncontrolled remote mutation.
- [ ] **P8-05** Evaluate separate Research/Architect/Developer/Reviewer agents **only** against the same single-loop baseline and equal budgets; keep the simpler loop unless task success measurably improves.
- [ ] **P8-06** Evaluate multi-model role routing, alternate quantizations, Kotlin/Android testing and richer memory or dashboard only when driven by task evidence.
- [ ] **P8-07** Consider SQLite migration only if JSONL query/transaction/concurrency requirements demonstrate a need; preserve replay compatibility.

## Completion record template

Copy under any checked milestone:

```text
Evidence:
  Code revision: <exact local commit SHA or N/A>
  Tool/model/runtime: <versions and digest>
  Test/experiment: <command or benchmark ID>
  Outcome: <pass/fail with relevant measurements>
  Artifacts: <relative evidence paths + hashes>
  UTC timestamp: <timestamp>
  Exceptions/limitations: <none or explicit explanation>
```

## Governing source documents

- [`SPEC.md`](SPEC.md) — authoritative scope, invariants and gates.
- `LOCAL_AI_CODER_ARCHITECTURE_DESIGN_REVIEW_2026-10-19.md` — first design proposal; historical, not normative.
- `CLAUDE_REVIEW_AND_V0_OUTLINE_2026-10-19.md` — first critique and slim v0 outline; historical.
- `LOCAL_AI_CODER_REVISED_ARCHITECTURE_CLAUDE_REVIEW_2026-10-19.md` — revised design discussion; historical.
- `CLAUDE_SECOND_REVIEW_2026-10-19.md` — second critique; reconciled into this checklist.

**Initial status:** Every task remains unchecked. No benchmark or software implementation is claimed complete by creating these documents.
