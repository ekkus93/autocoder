# Local AI Coder — Implementation TODO

**Status:** v0 and terminal UI verified; hosted push/PR CI passes with release-only artifacts
**Date:** 2026-10-19  
**Authority:** [`SPEC.md`](SPEC.md)  
**Primary goal:** Build a local-first autonomous coding system that makes small LLMs substantially more useful by improving context management, code retrieval, tool execution, and verification.

> **Rules for execution:** Work dependency-first. Never mark an item complete merely because code exists or a model reports success. Add commit SHA, pinned version, test command/result and evidence path for every completed milestone. Do not claim real hardware/CI/human acceptance without real evidence. Stage 0 is a hard gate; do not build the full v0 or TUI before viability is established. Microsoft Agent Framework is optional; Ralph Bridge, paid API dependencies, VS Code integration and mandatory Docker/Podman are excluded.

## Current execution checkpoint

The owner approved the custom v0. The persistent task CLI, bounded fresh phases,
scoped tools, confined navigation/checks, durable intent/outcome recovery and
controlled dependency preparation are implemented. The full suite now passes 77 tests (67 at the v0 evidence checkpoint).
Two repository policy repairs and two native Python/Rust project processes have
verified local outcomes; original checkouts were preserved during successful runs.

Only one Ollama endpoint is available, as confirmed by the owner. Shared-endpoint
concurrency is verified. The owner explicitly requested skipping the two-server
test on 2026-10-19. SPEC 1.1 defers independent-server/offline-server acceptance,
which remains untested. P6-07/P7-05 close under this revised scope; P7-02/P7-04
retain their untested portions as deferred.

P8-01's native terminal client is verified, P8-03's source/privacy evaluation is
recorded, and P8-07's workload review retains JSONL. P8-04's CI wrapper and the
owner-requested lint/test workflow now uses hosted Ubuntu with automatic branch/PR
checks and artifacts only for successful `v*` tag pushes. No self-hosted runner is
required. See the [hosted CI checkpoint](evidence/GITHUB_ACTIONS_2026-10-19.md) for
successful remote qualification and zero-artifact checks; the operator client
still requires an approved dispatch plan for mutation.
P8-02/P8-05/P8-06 remain conditional and untested, as detailed in the
[P8 checkpoint](evidence/P8_TERMINAL_AND_INTEGRATIONS_2026-10-19.md). See the
[v0 evidence and acceptance matrix](evidence/V0_IMPLEMENTATION_2026-10-19.md)
and [task command guide](V0.md). Original Stage 0 scores/registrations are unchanged.

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
- [x] **P0-04** Record exact model names/digests, quantization, chat templates, Ollama and client builds, Python/Serena versions, host/GPU details, tool inventories and licenses. **Accept:** reproducibility manifest emitted before every run.
  Evidence: `225510a894a5c7d1a86d2523d7545e6ded120071` | `per-run inventory; scripts/record_integrations.py` | manifests include model/template/build/host and independent integration inventory | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P0-05** Pre-register **five micro-experiment families** and **eight end-to-end tasks** (4 Python, 4 Rust) with fixed task prompts, protected oracles, scoring scripts, model settings, allowed tools and resource caps. **Accept:** immutable versioned benchmark manifest with checksums.
  Evidence: `225510a894a5c7d1a86d2523d7545e6ded120071` | `frozen benchmarks/v2, v3, v4` | five families and eight tasks registered per version; chronological limitations recorded | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P0-06** Set and freeze provisional Stage 0 thresholds from `SPEC.md` §11.4 *before* scored evaluation; provide an explicit change-control process. **Accept:** scored suite will refuse an unversioned changed threshold/budget.
  Evidence: `225510a894a5c7d1a86d2523d7545e6ded120071` | `verify_engines; tests/test_foundation.py` | checksum-bound gates and budgets reject changed assets | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P0-07** Implement baseline/hidden-oracle scoring and test-tamper detection. **Accept:** held-out checks are unreadable from candidate worktrees; a deliberate agent-side attempt to weaken tests is flagged.
  Evidence: `49cb356db41b7a71bd5f275bcb8f6294d4a9dabe` | `uv run pytest tests/test_evaluator.py` | private scoring and protected-test tamper detection verified | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P0-08** Select fixed task budget defaults (wall time, request tokens, output tokens, tool calls, repairs) and capture per-run usage. **Accept:** hard limits are enforced and produce `BUDGET_EXHAUSTED`, never false success.
  Evidence: `225510a894a5c7d1a86d2523d7545e6ded120071` | `uv run pytest; pilot-v4-01` | hard caps; actual budget failures retained as failures | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z

Registration chronology: runtime/tool scoring used frozen v2; subsequent component
adapters used v3; baseline qualification preceded frozen v4. A single complete
engine was not frozen before every earlier exploratory/integration activity.
Per-family source fingerprints and failures are retained; no retroactive common
pre-registration or global all-green result is claimed.

## P1 — Stage 0 micro-gates (do not start full v0 before decision)

### P1A. Runtime and context feasibility

- [x] **P1A-01** Probe Qwen3.5-9B on Ollama at 16K/32K/64K, and 128K only if practical. Record requested vs observed context, model residency, memory, prefill/generation throughput, failures and context quality. **Accept:** reproducible table with actual measurements.
  Evidence: `49cb356db41b7a71bd5f275bcb8f6294d4a9dabe` | `runtime-v2-01` | six allocation/short-context probes; full-window quality and physical GPU telemetry unverified | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P1A-02** Compare thinking enabled/disabled for relevant tasks, including output-budget and tool-use impact. **Accept:** phase-level metrics; no unsupported “thinking is always better” claim.
  Evidence: `d5f14acd2432c914aa78a25a45c0b457a7548b4b` | `runtime-v2-01; cache-v3-01` | thinking effects measured under fixed response limits | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P1A-03** Test remote Ollama connectivity/timeout/retry and non-ambiguous inference recovery. **Accept:** endpoint failure produces auditable error without modifying source or losing state.
  Evidence: `d5f14acd2432c914aa78a25a45c0b457a7548b4b` | `scripts/probe_transport.py; transport-01` | refusal/timeout/fresh recovery; source unchanged; controlled TCP faults, no second-host claim | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z

### P1B. Tool calling and prompt/cache behavior

- [x] **P1B-01** Test Ollama native tool and structured-output calls versus its OpenAI-compatible API using the actual model/chat template. **Accept:** first-try schema, semantic correctness, and recovered/unrecoverable failure rates are distinct.
  Evidence: `d5f14acd2432c914aa78a25a45c0b457a7548b4b` | `tools-v2-01; handoffs-v3-01` | tool calls pass by one recovery; compatible structured handoff fails | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P1B-02** Compare 4-, 6- and 12+-tool schema inventories over at least 40 representative tool-selection/argument trials. **Accept:** recorded schema-token cost and tool-choice correctness, including difficult negative cases.
  Evidence: `49cb356db41b7a71bd5f275bcb8f6294d4a9dabe` | `tools-v2-01` | 240 trials; 40 per API/inventory; narrow repeated scenario set | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P1B-03** Compare stable fixed 5–6 tool definitions with per-phase subsets for correctness, prompt-cache reuse and latency. Keep `num_ctx` fixed within each arm. **Accept:** chosen approach justified by measurements.
  Evidence: `d5f14acd2432c914aa78a25a45c0b457a7548b4b` | `cache-v3-01` | phase subsets selected from schema/latency measurements; limited cache evidence | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P1B-04** Check Pydantic/JSON Schema handoff decoding and bounded recovery of malformed responses. **Accept:** invalid outputs never silently enter the coordinator state.
  Evidence: `d5f14acd2432c914aa78a25a45c0b457a7548b4b` | `handoffs-v3-01; tests/test_handoffs.py` | strict decode, stale/unknown rejection, one seeded recovery | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [ ] **P1B-05** If tool parsing is a persistent blocker, run a small diagnostic using llama.cpp server and/or another quantization to identify the failure layer. **Accept:** documented root-cause hypothesis and tested mitigation or a clear no-go.

P1B-05 is conditional and was not triggered by the tool-choice results. The later
v4 edit-envelope failure is addressed by a separately registered flat tool interface.

### P1C. Code edits and retrieval

- [x] **P1C-01** Build the same edit fixtures for unique exact search/replace, Serena symbol edits, and unified diffs; include stale hashes, ambiguous matches, multiline replacements, and wrong files. **Accept:** fixtures and expected outcomes are versioned.
  Evidence: `d5f14acd2432c914aa78a25a45c0b457a7548b4b` | `benchmarks/v3/edit_trials.json` | five scenarios shared across three formats | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P1C-02** Run at least 30 measured edit attempts; score format validity, correct target, clean apply, functional correctness and successful recovery separately. **Accept:** one v0 edit primitive selected on evidence, with a fallback/stop policy.
  Evidence: `d5f14acd2432c914aa78a25a45c0b457a7548b4b` | `edits-v3-01` | 90 attempts; exact selected with guarded preconditions and one recovery | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P1C-03** Compare `rg` + bounded reads to Serena navigation for locating relevant symbols and tests; measure indexing overhead and tool output sizes. **Accept:** source-anchored recall/precision and latency report.
  Evidence: `d5f14acd2432c914aa78a25a45c0b457a7548b4b` | `retrieval-v3-01` | 8/8 each on narrow one-symbol fixtures; startup/output measurements saved | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P1C-04** Examine Aider's repo map as a measured optional retrieval feature rather than implementing one automatically. **Accept:** retain/defer decision based on baseline or targeted evaluation.
  Evidence: `225510a894a5c7d1a86d2523d7545e6ded120071` | `repomap-01` | 8/8 symbols without inference; retain baseline map, defer custom map | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z

### P1D. Security and sandbox feasibility

- [x] **P1D-01** Test bubblewrap on target Ubuntu host with real AppArmor/user-namespace settings. **Accept:** startup result, mount/network isolation settings and repeatable probe.
  Evidence: `3162163b25c460842f8d6b599aa4ad8cad26b4fc` | `uv run autocoder sandbox-probe` | observed BLOCKED_ENVIRONMENT; isolation gate remains closed | [checkpoint](evidence/STAGE0_FOUNDATION_2026-10-19.md) | 2026-10-19T11:15:32.717543+00:00
  Resumption: `832f9fae6c39f99bac7c709b13ab2828f0edcbb7` | `sandbox-resume-01` | VERIFIED_LOCAL; all five checks pass after policy installation | [component report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | 2026-10-19T21:30:39Z
- [x] **P1D-02** Prove the configured sandbox blocks reads of secret sentinels, writes outside worktree and disallowed network calls. **Accept:** all negative tests fail as expected, with logs.
  Evidence: `225510a894a5c7d1a86d2523d7545e6ded120071` | `uv run pytest tests/test_isolation.py; sandbox-resume-01` | actual sentinel/write/network probes pass after administrator policy installation | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P1D-03** Define controlled dependency preparation (download/cache vs executable installation/build hooks). **Accept:** no untrusted setup hook is executed unrestricted outside isolation.
  Evidence: `d5f14acd2432c914aa78a25a45c0b457a7548b4b` | `uv run pytest tests/test_isolation.py` | hostile hook confined; dependency policy documented; general acquisition unavailable | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P1D-04** Document a validated alternative if bubblewrap is unavailable, or explicitly constrain the product to supervised mode. **Gate:** no unattended tests/builds without proven isolation; do not bypass host security controls.
  Evidence: `225510a894a5c7d1a86d2523d7545e6ded120071` | `tests/test_evaluator.py; docs/DEPENDENCY_PREPARATION.md` | fail closed without qualified bubblewrap; no alternate or host execution supported | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z

### P1E. Microsoft Agent Framework spike

- [x] **P1E-01** Implement only a tiny MAF spike: remote/local Ollama, tool calls, Serena MCP, fresh contexts and structured outputs. **Accept:** actual run artifacts, current API/version pins and known workarounds.
  Evidence: `225510a894a5c7d1a86d2523d7545e6ded120071` | `experiments/maf/spike.py; maf-spike-01 and -02` | negative feasibility result; MCP initialization blocks tool qualification, failures retained | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P1E-02** Compare that tiny spike to direct Python `asyncio` + Ollama/MCP on complexity, reliability and observability; decide **use MAF** or **do not use MAF**. **Gate:** no full second backend or ambiguous mandatory framework dependency.
  Evidence: `225510a894a5c7d1a86d2523d7545e6ded120071` | `MAF/direct component comparison` | choose direct asyncio plus independent MCP; MAF not selected | [report](evidence/STAGE0_COMPONENTS_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z

## P2 — End-to-end Stage 0 gate

- [x] **P2-01** Prepare optimized OpenCode baseline with corrected Ollama context/tooling and the same model digest as our runner. **Accept:** recorded commands, config and fairness limitations.
  Evidence: `225510a894a5c7d1a86d2523d7545e6ded120071` | `opencode-qualification-02; pilot-v4-01` | pinned binary/custom short prompt/native-adapted provider qualified; fairness caveats recorded | [report](evidence/STAGE0_PILOT_V4_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P2-02** Prepare Aider baseline with matching model and comparable allowed context, tokens, time and test access. **Accept:** reproducible configuration and fairness limitations.
  Evidence: `225510a894a5c7d1a86d2523d7545e6ded120071` | `aider-qualification-02; pilot-v4-01` | isolated locked uv environment and bounded inference proxy qualified | [report](evidence/STAGE0_PILOT_V4_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P2-03** Build the minimal test harness to run orient → plan → edit → check on clean fixture copies with strict caps; this is not yet the general application. **Accept:** headless execution produces trace, diff and check result.
  Evidence: `225510a894a5c7d1a86d2523d7545e6ded120071` | `scripts/run_pilot.py; tests/test_pilot.py` | finite headless harness emits trace/diff/private terminal score | [report](evidence/STAGE0_PILOT_V4_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P2-04** Run the eight pre-registered Python/Rust tasks against baselines and our harness, with held-out oracles and independent workspaces. **Accept:** no task swaps after results and no oracle exposure.
  Evidence: `225510a894a5c7d1a86d2523d7545e6ded120071` | `pilot-v4-01` | all 24 initial runs complete; no task swaps; loop 3/8 versus baseline 7/8 each | [report](evidence/STAGE0_PILOT_V4_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
- [x] **P2-05** Repeat the preselected subset, classify failures and report task-level unrecoverable error rates, regressions, time/tokens and context/caching effects. **Accept:** raw outputs, summary and clear small-sample uncertainty.
  Evidence: `225510a894a5c7d1a86d2523d7545e6ded120071` | `pilot-v4-01` | 18 preselected repeats complete; rates/usage in v4 report; no isolated cache ablation | [report](evidence/STAGE0_PILOT_V4_2026-10-19.md) | reviewed 2026-10-19T21:30:39Z
  Corrective evidence for P2-03–05: `832f9fae6c39f99bac7c709b13ab2828f0edcbb7` | `scripts/run_pilot_v5.py` with frozen digest `c04da250ab2f317ff8f4dabef3f18d91530e75811d6ed5a68f730e89ade87307` | 42 runs complete; original tasks/oracles retained; v5 is a different registered condition | [report](evidence/STAGE0_PILOT_V5_2026-10-19.md) | reviewed 2026-10-19T21:39:48.581736+00:00
- [x] **P2-06** **STAGE 0 GO/NO-GO DECISION.** Apply frozen policy in `SPEC.md` §11.4. **Accept:** signed-off proceed/change-model/change-tools/stop decision with evidence; no claim of superiority from a tiny sample.

  Decision: owner approved custom v0 in this session (“Ok. Let's do that.”) after reviewing the decision packet. Compact context usage and reliable recovery are the selected product goals. Numeric benchmark outcomes are unchanged; this is implementation authorization, not v0 acceptance. | 2026-10-19T22:26:54.990591+00:00

## P3 — v0 deterministic coordinator and model interface (depends on P2-06 go)

- [x] **P3-01** Implement task/phase state machine and outcome vocabulary from `SPEC.md` §3, §10, with deterministic transitions and unit tests.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `uv run pytest tests/test_v0.py` | deterministic transitions/outcomes; normal, invalid, repair and replan paths verified | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217094+00:00
- [x] **P3-02** Implement chosen `ModelBackend` with endpoint override, model ID, timeout/cancel, usage metrics, bounded retries for inference-only calls, and pinned request context.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `ModelBackend; v0 real and shared-endpoint runs` | native endpoint/digest checks, deadlines/cancellation, usage reservations; no ambiguous inference replay | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217104+00:00
- [x] **P3-03** Implement fresh-context phase builder with stable prefixes, token/schema accounting, compact structured evidence, context reserves, and no inherited prior phase transcript.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `ContextBuilder; MODEL_REQUEST artifacts` | fresh phase handoffs; within-phase native history; schema/input accounting and context reserves | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217108+00:00
- [x] **P3-04** Implement schema-validated orient/plan/implementation artifacts with grounding to paths, hashes and actual source revisions; reject invalid/stale handoffs.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `uv run pytest tests/test_v0.py; live task traces` | strict grounded findings/plans; unknown paths, stale hashes, duplicate names and changed check sets rejected | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217110+00:00
- [x] **P3-05** Implement in-phase tool/step cap, duplicate tool-call fingerprint detection, observation truncation, task token/time cap, one replan and bounded repairs. **Accept:** seeded looping agent stops safely and reports exact reason.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `uv run pytest tests/test_v0.py` | phase/total caps, duplicate fingerprints, bounded observations, three repairs and one restart/replan | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217113+00:00
- [x] **P3-06** Implement versioned event emitter and headless CLI consuming/printing task status, diff and approvals. **Accept:** batch mode and live event subscriber receive consistent state; no TUI prerequisite.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `autocoder-task; event-replay-audit.json` | native live JSONL stdout and journal replay agree; diff/status/cancel/resume interfaces implemented | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217116+00:00

## P4 — v0 tool gateway, Serena and source edits (depends on P3)

- [x] **P4-01** Implement scoped `search_text`, `read_file_range`/`read_symbol`, `find_references`, `apply_edit`, and `run_named_check` contracts using typed inputs/outputs and bounded responses.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `ToolGateway; live project traces` | typed bounded search/read/symbol/reference/edit/named-check interfaces; explicit fallback labels | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217130+00:00
- [x] **P4-02** Enforce canonical root, symlink, role/phase permissions, protected-path policy, timeout and output caps **in gateway code**. **Accept:** negative tests block cross-repo writes and unauthorized commands.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `uv run pytest tests/test_v0.py` | canonical scopes, symlink/hardlink rejection, role/plan permissions and protected-file policy verified | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217133+00:00
- [x] **P4-03** Supervise one Serena MCP server per active task worktree; verify active root and handle cold startup/restart/timeout; provide safe `rg` fallback where valid.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `scripts/probe_v0_navigation.py; v0-navigation-04` | confined worktree-mirror MCP ownership, active-root check, source-change restart and bounded fallback | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217136+00:00
- [x] **P4-04** Implement the Stage 0-selected edit primitive with unique targets, expected hashes, atomic/rollback-aware application and actual-diff inspection. **Accept:** ambiguous/stale/partial cases cannot be silently accepted.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `uv run pytest tests/test_v0.py; live task diffs` | unique exact edits, raw hashes, atomic replacement and ambiguous-outcome reconciliation | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217139+00:00
- [x] **P4-05** Capture source provenance, tested revision, relevant symbol refs and bounded evidence snippets; invalidate stale references after edits.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `HANDOFF/NAVIGATION/CHECK artifacts` | source/base hashes and actual line locations; invalid coordinates flagged and changed indexes restarted | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217145+00:00

## P5 — v0 Git lifecycle and durable side effects (depends on P3–P4)

- [x] **P5-01** Create collision-checked local task branch and isolated Git worktree from recorded exact base SHA; protect original checkout and pre-existing dirty files.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `v0-real-policy-05; v0-real-path-01; v0-projects-02` | named retained task branches/worktrees; successful runs preserve original status | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217160+00:00
- [x] **P5-02** Implement per-worktree lock and write precondition checks; reject unauthorized path/symlink escapes and concurrently changed files.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `uv run pytest tests/test_v0.py` | exclusive task lock, write preconditions and unexpected-file/source-change refusal | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217163+00:00
- [x] **P5-03** Implement project-scoped append-only JSONL event journal and content-hashed evidence files outside the Git repo. **Accept:** events have task/operation IDs, UTC times, expected and observed state; secrets and source dumps excluded.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `Journal; live JSONL traces` | private per-project state, fsynced hash chain, operation identities and hashed external evidence | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217167+00:00
- [x] **P5-04** Journal intent → execution → observed outcome for edits and Git side effects. **Accept:** seeded crash between edit and outcome results in reconciliation without duplicate mutation.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `SIGKILL and interrupted-commit tests` | intent before filesystem/Git changes, observed outcomes afterward; pending operations reconciled without duplicate writes | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217171+00:00
- [x] **P5-05** Implement safe restart/resume after killed process, validating worktree identity, branch, hashes, journal tail and unresolved intents before further action.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `full-loop SIGKILL/resume test` | policy/private assets, branch/HEAD/worktree, source hashes and journal revalidated; reservations survive restart | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217175+00:00
- [x] **P5-06** Surface real diff, changed files, protected-test/config changes, and explicit **user-controlled** integration. **Accept:** no unexpected push, PR, merge, or main-branch mutation.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `autocoder-task diff/status/approve/refuse/mark-integrated` | real diff and approval/integration record; no generated branch merged or remote mutation performed | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217179+00:00
- [x] **P5-07** Measure Serena/LSP and Rust/Python cache startup in task worktrees; use only validated cache-sharing strategies.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `v0-navigation-04; v0-projects-02 CHECK timings` | cold/warm navigation and fresh Python/Rust check costs recorded; no shared writable compiler/LSP cache qualified | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217184+00:00

## P6 — v0 sandboxed checks, test integrity and repair (depends on P3–P5; P1D gate)

- [x] **P6-01** Implement configured named checks for Python and Rust; record baseline and candidate exit codes, timestamps, exact revision and artifacts.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `VerificationRunner; real Python/Rust runs` | named checks record baseline/candidate exit, UTC times, exact source-tree hashes, base revisions and command artifacts | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217200+00:00
- [x] **P6-02** Execute unattended compilation/tests only inside the validated confinement backend. **Accept:** disabling/unavailable isolation results in fail-closed state, not host execution.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `TaskSandbox; confinement and dependency tests` | offline namespaced/cgroup execution only; failed qualification refuses host execution | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217204+00:00
- [x] **P6-03** Implement safe dependency preparation/caching and offline check execution; verify build hooks cannot bypass the sandbox boundary.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `uv run pytest tests/test_v0_dependencies.py` | inert bounded hash-pinned fetch, cache reuse, offline hostile hooks and read-only artifacts/prepared outputs | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217209+00:00
- [x] **P6-04** Enforce protected existing tests/config/CI paths and review of explicit requested test modifications. **Accept:** a malicious/vacuous test change cannot obtain completion by itself.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `tamper, protected-path, inline-test and private-oracle tests` | existing protected changes cannot pass silently; exact approvals are frozen in policy | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217214+00:00
- [x] **P6-05** Implement reproduce-first checks: bug regression fails on base for expected reason and passes on candidate; report inconclusive reproduction rather than pretending success.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `real policy/path and Python/Rust controlled tasks` | expected public signatures fail on bases, candidate checks pass; passing/unrelated bases stop inconclusively | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217220+00:00
- [x] **P6-06** Implement deterministic verification matrix and repair cycle with bounded diagnostics and independent held-out acceptance checks. **Accept:** failing checks never become pass via model assertion.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `repair/replan and private-failure tests; live accepted tasks` | deterministic all-check matrix, bounded public repair, terminal independent private acceptance | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217225+00:00
- [x] **P6-07** Run end-to-end v0 on real representative tasks; independently inspect diffs, tests, recovery and task statuses. **Accept:** every `SPEC.md` §12 criterion has a linked evidence artifact.

P6-07 evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` |
`uv run pytest` (67 passed), two real repository repairs and two controlled
mixed-language projects | local pass within SPEC 1.1 scope, reviewed 2026-10-19.
The owner deferred independent-server acceptance; that scenario was not run.
The [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) preserves failed attempts,
fixture corrections, revision/artifact hashes and explicit limitations.

## P7 — Native multi-project / multi-Ollama v0 acceptance

- [x] **P7-01** Implement per-project configuration for canonical repository path, Ollama URL/model, permissions, task workspace and evidence directory; store secrets outside tracked config.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `Project JSON policy; native live runs` | canonical repo/endpoint/model/state/scopes; private assets/runtime digests; credentials rejected in origins | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217249+00:00
- [ ] **P7-02** **Deferred: distinct-server portion (owner decision, 2026-10-19).** Run two separate headless AI-coder processes on one host: Project A → remote/local Ollama A and Project B → remote/local Ollama B. **Accept:** both run concurrently without Docker/Podman.
- [x] **P7-03** Prove separate worktrees, Serena processes, task IDs, journals and allowed path roots. **Accept:** deliberate cross-project file/tool requests are refused.
  Evidence: `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` | `v0-projects-02; project-isolation tests` | separate worktrees, journals, task IDs, navigation PIDs and roots; actual cross-project read refused | [v0 report](evidence/V0_IMPLEMENTATION_2026-10-19.md) | reviewed 2026-10-19T23:13:18.217259+00:00
- [ ] **P7-04** **Deferred: remote/two-server acceptance (owner decision, 2026-10-19).** Verify secure remote inference options (SSH tunnel/VPN/approved LAN), connection errors, and isolation when one server goes offline. **Accept:** other project's task state remains intact.
- [x] **P7-05** Publish an end-to-end evidence report: model/runtime matrix, benchmark results, open limitations, and honest local-vs-CI-vs-human acceptance state. **Gate:** v0 declared complete only if `SPEC.md` §12 passes.

P7-02/P7-04 availability checkpoint: the owner confirmed “There's only one ollama
endpoint.” Two native processes sharing that endpoint pass, and all inference-lock
intervals are disjoint. This is not evidence for two independent servers or one
server going offline while the other continues. The owner subsequently instructed:
“We need to skip that test because I only have one available.” SPEC 1.1 records
this explicit scope revision; deferred cases are not v0 blockers or passing tests.
P7-05 evidence: controller `3b035ac9fa089b3e05058f93ce70a1b5f4910e39` |
`scripts/summarize_v0.py` | [published report and acceptance matrix](evidence/V0_IMPLEMENTATION_2026-10-19.md) |
local scope verified, reviewed 2026-10-19; remote CI/hardware/human patch acceptance remain unclaimed.

---

## P8 — After v0: terminal experience and optional integrations (not gate for v0)

- [x] **P8-01** Build a native TUI as a client of the existing event stream: task prompt, phase/tool status, diff/evidence, approve/reject, stop, and resume.
  Evidence: `852b1e8fa8dfa7507021f4eaeb5c61f3773a71f0` | `uv run pytest -q` (77 passed; six terminal tests, including real PTY) | local pass; display limits and no manual usability acceptance documented | [P8 report](evidence/P8_TERMINAL_AND_INTEGRATIONS_2026-10-19.md) | reviewed 2026-10-20T00:01:33Z
- [ ] **P8-02** Add Grounded Docs (local/self-hosted documentation MCP) against one controlled corpus; benchmark retrieval benefit and token cost before expanding sources.
- [x] **P8-03** Evaluate SearXNG and Fetch MCP for optional public search with explicit privacy/network policy; no paid API dependency.
  Evidence: `852b1e8fa8dfa7507021f4eaeb5c61f3773a71f0` | pinned upstream source/configuration review | evaluation complete; retain offline core, services/adapters not installed or runtime-qualified | [P8 report](evidence/P8_TERMINAL_AND_INTEGRATIONS_2026-10-19.md) | reviewed 2026-10-20T00:01:33Z
- [ ] **P8-04** Add `gh` wrapper for approved GitHub Actions dispatch and exact-commit CI inspection, with retries, output bounds and no uncontrolled remote mutation.
  Partial evidence: `852b1e8fa8dfa7507021f4eaeb5c61f3773a71f0` | four CI tests and local workflow commands pass | wrapper prepared; hosted automatic CI configured with release-only artifacts; operator dispatch remains separately approved | [P8 report](evidence/P8_TERMINAL_AND_INTEGRATIONS_2026-10-19.md).
- [ ] **P8-05** Evaluate separate Research/Architect/Developer/Reviewer agents **only** against the same single-loop baseline and equal budgets; keep the simpler loop unless task success measurably improves.
- [ ] **P8-06** Evaluate multi-model role routing, alternate quantizations, Kotlin/Android testing and richer memory or dashboard only when driven by task evidence.
- [x] **P8-07** Consider SQLite migration only if JSONL query/transaction/concurrency requirements demonstrate a need; preserve replay compatibility.
  Evidence: `852b1e8fa8dfa7507021f4eaeb5c61f3773a71f0` | `scripts/audit_journal_workload.py --journal ... --output ...` | four journals, 68–79 events, median replay 1.51–2.18 ms; retain JSONL, no scale claim | [P8 report](evidence/P8_TERMINAL_AND_INTEGRATIONS_2026-10-19.md) | reviewed 2026-10-20T00:01:33Z

P8-02 requires a real docs-retrieval gap (SPEC §5.3); none has been demonstrated.
P8-05 has no role-ablation result, and P8-06 remains task-evidence conditional.
These unchecked items are pending experiments, not completed integrations.
P8-04 uses hosted CI after the owner requested GitHub Actions setup; no runner
provisioning is needed. Operator-client dispatch qualification remains separate
from automatic push/PR verification.

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

**Initial document status:** This checklist began with every task unchecked. Current completion claims require the evidence records above.
