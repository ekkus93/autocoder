# Local AI Coder — Technical Specification

**Status:** v0 locally verified within the owner-approved single-endpoint scope
**Version:** 1.1-draft
**Date:** 2026-10-19  
**Companion:** [`TODO.md`](TODO.md)  
**Design inputs:** `LOCAL_AI_CODER_ARCHITECTURE_DESIGN_REVIEW_2026-10-19.md`, `CLAUDE_REVIEW_AND_V0_OUTLINE_2026-10-19.md`, `LOCAL_AI_CODER_REVISED_ARCHITECTURE_CLAUDE_REVIEW_2026-10-19.md`, and `CLAUDE_SECOND_REVIEW_2026-10-19.md`.

> **Primary goal (user-approved):** Build a local-first autonomous coding system that makes small LLMs substantially more useful by improving context management, code retrieval, tool execution, and verification.
>
> **Status note:** This is a normative *design target*, not a claim that any capability, configuration, benchmark, sandbox, or integration is implemented or validated. The Stage 0 tests below decide which implementation choices are viable.

## 1. Scope and design principles

### 1.1 Confirmed decisions

1. **v0 uses one context-isolated coding loop**, not four parallel or conversational agents. Research, planning, implementation, and repair are phases in a single deterministic workflow.
2. **Microsoft Agent Framework (MAF) is a candidate integration, not a required architectural dependency.** A narrow feasibility spike decides whether to use it; direct Ollama + MCP + `asyncio` is an acceptable alternative.
3. **Reliability precedes autonomy:** objective benchmarks, safe edits, independent tests, auditable evidence, and constrained execution must work before expanding scope.
4. **Local-first and no mandatory paid services.** Model inference, code tooling, and the core workflow operate with freely usable, locally executable software; optional remote Ollama servers may be user-controlled.
5. **CLI/headless engine before TUI.** The user-facing product is terminal-first and ultimately includes a TUI; no VS Code extension or browser frontend is required.
6. **Use native `git` and optional `gh`.** Ralph Bridge is explicitly excluded. Docker and Podman are not required for installation, project separation, or normal operation.
7. **Project isolation:** separate AI-coder processes may operate on different repositories while connecting to different local or remote Ollama servers.
8. **Serena MCP** is the primary semantic-navigation candidate, always scoped to the *active task worktree*. Native `rg` and bounded file reads provide a fallback.
9. A model's confidence, a passing unit test, a local commit, remote CI, and human acceptance are **distinct states**. Never conflate them.

### 1.2 Terminology

- **MUST / MUST NOT:** required for the indicated milestone; a violation blocks acceptance.
- **SHOULD:** expected default; deviations require documented rationale.
- **MAY:** optional, not an acceptance blocker.
- **Stage 0:** finite feasibility/benchmark gate, *not* a full application implementation.
- **v0:** smallest working end-to-end coding loop after Stage 0 succeeds.
- **Post-v0:** optional capabilities admitted only on measured need.
- **Task:** one user-requested, bounded change against a recorded repository revision.
- **Phase:** independently initialized model context with defined inputs, tools, outputs, and budget.
- **Evidence:** immutable or content-hashed records of source state, edits, command results, and acceptance checks.

### 1.3 In scope for v0

- Local Python application, installed with `uv`, supporting local or remote Ollama endpoints.
- Deterministic coordinator; phase-scoped contexts; typed model-tool gateway; bounded loops and observations.
- `git` worktree isolation, named local task branches, safe reconciliation, diff/approval flow.
- `rg` plus Serena MCP for targeted repository navigation and optionally editing if qualified.
- One empirically selected primary code-edit primitive, with explicit mismatch/partial-failure handling.
- Reproduce-first bug-fix path; deterministic build/lint/test verification; bounded repair.
- Validated native OS sandbox for unattended build/test execution; safe failure when unavailable.
- Minimal append-only event log, evidence artifacts, recovery checks.
- Headless CLI with machine-readable events that can later drive the TUI.
- Independent project invocations with independent endpoints, directories, Serena sessions, and state.

### 1.4 Explicitly out of v0

- Four-agent conversations, an LLM orchestrator, agent debate, a second reviewer model.
- Automatic pushing, opening PRs, merging, or triggering GitHub Actions.
- Full MCP-server-manager UI, model-fleet dashboard, distributed daemon/scheduler.
- Grounded Docs lifecycle, SearXNG, Fetch MCP, general web browsing, embeddings/vector DB.
- Automatic model training/fine-tuning, system-wide knowledge graph, elaborate memory schema.
- VS Code integration; mandatory Docker/Podman; paid LLM/search/docs APIs.
- Unattended execution when a real, validated sandbox cannot be provided.

## 2. Logical architecture

```text
CLI (Stage 0 / v0) ─── Event stream ─── Future TUI
        │
        ▼
Deterministic coordinator (Python/asyncio)
 ├── State machine + task/attempt/phase budgets
 ├── Context builder (stable prefixes; scoped evidence; token accounting)
 ├── Model adapter (local/remote Ollama; optional MAF behind spike)
 ├── Typed tool gateway (policy, normalization, bounding, audit)
 │    ├── Serena MCP instance for active task worktree
 │    ├── rg + bounded file reads
 │    └── controlled edit operation
 ├── Git worktree / revision manager
 ├── Sandbox executor for named checks
 └── Append-only JSONL journal + evidence files
        │
        ▼
Task-local branch/worktree; source, tests and diffs
```

**Control-plane rule:** Python owns authorization, phase transitions, budgets, check results, task identity, write coordination, and completion criteria. LLM output supplies proposed findings and changes; it is never the authority for a gate.

### 2.1 Engine boundaries

The codebase SHOULD have replaceable interfaces for `ModelBackend`, `ToolGateway`, `RepositoryWorkspace`, `VerificationRunner`, `Journal`, and `EventSink`. The interfaces MUST remain small: avoid implementing a generic multi-agent framework in anticipation of future features.

- **ModelBackend:** prompt/message submission, tool calls, schema-constrained responses where supported, timeouts, cancellation and usage metrics.
- **ToolGateway:** validates and authorizes operations, handles exact project paths, bounds responses, records tool evidence.
- **RepositoryWorkspace:** records base SHA, acquires local task lock, creates/cleans worktrees, performs guarded edits, reports actual diffs.
- **VerificationRunner:** selects predeclared named checks, handles sandbox and dependency preparation, captures exit codes and evidence.
- **Journal:** durable task, operation-intent, outcome, and reconciliation events.
- **EventSink:** serializable status/change/progress events for CLI, benchmarks, and future TUI clients.

The engine MUST run without a TUI. No framework-level checkpoint may be treated as a transaction covering file-system or Git side effects.

## 3. Phase-oriented coding workflow

### 3.1 State machine

```text
PREFLIGHT → ORIENT → REPRODUCE_AND_PLAN → IMPLEMENT → VERIFY
                                          ▲             │
                                          └── REPAIR ←──┤ failed, budget remains
                                                       │
                                       VERIFIED_LOCAL ←─┘ passed
                                              │
                                    REPORT + USER INTEGRATION
```

Any phase may terminate in `NEEDS_USER`, `BLOCKED_ENVIRONMENT`, `BUDGET_EXHAUSTED`, `FAILED_VERIFICATION`, or `CANCELLED` with evidence. `VERIFIED_LOCAL` never implies CI, hardware, deployment, or human acceptance.

### 3.2 Preflight

- Resolve and canonicalize the repository root, selected worktree root, `.git` identity, model endpoint and allowed paths.
- Capture base commit SHA, branch, porcelain status, tool versions, model tag/digest, server/build info, configured and observed context where available.
- Reject dirty-source overwrites; use isolated task worktree by default.
- Validate sandbox and basic tool capabilities before allowing unattended mutating/test tasks.
- Create durable task ID, local branch/worktree and initial journal record before modification.

### 3.3 Orient (fresh context)

Use `rg`, scoped file slices and Serena to locate likely files, symbols, references and tests. Return **source-anchored evidence** with paths and revision, not a long free-form summary. File discovery MUST NOT alter the repository. A repo map is optional pending Stage 0 evidence (Aider comparison).

### 3.4 Reproduce and plan (fresh context)

- Record baseline check outcomes before production-code changes, where feasible.
- For bug fixes, prefer a reproducer that fails **on the base revision for the expected behavior/signature**, not merely any failed test. A newly written test that passes on base is not accepted as regression evidence.
- Distinguish environmental failure, pre-existing unrelated failure and target regression.
- Emit an ordered, scoped plan and independently measurable acceptance checks in schema-validated format. Do not generate a large speculative task graph.

### 3.5 Implement (bounded multi-turn context)

- Work on one bounded subtask at a time, under its worktree lock.
- Retrieve targeted evidence when needed; no full-repository dumps or raw 3,000-line tool logs.
- Apply edits through the **single qualified edit primitive** chosen in Stage 0. Every write requires precondition checks and is journaled.
- Capture the resulting Git diff and file hashes as authority; do not trust a model's narrative of what it changed.
- Edits outside the allowed root, symlink escapes, binary overwrites, or ambiguous match replacements MUST fail closed.

### 3.6 Verify (deterministic; no model verdict)

- Run configured formatter, lint, type-check/compile and targeted tests; execute a broader suite when appropriate and feasible.
- Only named and configured checks are callable by the model; shell command construction is outside its authority.
- Report process exit status, bounded diagnostics, hashes/revision, and timestamp. Store full logs out of context.
- A passing code-format check does not imply a passing test; report each separately.

### 3.7 Repair/replan (fresh context)

- On failure, provide the first relevant diagnostic, actual diff, unchanged acceptance criteria and known attempted fixes.
- Default candidate budgets: **20 model-visible tool calls per phase**, **3 repair attempts per subtask**, **1 architecture replan**, **2 identical unsuccessful operation fingerprints** before loop interruption, **2,048-token maximum returned observation per call**, and compaction/phase reset around **75–80%** of the available window.
- These numbers are initial tunable safeguards, not measured optimal values; Stage 0 MUST record variations. A task-level total token/call/time budget is required and MUST be set before execution.
- Detect repetitive read/search/edit loops *within* a phase, not only across repair attempts.
- On exhaustion, stop with a precise reason; never claim task success.

### 3.8 Optional review; reporting and approval

Deterministic checks come first. An LLM review of the *actual* diff MAY be added after experiments justify it, initially read-only and advisory. Completion report MUST include changed files, diff reference, checks run and results, unresolved uncertainty, task branch/worktree location, and separately labeled `local_tests`, `llm_review`, `remote_ci`, `hardware_acceptance`, `human_acceptance` statuses.

## 4. Context design, inference and tool schemas

### 4.1 Context isolation contract

Each phase starts a new model session or equivalently reset message context. **No phase inherits another phase's raw conversation, entire tool output, or private reasoning.** Handoffs use validated compact artifacts referencing source paths, hashes and stored evidence. The underlying model's actual context limit does not increase; **effective project working memory** comes from retrieval and persisted artifacts.

Each request's budget MUST account for system/developer prompt, rendered tool schemas, task/evidence, recent observations, thinking/output, and a safety reserve. Tool schema tokens are measured—not assumed negligible. Outputs and thinking tokens count toward the actual available capacity.

### 4.2 Prefix caching and tool-set experiments

Place stable instructions and, where supported, stable tool schemas before changing task/evidence text. Stage 0 MUST compare: (A) **fixed small tool set** across phases with gateway-side permissions vs (B) role-specific model-visible subsets. Compare tool-selection quality, schema size, prefill latency and cache reuse; neither is a universal default before measurements. Keep `num_ctx` fixed for a given endpoint/model process during a benchmark arm to avoid confounding reload behavior.

### 4.3 Ollama and model routing

- Stage 0 reference model: user's Qwen3.5-9B quantization on Ollama. Pin exact model digest, quantization, client/server versions and chat template details in results.
- Probe 16K, 32K and 64K *actual allocations*; test 128K only if supported efficiently. Do not infer GPU residency or effective quality from model-card maximum alone.
- Record CPU/GPU split, VRAM, prompt-processing speed, generation speed, context allocation, and observed stability. Remote endpoint probes are made against the correct server.
- Support thinking on/off as separate benchmark configurations when model/runtime supports it; never assume it improves every phase.
- Compare Ollama native tool/structured-output API with OpenAI-compatible API where feasible. If tool parsing fails, test a llama.cpp server as a diagnostic alternative, not as a v0 requirement.
- Concurrency defaults to one active inference request per server until measured; each project may point to an independent endpoint.

### 4.4 Typed handoffs

Pydantic/JSON Schema MUST validate machine-readable outputs for plans, findings, tool arguments and completion records. If provider-native schema-constrained decoding is available, use and test it; reject and boundedly repair invalid output rather than silently interpreting malformed YAML. Schema-valid != semantically correct: test both.

## 5. Tooling and MCP integration

### 5.1 Minimum model-visible tool API

The initial five conceptual tools are:

| Tool | Purpose | Safety constraint |
|---|---|---|
| `search_text` | Scoped `rg` search | Bounded match/result count; confined root |
| `read_file_range` or `read_symbol` | Read targeted source | Path/cursor bounds; citation to revision |
| `find_references` | Serena-supported reference lookup | Worktree-scoped; result cap |
| `apply_edit` | Qualified edit primitive | Precondition hashes + allowed paths + journal |
| `run_named_check` | Request configured verification | Named checks only, sandbox requirement enforced |

`git status`, repository map, and diffs SHOULD be collected deterministically by the coordinator and injected as bounded evidence; they do not need distinct model-visible tool schemas. The gateway MAY present a smaller subset per phase if measurements show a win. Agents MUST NOT receive general shell access or arbitrary MCP tool inventories by default.

### 5.2 Serena process ownership

- Start one Serena MCP server **per active worktree** where semantic tooling is required; pin its project path and confirm root on every session.
- Restrict exposed capabilities through the gateway; a tool not expressly permitted MUST be unreachable, regardless of the prompt.
- Validate MCP responses as untrusted; cap size, escape outside-root paths, time out stalled calls, and supervise server lifecycle.
- Measure startup, rust-analyzer/LSP cold indexing, health, and worktree cache overhead. Failure to start Serena may use `rg`/bounded-read fallback only when the task can still be completed without misleading claims.
- Pin and recheck Serena version, exact tool names and licensing. Serena application licensing differs from SolidLSP's; running an independently installed MCP process is the proposed local-use arrangement. Redistribution requires separate legal review.

### 5.3 Optional documentation and web search

Grounded Docs/docs-mcp-server is the first **optional** local documentation index; add one controlled documentation source only after tasks reveal a real retrieval gap. SearXNG, Fetch, embeddings and browser automation remain post-v0. No core feature may require a paid API. Search tools must not send private source snippets externally without explicit opt-in; returned docs/web content never overrides trusted task policy.

## 6. Editing, tests and anti-tampering

### 6.1 Editing candidate selection

Stage 0 MUST run the same edit fixtures against:

1. Exact-match search/replace with unique-match preconditions.
2. Serena symbol edits when supported by the pinned release/language.
3. Validated unified diffs.

The selected format is documented with **parse/format validity**, **apply success**, **correct target**, **functional correctness**, and **recovery rate** separately. Failed or partial applies are rejected and reconciled from Git state; no blind repeats after timeout.

### 6.2 Test integrity

- Existing tests, test fixtures, verification configuration, CI workflow files and acceptance scripts are **protected paths**. Changes MUST be flagged and require explicit approval before acceptance, unless the task explicitly authorizes an identified test change.
- A model-authored regression test MUST be demonstrated to fail on the unmodified base for the *expected reason* and pass on the candidate change; otherwise it is weak evidence.
- Independent held-out oracle tests MUST be physically inaccessible to the model and mutation worktree; do not merely omit them from prompts. They run from a separately controlled evaluator context against a copy or artifact of candidate code.
- Keep evaluation task fixtures unknown to the tested model where practical; favor private repositories at old SHAs and seeded defects to mitigate benchmark contamination.
- Compare baseline and candidate check results, recognizing pre-existing failures and environment differences.

## 7. Git workspaces and multi-project isolation

### 7.1 Task worktrees

- Autonomous tasks default to `git worktree add -b autocoder/task-<id> <task-path> <base-sha>` (or equivalent safe, collision-checked local branch). **No remote PR or branch is required.**
- Lock the worktree with an OS lock; ensure base SHA, branch identity and file precondition hashes remain consistent before writes.
- Worktree filesystem isolation does not imply process security isolation. The original user checkout is not modified by task edits.
- Keep task branch refs until user-controlled integration or explicit cleanup; never lose commits by deleting unreferenced detached HEADs.
- Report integration instructions and conflicts honestly; do not silently cherry-pick, merge, push or force-update protected branches.
- Record and measure dependency/build-cache and Serena startup costs. Shared downloaded dependencies or compiler caches require verification that their sharing cannot corrupt task isolation.
- **Supervised direct mode** MAY exist with explicit approval and dirty-tree protections; it is not the autonomous default.

### 7.2 Multiple projects and Ollama endpoints

- Project A and Project B MUST be launchable as **separate native processes** on the same Ubuntu host, using different repositories and independently configured endpoint settings, with no containers or global daemon. They MAY share one Ollama endpoint; inference requests to that endpoint must serialize.
- Independent-server concurrency, secure remote transport and one-server-outage acceptance are deferred until a second endpoint is available. The owner explicitly requested skipping this test on 2026-10-19; no two-server result is claimed.
- Each process MUST isolate config, worktree roots, logs, task IDs, journal and Serena process. Cross-project filesystem paths MUST be rejected by gateway root validation.
- Global installations of `git`, `gh`, `uv`, Python and shared stateless services MAY be reused.
- Remote Ollama credentials/addresses must not leak into model prompts. Avoid exposing unauthenticated Ollama directly to untrusted networks; prefer SSH tunnels/VPN or other approved secure transport.
- A multi-project dashboard, central GPU scheduler and cross-project orchestration are deferred.

### 7.3 `gh` policy (post-v0)

Native `git` is sufficient for v0. Later, a narrow `gh` wrapper MAY check exact-SHA CI, dispatch explicitly approved workflows, and access GitHub. No silent push, merge, PR creation, secrets retrieval, or destructive remote operations. Jobs must be correlated to the exact commit SHA tested.

## 8. Execution sandbox and threat model

### 8.1 Trust boundaries

Untrusted inputs include repositories, tests, build scripts, package installation hooks, model-generated code, downloaded pages, MCP server responses and documentation. Running `pytest`, `cargo test`, `npm test`, build scripts or package installation may execute arbitrary code. An allowlisted command name alone is **not** a sandbox.

### 8.2 Unattended execution requirements

- Probe whether bubblewrap can enforce restricted mounts, process limits and network restrictions on the actual Ubuntu host (including user-namespace/AppArmor policy). An equivalent verified OS isolation backend MAY substitute.
- Restrict sandbox visibility to a writable task worktree and explicitly required read-only dependencies/toolchains; deny unrelated projects, home credentials, SSH keys, host tokens, and private evaluation tests.
- By default, builds/tests have no network. The coordinator and model endpoint live outside that sandbox.
- Dependency preparation is a distinct controlled step. Downloads can be network-enabled under approved policy, but executable install/build hooks must not run unrestricted outside isolation. Verify cached deps and then run checks with network disabled.
- Prove negative tests: attempts to read a sentinel secret, write outside the worktree or contact the network are blocked.
- If a valid isolation backend is unavailable, **unattended code execution MUST fail closed**. Supervised operation MAY be offered with clear risk disclosure; never silently disable sandboxing or bypass host protections.
- The tool gateway MUST enforce restrictions independently of any model instruction. Model-generated URLs and remote text are data, not executable authorization.

## 9. Event journal, evidence and recovery

### 9.1 v0 storage

Use a simple per-project **append-only JSONL event stream** (plus content-hashed evidence files). SQLite is a permissible future upgrade if query/concurrency demands arise; do not require an elaborate schema for v0. Store outside the tracked repository under an application data directory. One writer/locked append per task is sufficient for the initial single-process model.

Minimum event fields: `event_id`, `event_version`, `utc_time`, `project_id`, `task_id`, `phase`, `kind`, `operation_id`, `base_sha`, `worktree_id`, `expected_hashes` (when relevant), `observed_hashes` (when relevant), `status`, and `evidence_ref`. Secrets and entire source bodies MUST NOT appear in the journal.

### 9.2 Side-effect protocol

For edits and Git mutations:

1. Durably record intent with expected revision/hash and unique operation ID.
2. Execute only after authorization and state precondition checks.
3. Read back actual filesystem/Git state, independently of model output.
4. Record observed outcome and evidence hash/reference.

On an ambiguous error, timeout or crash after intent, compare the actual worktree with expected and proposed changes. **Never blindly replay a possibly completed mutation.** If reconciliation is impossible, stop with `NEEDS_USER` or `BLOCKED_ENVIRONMENT`.

### 9.3 Events and recovery

The headless engine MUST emit versioned machine-readable events for phase start/end, tool calls, checks, state changes, required approvals and final outcome. The eventual TUI consumes the same stream rather than duplicating execution logic. Restart MUST revalidate project/worktree identity, branch SHA, status, locks, journal tail and any unresolved operation before resuming.

## 10. User controls, outcomes and UI

### 10.1 CLI and eventual TUI

Stage 0 uses a batch-capable CLI runner and JSON/JSONL output. v0 MUST offer a headless command to start tasks, inspect diff/evidence, approve or refuse integration, cancel and resume safely. The terminal TUI is a **post-v0 product requirement** consuming the same event stream; it is not on the Stage 0/v0 critical path. No IDE integration is planned.

### 10.2 Approval boundaries

Read-only repository exploration may proceed automatically within scope. Mutating source in an isolated task worktree may follow a configured policy, but **existing-test edits, protected configuration, integration into user branches, pushes, remote CI dispatch, credential/network exposure, and destructive operations require explicit user or pre-established policy authorization**. No operation obtains approval by prompting itself.

### 10.3 Outcome vocabulary

The implementation MUST support at least:

`PENDING`, `RUNNING`, `VERIFIED_LOCAL`, `FAILED_VERIFICATION`, `BLOCKED_ENVIRONMENT`, `BUDGET_EXHAUSTED`, `NEEDS_USER`, `CANCELLED`, and `INTEGRATED_BY_USER`.

Separate evidence fields for `format`, `lint`, `compile`, `tests`, `review`, `remote_ci`, `hardware`, and `human_acceptance` use `pass`, `fail`, `not_run`, `blocked`, or `unknown`. Never infer a `pass` from an unobserved check.

## 11. Stage 0 — finite feasibility gate

### 11.1 Purpose and limits

Answer one question before building a large harness: **Can the selected Qwen/Ollama setup reliably navigate, edit and validate real, bounded coding tasks with a constrained tool loop?** Stage 0 is capped to **five micro-experiment families** and an **initial eight-task end-to-end suite**, with at most four additional targeted tasks if needed to resolve a major ambiguity. Its purpose is detecting large effects and blockers, not proving small statistical differences.

Before running the scored suite, freeze the test cases, scoring scripts, allowed tools, budget, model settings and proposed gates. Record any changes as a new benchmark version, not a silent adjustment.

### 11.2 Micro-experiments (in dependency order)

| Family | Controlled comparison | Evidence |
|---|---|---|
| S0-A: Runtime/context | Actual context 16K/32K/64K; 128K only if viable; thinking on/off where supported | Model/runtime versions, `ollama ps`, memory, latency, errors |
| S0-B: Tool calls | 4/6/12+ tools; fixed vs per-phase schemas; native vs OpenAI-compatible API | First-try validity, semantic correctness, recovered vs unrecoverable failures, prefix metrics |
| S0-C: Edits | Unique search/replace, Serena symbol editing, unified diffs on same fixtures | Valid syntax, correct target, clean apply, repairability, oracle results |
| S0-D: Retrieval | `rg` and bounded reads; add Serena; compare repo map only if evidence warrants | Relevant-symbol accuracy, prompt size, latency, task effect |
| S0-E: Isolation/framework | bubblewrap policy and negative tests; tiny MAF spike against direct model/MCP integration | Sandbox proof or fail-closed; adapter-fit decision |

The MAF spike is **not** a separate full benchmark arm. Its decision is whether a small vertical slice can use Ollama calls, Serena MCP, isolated contexts and structured outputs without fighting framework defaults or bloating complexity. Document retain/reject with evidence.

### 11.3 End-to-end evaluation

- Use eight pre-registered tasks: four Python and four Rust, covering reproducible bugs and bounded multi-file changes. Prefer private historical revisions and injected defects; held-out oracle tests are inaccessible to the candidate worktree.
- Test **optimized OpenCode**, **Aider**, and the **minimal coding loop** with the same model/digest and comparable context, wall-clock, token and tool permissions to the extent supported; record non-equivalent features transparently.
- Repeat a small predetermined subset to estimate variance. **Do not claim statistical significance** from the eight-task sample.
- Record task success against independent oracle, unrecoverable tool/edit failures per task, first-try and recovered failure rates, changed-file scope, regression rate, total tokens, elapsed wall time, retrieval quality, and sandbox status.
- Keep a failure taxonomy: model/tool parsing, tool selection, wrong target, edit format, stale precondition, context overflow, test tampering, environment/build, sandbox, timeout, and coordination/recovery.

### 11.4 Provisional gate policy

The following are **initial engineering screening thresholds** to pre-register and, if justified, revise *before* any scored evaluation. They are not statistically validated guarantees:

1. **Zero unauthorized scope writes, secret exposure or sandbox escape** in safety probes; otherwise no unattended v0.
2. Across at least 40 representative tool-choice/argument trials, **≥90% semantically correct and schema-valid by at most one bounded recovery**. Report first-pass separately.
3. Across at least 30 measured edit attempts, **≥80% correct-target clean applies by at most one recovery**; report syntax-valid, apply and functional success separately.
4. In the eight-task pilot, at least **four independently verified completions** within the frozen resource budget and no acceptance-test tampering. This is only a minimum feasibility signal, not proof of superiority.
5. Benchmarks must show some actionable advantage over corrected OpenCode/Aider, or a clear unmet requirement they cannot provide; otherwise **reassess whether building this product is warranted**.
6. MAF selection requires passing its tiny feasibility spike *and* a documented simplification over direct integration. Otherwise choose direct `asyncio` + Ollama + MCP.

If the component gate fails, do not invest in a full TUI or multi-agent expansion. Diagnose model, quantization, Ollama chat template, edit format, or tool surface first; repeat as a newly versioned experiment.

## 12. v0 acceptance criteria

v0 is acceptable only when all the following have objective evidence. Version 1.1
records the owner's 2026-10-19 decision to skip the unavailable two-server test;
shared-endpoint isolation is the current acceptance scope. Evidence for the
criteria below is recorded in the [v0 acceptance matrix](evidence/V0_IMPLEMENTATION_2026-10-19.md).

- [x] A full loop completes a controlled task: baseline → orientation → plan → guarded edit → deterministic verification → bounded repair if needed → evidence-backed completion.
- [x] Each phase is demonstrably fresh-context, with structured bounded handoffs and measured token/schema consumption.
- [x] The qualified edit primitive correctly enforces unique target/path and hash preconditions and reconciles ambiguous mutations.
- [x] Existing tests/protected files cannot be silently weakened; held-out acceptance checks remain outside agent visibility.
- [x] Unattended checks execute in validated sandbox confinement; otherwise the engine refuses them.
- [x] JSONL intent/outcome records allow restart to identify and reconcile unresolved operations without duplicate edits.
- [x] An isolated local task branch/worktree is created and remains available for user integration; user checkout is unchanged.
- [x] Two native processes can run distinct repositories against the available shared Ollama endpoint without crossed paths or state, serializing inference requests. Independent-server acceptance is deferred, not passed.
- [x] Headless CLI emits machine-readable events, useful errors, actual diffs, test evidence, and honest outcome statuses.
- [x] No paid API, Ralph Bridge, IDE integration, or mandatory Docker/Podman is required.
- [x] Benchmarks and v0 results include exact model/runtime/tool versions, budgets, comparison evidence and explicit limitations.

## 13. Later milestones (not part of v0 acceptance)

- **User-facing TUI:** event-driven progress, task detail, diffs, approvals, cancellation, resume.
- **Local documentation retrieval:** Grounded Docs corpus and measured result-size budgeting.
- **Self-hosted public-web search:** SearXNG/Fetch with explicit privacy/network control.
- **GitHub workflow integration:** narrow, approved `gh` commands, exact-SHA CI evidence.
- **Higher-order agents:** separate planner/researcher/reviewer or multiple models *only after* ablation shows a real task-success gain.
- **Richer persistence, project dashboard, scheduling:** add only when workload warrants SQLite/global coordination.
- **Additional languages:** Kotlin/Android/TypeScript and project-specific tooling after Python/Rust baseline.

## 14. Validation and provenance

This specification translates the project owner's confirmed decisions and the two architecture-review cycles into testable targets. Stage 0 MUST pin current upstream versions and verify assumptions rather than relying on dated examples. Relevant references:

- Microsoft Agent Framework: <https://github.com/microsoft/agent-framework> (candidate only)
- Agent Framework MCP: <https://learn.microsoft.com/en-us/agent-framework/agents/tools/local-mcp-tools>
- Ollama structured outputs: <https://docs.ollama.com/capabilities/structured-outputs>
- Ollama context management: <https://docs.ollama.com/context-length>
- Serena MCP and component licensing: <https://github.com/oraios/serena> and <https://github.com/oraios/serena/blob/main/docs/01-about/060_license.md>
- Aider repo map: <https://aider.chat/docs/repomap.html>
- Aider Ollama instructions: <https://aider.chat/docs/llms/ollama.html>
- Git worktree: <https://git-scm.com/docs/git-worktree>
- bubblewrap: <https://github.com/containers/bubblewrap>
- GitHub CLI: <https://cli.github.com/manual/>

**Evidence rule:** Neither this specification nor the reviews proves runtime compatibility, model quality, safety or performance. Mark work complete only with reproducible test artifacts, observed results and pinned versions. The actionable dependency-order checklist is [`TODO.md`](TODO.md).
