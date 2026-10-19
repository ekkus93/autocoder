# Local AI Coder — Revised Architecture and Response to Claude's Review

**Document type:** Architecture design review / discussion draft  
**Date:** 2026-10-19  
**Revision:** 0.2 (second-review candidate)  
**Status:** **PROPOSAL — NOT AN IMPLEMENTATION SPECIFICATION OR TODO**  
**Intended audience:** Project owner, Claude, and subsequent architecture reviewers

**Inputs reviewed**

- `LOCAL_AI_CODER_ARCHITECTURE_DESIGN_REVIEW_2026-10-19.md` (original design proposal, v0.1).
- `CLAUDE_REVIEW_AND_V0_OUTLINE_2026-10-19.md` (Claude's critique and minimal v0 outline).
- Subsequent architectural assessment and decisions from the discussion.

> **Review objective:** Decide whether a small local LLM can become a practical autonomous coding assistant through focused retrieval, bounded contexts, disciplined tool use, and objective verification. Resolve the minimum architecture that allows this hypothesis to be tested honestly before authoring a normative `SPEC.md` or implementation `TODO.md`.
>
> **Evidence status:** This document synthesizes two design/review artifacts and subsequent analysis. It does **not** report that the proposed software, MCP combinations, API adapters, sandbox, or model configurations have been tested. Version-specific capability and licensing details remain **validation tasks** for Stage 0; cited documentation is a place to verify, not a substitute for an integration test.

---

## 1. Executive summary

The original proposal described a relatively ambitious **four-agent Microsoft Agent Framework system** with durable workflows, project memory, several MCP services, a TUI, and multi-project support. Claude's review made a compelling criticism: much of that infrastructure is speculative until a 9B-class model demonstrates robust tool calls and source edits. Four specialized prompts using one model do not automatically confer four independent capabilities. The likely benefit is **fresh, task-focused context**, which can be tested with a **single LLM loop divided into phases**.

**Revised recommendation:**

1. Run a **Stage 0 feasibility study** on the actual local/remote Ollama configuration, with an optimized OpenCode baseline.
2. Implement a **minimal, deterministic, one-model coding loop** with distinct fresh-context phases: orient, reproduce/plan, implement, deterministic verify, repair, and optional review.
3. Use **Serena MCP**, lexical search, a cheap repository map, local `git`, structured tool calls, isolated Git worktrees, and an append-only SQLite event/side-effect journal.
4. Run build and test commands inside a **validated OS-level sandbox for unattended execution**; containers are not a requirement.
5. Keep the model and orchestration interfaces narrow. **Microsoft Agent Framework remains a candidate adapter, not an unquestioned backbone**; compare it with direct Ollama + MCP + `asyncio` integration.
6. Preserve the product goals of a **native TUI**, **no paid inference/search APIs**, **no Ralph Bridge**, **no VS Code integration**, and **independent project instances** using distinct local or remote Ollama servers.
7. Add distinct Researcher/Architect/Developer/Reviewer agent instances, documentation indexing, self-hosted web search, and richer memory **only when measured evidence justifies them**.

The long-term vision is unchanged: **a context-efficient, evidence-driven autonomous coder for small local models**. The proposed implementation sequence is much narrower.

## 2. Requirements and non-goals

### 2.1 User-established requirements (retain)

- **Terminal-native interface:** TUI only. No required IDE extension or VS Code integration.
- **Free/open-source local stack:** no paid LLM, documentation, or search API needed for the core product. Remote hosts are user-controlled; outbound internet use is optional and explicit.
- **Ollama first, configurable:** Qwen3.5-9B is the primary experimental model; other models, quantizations, and inference servers can be substituted.
- **Context efficiency takes priority over raw speed:** the user accepts slower, sequential multi-pass work if it actually improves coding outcomes.
- **Serena MCP:** use semantic navigation and, if reliable, controlled source edits.
- **Native Git and `gh`:** use `git` locally and GitHub CLI for optional remote CI/GitHub tasks; **do not use Ralph Bridge**.
- **Multiple project processes on one computer:** Project A may use Ollama server A and Project B Ollama server B. Neither Docker nor Podman is required for this arrangement.
- **No container dependency:** native Ubuntu deployment; isolation for untrusted builds/tests must still be evaluated independently.
- **Transparency and safety:** visible diffs, test evidence, meaningful approval controls, and honest completion states.

### 2.2 Product goals

The system should ultimately support repository exploration, bug fixes, tests, refactors, and multi-file features. A successful task must be determined by **external evidence**—tests, diffs, static checks, or user acceptance—not just the model's assessment of itself.

The system should eventually resume interrupted work and support multiple independently configured projects without state collisions. However, a full fleet dashboard, general scheduling daemon, multi-user server, and advanced agent council are outside the first vertical slice.

### 2.3 Explicit exclusions

- No ChatGPT-specific Ralph Bridge.
- No VS Code extension.
- No paid SaaS dependency for required functionality.
- No Docker/Podman requirement for normal deployment or project separation.
- No automatic remote branch/PR per subtask as a universal policy.
- No assumption that four agents beat one phase-oriented loop.
- No elaborate vector-store or multi-tier project-memory architecture in v0.
- No unrestricted unattended execution of repository-supplied scripts.
- No `SPEC.md` or `TODO.md` as part of this review artifact.

---

## 3. Evaluation of Claude's critique

Claude's review emphasized the following concerns. The assessment below records **adopted recommendations**, **modified recommendations**, and **unresolved decisions**.

| Claude's point | Assessment | Revised position |
|---|---|---|
| Prove 9B tool use and edits before building the full product | Strong agreement | **Stage 0 go/no-go gate** |
| Four same-model agents are mostly four different prompts | Agreement | **One phased loop in v0**; compare multi-agent later |
| Deterministic coordinator beats an LLM coordinator | Strong agreement | Python state machine / `asyncio` |
| Agent Framework may not earn its complexity | Agreement that it must prove value | Benchmark **thin framework adapter vs direct Ollama/MCP** |
| Tool-schema tokens and tool-selection accuracy are ignored | Strong agreement | Measure schema overhead; limit per-phase tools |
| Patch/edit format is a critical missing decision | Strong agreement | Benchmark **symbol edits vs search/replace vs unified diff** |
| Fresh contexts can defeat prompt-prefix/KV caching | Agreement | Stable role prompts, bounded evidence, measure prefill latency |
| Security must precede unattended tests/builds | Strong agreement | Validate bubblewrap/equivalent; otherwise supervised only |
| Project memory is overbuilt | Strong agreement | Start with state, evidence, human conventions, and source references |
| Default to Git worktrees per task | Agreement with qualifications | **Detached/local isolated worktrees by default**; direct mode opt-in |
| Reproduce-first and baseline tests | Strong agreement | Include explicit baseline and failing-test workflow |
| Add cheap repository map | Agreement | Tree-sitter-based map is a candidate, with `rg` fallback |
| Structured/schema-constrained handoffs | Strong agreement | Ollama schema output + Pydantic validation; test separately from tool calls |
| Defer search, docs lifecycle, managers, dashboard | Agreement | Add when task evidence demonstrates a need |
| Defer persistence until later stages | **Partial disagreement** | Minimal intent/outcome journal **from first real mutation** |

Claude's concern about context and multiple agents is particularly persuasive: **context isolation is a mechanism; multiple named agents are only one implementation of it**. A single process can run phases using fresh model sessions and different tool permissions. The effect must be measured before introducing extra orchestration.

### Two reservations about Claude's recommendations

**Retain Agent Framework as an experiment rather than discarding it upfront.** It may provide useful model/MCP integration and session-management primitives, but we should not take on its workflow abstractions unless they reduce implementation burden or improve reliability. Keep the internal interface small enough to compare implementations without creating a large framework-of-frameworks.

**Journal side effects from the first working mutation.** Full crash-resume orchestration can wait. But even the first coding prototype must record which repository revision was inspected, what edit was attempted, and its observed outcome. Framework checkpoints cannot atomically roll back filesystem or Git side effects.

---

## 4. Revised architecture

### 4.1 v0 topology

```text
                         USER
                          |
                     Minimal TUI
                          |
                Deterministic coordinator
                    (Python asyncio)
                          |
            +-------------+-------------+
            |                           |
     Task state and journal      Context/tool-budget manager
     SQLite + evidence files       Fresh per-phase sessions
            |                           |
            +-------------+-------------+
                          |
                    CODING LOOP
                          |
      Orient -> Reproduce/Plan -> Implement
                          |
              Deterministic verification
                          |
               Pass? --No--> Repair / Replan
                 |
                Yes
                 |
        Optional read-only diff review
                 |
          Human approval / completion
                          |
          +---------------+---------------+
          |               |               |
   Model client      Tool gateway    Sandbox runner
   local/remote       Serena MCP      build / test
   Ollama              rg, repo map   isolated process
                       git, diff
                          |
                  Isolated worktree
```

**Control-plane principle:** the coordinator owns task state, phase transitions, retry ceilings, evidence validation, permissions, and repository identity. The model suggests actions and code; deterministic code enforces policy and judges actual command results.

### 4.2 Why one loop instead of four agents?

The four conceptual responsibilities remain useful, but need not initially map to four enduring agent objects:

| Original role | v0 equivalent | Can be split into a separate agent later? |
|---|---|---|
| Researcher | Orient phase | Yes, if focused retrieval measurably helps |
| Architect | Reproduce/Plan phase | Yes, if independent planning improves results |
| Developer | Implement + Repair phases | Yes, if model/tool specialization helps |
| Reviewer | Deterministic gates + optional independent LLM review | Yes, ideally with measured value or a different model |
| Coordinator | Deterministic Python controller | Remains non-LLM |

Every phase has a **fresh, bounded model context**, its own permitted tools, and structured output. The system does **not** relay full preceding conversations into subsequent phases.

### 4.3 Phase flow

**Phase A — Orient.** Capture Git base revision, branch/detached state, clean/dirty status, repository map, language/toolchain profile, relevant files/symbols, and known constraints. Use `rg` and Serena read-only tools. Output: short source-anchored evidence artifact.

**Phase B — Reproduce / Plan.** Run an initial baseline test where feasible to distinguish pre-existing failures. For bug fixes, locate or create an appropriate failing regression test before altering production behavior, whenever practical. Produce an ordered, bounded subtask plan with specific acceptance checks.

**Phase C — Implement.** Apply one subtask using a measured edit strategy and explicit file/symbol scope. Keep actual diffs as authoritative evidence. If the model needs new information, request targeted retrieval rather than stuffing whole files into its context.

**Phase D — Verify.** Deterministic coordinator executes relevant format, lint, compile, and test checks and captures exit codes plus bounded diagnostic excerpts. This phase does **not** need an LLM call to decide pass/fail.

**Phase E — Repair / Replan.** Provide only the most relevant failures, current diff, and acceptance criteria in a fresh context. Apply bounded attempts (three is an initial candidate), detect repeated identical failure signatures, and re-plan or stop on lack of progress.

**Phase F — Review (initially optional).** Once deterministic checks pass, optionally review the *actual* diff against the original requirements with a read-only fresh-context model pass. This is advisory; tests and static checks remain separate gates. An alternative-model review can be evaluated later.

**Phase G — Approval / Completion.** Show modified files, actual diff, verification statuses, residual uncertainty, and any user action required. Do not equate a passing local test with CI, hardware validation, or human acceptance.

### 4.4 Example compact handoff (illustrative, not normative schema)

```json
{
  "task_id": "task-0042",
  "base_revision": "<actual-git-sha>",
  "goal": "Fix queue transition regression",
  "source_refs": [
    {"path": "src/audio/queue.rs", "symbol": "PlaybackQueue::next"}
  ],
  "acceptance_checks": ["queue transition regression test"],
  "known_baseline_failures": [],
  "uncertainties": ["Possible hardware-only race remains unverified"]
}
```

The coordinator should validate artifacts using **Pydantic/JSON Schema**, reject malformed or ungrounded records, and keep references to raw logs/source evidence outside the model's context. Schema-constrained output and true tool-call correctness must be benchmarked **separately**.

---

## 5. Model, context and prompt engineering

### 5.1 Inference design

- Primary test model: **Qwen3.5-9B** through Ollama (exact tag, quantization, runtime build and model hash to be recorded).
- Accept local or remote Ollama endpoints; the inference backend must not be bound to the workstation running the TUI.
- No fixed assumption that requested context equals allocated context. Record `ollama ps`, configured `num_ctx`, CPU/GPU offload, VRAM, throughput, and timeouts.
- Start benchmark contexts at **16K, 32K and 64K**, then test **128K** if the hardware/runtime results support it.
- Keep inference concurrency at **one active request per endpoint** as an initial conservative policy; relax only after measurement.
- Treat Qwen3.5-27B and other local models as optional comparison candidates. A higher-parameter model at aggressive quantization might lose to a 9B model with better tooling/context.

### 5.2 Context budgeting

Each invocation needs a bounded allocation for:

1. Stable role/policy instructions.
2. Tool schemas (measured token count, not a vague estimate).
3. Source evidence and retrieved documentation.
4. Recent tool observations.
5. Output and optional thinking/reasoning tokens.

Keep stable instructions at the front of prompts to improve prefix-cache reuse where supported. Place per-task changing evidence later. Do not assume that every fresh context benefits equally from Ollama prefix/KV caching; measure prompt prefill cost and cache behavior.

Limit each phase to the smallest viable set of model-visible tools (initial candidate **4–8**, plus control-plane-only tools that never enter the model prompt). A maximum must be justified by actual tool-selection and schema-token experiments, not treated as a universal constant.

### 5.3 Reasoning mode

Benchmark thinking **on vs off per phase**. The output-token budget includes thinking where the server/model emits such tokens; do not spend context on verbose reasoning where a deterministic tool is better. In particular, the verify phase should not spend model tokens merely interpreting process exit codes.

### 5.4 Effective working memory

A project can exceed any single model window because most information stays in files, source indexes, a repository map, and task evidence. The model retrieves only what the current phase needs. Fresh contexts **do not** increase Qwen's native context limit or make the model intrinsically more knowledgeable.

A summary is never the authoritative version of code. The file tree, source revision, diff, and actual test output are.

---

## 6. Editing and retrieval strategy

### 6.1 Repository understanding

Use complementary retrieval techniques:

- `ripgrep` for precise textual search and errors.
- A lightweight **repo map** (tree-sitter-based if supported; otherwise a simple file/symbol index) for language-agnostic structural hints.
- **Serena MCP** for semantic symbol lookup, references, and possibly symbol-level changes.
- Direct, bounded file reads when necessary.

All retrieved findings should include file/symbol references and the Git revision they describe. Recheck stale observations after edits or external source changes.

### 6.2 Code-editing benchmark

Select the v0 editing primitive using evidence from **the actual model**, rather than architectural intuition.

| Candidate | Evaluate | Known risk |
|---|---|---|
| Serena symbol-based edits | Correct symbol selection; correct modified AST/text; language coverage | LSP limitations; incorrect symbol targeting |
| Exact search/replace blocks | Unique match rate; handling nearby changes; repairability | Ambiguous or stale search spans |
| Unified diff patch | Parse/apply success; multi-file robustness; error recovery | Malformed hunks and context conflicts |

Metrics must distinguish **valid proposed edit**, **successful application**, **correct target**, **compilation/test success**, and **task success**. Never accept an ambiguous or partially applied patch without inspecting the resulting worktree.

### 6.3 Tool gateway

Expose a small, typed API such as:

```text
search_text(query, glob)
repo_map(scope)
read_symbol(symbol_id)
find_references(symbol_id)
apply_edit(edit_request)
get_diff(paths)
run_named_check(check_id)
```

These are **conceptual application tools**, not promises about current Serena tool names. The gateway maps them to installed tools, checks path permissions, limits responses, and records side effects. It enforces read-only versus edit capabilities in code rather than trusting role instructions.

The coordinator handles Git operations and test commands through a narrow Python wrapper. Do not give the model an unrestricted shell by default.

---

## 7. MCP and documentation/search strategy

### 7.1 Essential or early evaluation

| Component | Role | Position |
|---|---|---|
| **Serena MCP** | Symbol navigation and controlled editing | **Stage 0/v0 evaluation** |
| Native `rg`, `git`, test tools | Repository text, diff, and verification | **Required** |
| Repo map | Compact repository structure | **Stage 0 candidate** |

### 7.2 Deferred until demand is demonstrated

| Component | Purpose | Condition for introduction |
|---|---|---|
| **Grounded Docs / docs-mcp-server** | Local or self-hosted documentation search | Add a small indexed corpus when benchmark tasks actually need docs |
| **SearXNG + MCP adapter** | Self-hosted public-web search | Add when diagnosing external issues measurably needs web search |
| **Fetch MCP** | Fetch selected external documentation pages | Add alongside documented external source retrieval needs |
| Local embeddings or vector index | Semantic documentation/project-memory retrieval | Add only if full-text+symbols is insufficient |
| Playwright/Android-specialist integrations | UI/device testing | Add for projects where deterministic tests require them |

Serena and optional doc/search services must remain **free to operate without paid commercial APIs**. The application should avoid sending private repository contents to external search engines by default. Self-hosted metasearch still makes outbound network requests and may experience engine rate limits.

### 7.3 MCP state isolation

For actual mutating worktrees, instantiate Serena **against the active task worktree**, not the original repository checkout. If two worktrees are active, they must not share a mutable Serena project root or silently switch one server's project. Serena version/tool inventory and actual license must be pinned and checked before implementation.

Only a carefully filtered, project-specific tool subset should be available to the model at any phase. The MCP client should supervise subprocess lifecycle, enforce timeouts, and constrain output size. A working MCP connection alone is not evidence that Qwen calls its tools correctly.

---

## 8. Repository isolation, Git and CI

### 8.1 Default worktree strategy

**Default for autonomous mutation:** one **local isolated Git worktree per task** (detached HEAD or otherwise locally isolated as the project policy permits), plus an OS file lock for that worktree. This does **not** imply opening a remote PR or branch for every subtask.

**Supervised alternative:** direct edits in a user's current working tree, requiring explicit protections for dirty files and user changes.

Record at task start:

- Canonical repository and worktree paths.
- Base commit SHA and relevant file hashes.
- Current Git status, including existing user modifications.
- Task identity and tool permission profile.

Revalidate the expected source before each write. On ambiguous errors/timeouts, inspect actual files and Git state instead of blindly retrying.

### 8.2 Serena per active worktree

```
main checkout (human workspace)
      |
      +-- task worktree A -> Serena A -> task A changes
      |
      +-- task worktree B -> Serena B -> task B changes
```

This isolates source edits and symbol analysis while letting independent tasks run on separate worktrees. It does not eliminate shared system resource limits or the complexity of reconciling completed changes.

### 8.3 Local Git vs GitHub CLI

Use `git` locally to inspect and edit worktrees, produce diffs and commits subject to configured approvals. Use **`gh`** for optional authenticated GitHub remote operations: workflow dispatch, exact-head CI result inspection, issues, PRs, and pushes when authorized.

No Ralph Bridge dependency. No mandatory branch/PR workflow. Project-specific policy determines whether and when changes are committed, integrated, pushed, or subjected to remote CI.

v0 should focus on local coding and verification. GitHub Actions dispatch through `gh` can be added after the core loop works; when added, CI evidence must match the **exact commit SHA**, not merely a passing branch run.

---

## 9. Side effects, persistence and recovery

### 9.1 Keep storage minimal

For the first mutation-capable version, use **one project-scoped SQLite database** and files for larger artifacts:

- Task and phase status.
- Task input and source revision.
- Tool invocation **intent**, expected state, and observed result.
- Diff or edit artifact references.
- Test/build evidence references, exit codes, and failure signatures.
- Approval/outcome records.

Avoid a large schema of agent identities, architectural memories, knowledge graphs, resource leases, and embeddings before they are necessary.

### 9.2 Minimal side-effect journal

For every potentially mutating operation:

```text
1. Record operation intent (task ID, target paths, expected hashes/revision).
2. Execute guarded operation.
3. Observe actual result (files, hashes, Git status, process exit, etc.).
4. Record reconciled outcome and evidence reference.
```

A crash between steps 2 and 4 requires **reconciliation**, not automatic replay. Framework checkpoints are not transactions covering filesystem, Git, and external processes.

### 9.3 Resumption and concurrency

One process per project is the intended normal mode. Task worktrees and OS locks manage mutating ownership. An interrupted process must revalidate its worktree and journal before continuing. An advanced lease/heartbeat protocol and multi-project management daemon are **deferred** until actual concurrency demands them.

Evidence files may retain full logs; prompts receive only bounded relevant extracts. Source references and tested Git revisions are preferable to unverified persistent LLM-generated architecture summaries.

---

## 10. Security and execution isolation

**Unattended code execution is unsafe without a validated confinement mechanism.** Even an allowlisted `cargo test`, `pytest`, `npm test`, or build command may run arbitrary repository-supplied code.

### 10.1 Default security stance

- Code reading and text search can occur in a project-scoped supervised process.
- Source writes are confined to the configured task worktree and checked against expected revision/hash.
- **Unattended builds/tests require an OS sandbox** (e.g., bubblewrap or another validated isolation mechanism), otherwise the application must fail closed or request supervised execution.
- Sandbox filesystem mounts should be restrictive; home SSH keys, GitHub credentials, other projects, and host secrets must not be visible to untrusted build/test code.
- The model-provider connection stays in the coordinator outside the test sandbox; network from tests should be disabled unless explicitly required and approved.
- Remote search/documentation responses are **untrusted input**, not instructions. Guard URL resolution, redirects, SSRF, oversized content, and prompt injection.
- Tool authorization must be enforced by code, not by natural-language prompts.
- Never put authentication tokens into model prompts or logs.

### 10.2 Ubuntu/bubblewrap caveat

On Ubuntu, unprivileged user namespace and AppArmor settings can affect bubblewrap feasibility. A Stage 0 security probe must test whether the target host can launch and enforce the required sandbox policy. Do **not** attempt to silently bypass host security restrictions. If no safe backend is available, keep execution supervised until one is configured.

Native worktrees provide workflow isolation, **not security isolation**. Separate Python virtual environments are also **not** security boundaries.

---

## 11. Multi-project / multi-Ollama design

Concurrent projects do not need containers:

```text
                   One Ubuntu workstation
                      /             \
              AI Coder A           AI Coder B
                 |                     |
          Repo/worktree A       Repo/worktree B
          Serena A              Serena B
          SQLite A              SQLite B
                 |                     |
          Ollama host A         Ollama host B
          (remote/local)        (remote/local)
```

Each native TUI process has its **own project root, task state, permissions, worktrees, MCP sessions, and model routing configuration**. `git`, `gh`, Python packages, and possibly public documentation indexes may be shared as installed infrastructure, not as mutable task state.

**Example project configuration (illustrative, not final schema):**

```yaml
project:
  root: /home/user/projects/project-a

model:
  provider: ollama
  host: http://127.0.0.1:11435  # SSH tunnel to remote Ollama A
  name: qwen3.5:9b
  requested_context: 65536

execution:
  max_parallel_model_calls: 1
  mutation_mode: isolated_worktree
  unattended_tests: sandbox_required

mcp:
  serena:
    enabled: true
    scope: active_worktree
```

A second project can instead use `http://127.0.0.1:11436` over a separate tunnel to remote Ollama B, with a different model. Do not expose Ollama's unauthenticated API directly to the public internet; use loopback/SSH tunnel or an appropriately secured private network.

We should design the configuration/store boundary for multiple projects **now** but defer a global multi-project dashboard, endpoint-level scheduling daemon, and dynamic model pool manager until measured demand exists.

---

## 12. Stage 0: feasibility and architecture-selection gate

### 12.1 Key question

> Can a specific Qwen3.5-9B + Ollama configuration reliably navigate, modify, and verify real repository tasks with a small context-aware harness—and does it outperform a fairly configured OpenCode baseline enough to warrant custom infrastructure?

Stage 0 is **experimental engineering**, not the beginning of feature-complete product development. Pre-register the task set, metrics, and success criteria before evaluating candidates.

### 12.2 Controlled test conditions

Use the same model tag/quantization, actual allocated context, repositories, task instructions, tool access, and machine/server conditions wherever possible. Capture `ollama ps`, inference host profile, input/output tokens, cache/prefill behavior if observable, wall-clock time, and test outcomes. Keep benchmark tasks hidden from prompt examples and iterative tuning when feasible.

A representative test suite should contain **~20–30 tasks**, spanning Python, Rust and (if toolchains are available) Kotlin/Android, with examples of bug fixes, targeted refactors, multi-file changes, and unexpected test failures. Use held-out acceptance tests or independent oracles when available; never score mere compilability as task completion.

Record model and tool calls separately. Tool schema validity, correct tool selection, correct edit application, and end-to-end task success are different quantities.

### 12.3 Experiments and metrics

| Experiment | Comparisons | Primary measurement |
|---|---|---|
| Ollama context | 16K, 32K, 64K; optionally 128K | Actual context, VRAM, offload, prompt speed, task success |
| Tool inventory | 4 vs 8 vs 20 model-visible tool schemas | Schema tokens, valid calls, correct tool selection |
| Editing format | Serena symbol edit vs exact search/replace vs unified diff | Valid edits, successful application, correct target, test pass |
| Thinking configuration | Enabled vs disabled for phases | Quality, output budget, latency |
| Retrieval | `rg` only vs repo map vs Serena | Relevant-symbol recall, tokens per useful finding, task success |
| Context management | Continuous session vs fresh phase contexts | Task pass rate, truncation, prefill latency, recovery |
| Orchestration backend | Direct Ollama/MCP/`asyncio` vs minimal Agent Framework adapter | Tool reliability, code complexity, latency, maintainability |
| Repair loop | One-shot vs bounded repair | Verified recovery rate, regression count, wasted retries |
| Remote inference | Local endpoint vs configured remote Ollama host | Timeout/transport recovery and isolation correctness |
| OpenCode baseline | OpenCode with correctly sized `num_ctx`, repo guidance, equivalent tools | End-to-end independently verified task outcomes |

**Example provisional engineering targets** (must be agreed *before* scored experiments and revised based on task criticality):

- >=95% **syntactically/schema-valid** tool calls on a fixed tool-call suite; track semantically correct tool choice separately.
- >=95% successfully parsed/applied edits on a fixed edit-format suite; require correct target and actual task correctness as additional gates.
- No silent overwriting of user changes, cross-project file access, or falsely reported test success in the controlled safety suite.
- Clear measured advantage over the optimized OpenCode baseline **or** compelling simplification/reliability advantages before investing in a custom full product.

These values are **proposed benchmark criteria**, not established performance or a claim that 95% is sufficient for long autonomous tasks. Aggregate task-completion rates should be reported with per-task outcomes and variability across repeated runs where feasible.

### 12.4 Go/no-go logic

- **Go to v0:** tools and edits are sufficiently reliable, test evidence is attributable, and there is a credible path to surpassing baseline end-to-end performance.
- **Fix the fundamentals:** if tool selection or edit application is fragile, focus on model, decoding/schema, edit primitive, prompt and retrieval changes **before** adding agents.
- **Reassess the product:** if corrected OpenCode already solves the target tasks just as well with lower complexity, do not build a larger custom framework merely for its own sake.

A failure of one model quantization is not automatically a failure of the architecture; record the limitation and consider an alternative model/quantization under the same evaluation protocol.

---

## 13. Proposed incremental evolution (not an implementation TODO)

These are conceptual **decision gates**, not a prescriptive engineering task checklist.

| Stage | Scope | Evidence required to proceed |
|---|---|---|
| **0 — Feasibility** | Model/tool/edit/context experiments + corrected OpenCode baseline | Tool reliability, edit reliability, candidate architecture value |
| **v0 — Vertical slice** | Minimal TUI, one phased loop, Serena, guarded edits, sandboxed tests, SQLite journal | At least one nontrivial real task completed and recoverable |
| **v1 — Reliability** | Stronger repair, resumption, regression suite, multi-repo policy hardening | Repeated passes, honest recovery, no cross-project contamination |
| **v2 — Optional specialists** | Separate planner/researcher/reviewer agents or alternate models | Measured end-to-end improvement vs single phased loop |
| **v3 — Optional ecosystem** | Grounded Docs, SearXNG/Fetch, `gh` CI, richer project controls | Each integration justified by evaluated task demand |

**Note:** Basic project-specific endpoint configuration and storage isolation are v0 architectural boundaries, even if the global dashboard and scheduling features arrive much later.

---

## 14. Decision log: fixed, adopted, and unresolved

### 14.1 Fixed by user preference

| Topic | Decision |
|---|---|
| Interface | TUI, not VS Code |
| Model execution | Local and remote Ollama allowed |
| Multiple projects | Separate native processes on one computer; separate state |
| Paid dependencies | No required paid model/search/docs APIs |
| GitHub | `git` + `gh`, not Ralph Bridge |
| Containers | Docker/Podman not required |
| Code intelligence | Serena MCP desired |
| Performance tradeoff | More inference time acceptable if task success improves |

### 14.2 Adopted for the next experiment

- Deterministic Python coordinator.
- Single **phase-oriented loop** as v0 baseline.
- Bounded fresh contexts and explicit token/schema budgets.
- Schema-validated artifacts and actual revision/source references.
- Reproduce-first where possible; baseline test evidence before mutation.
- Compare edit formats, retrieval approaches, thinking settings, and framework adapter choices.
- Isolated local worktrees by default; no mandatory remote PR/branch per task.
- Serena scoped to the **active worktree**.
- Minimal SQLite event/side-effect journal from the first mutation.
- Sandboxed unattended build/test execution, with fail-closed fallback.
- External services, complex memory, and many-agent orchestration deferred until justified.

### 14.3 Still open / requires validation

1. Does the model reliably call tools and apply edits under a practical context budget?
2. Which editing primitive wins on Rust, Python, and Kotlin/TypeScript tasks?
3. What actual Ollama context/offload/latency is feasible on the target 16 GB GPU?
4. Does thinking improve tool use and coding by phase, net of output-budget cost?
5. Is Serena's current tool inventory usable with a sharply limited schema budget?
6. How much does a repo map improve retrieval beyond `rg` and Serena?
7. Does Agent Framework simplify model/MCP orchestration compared with plain `asyncio`?
8. How should phase prompts be structured for efficient cache reuse?
9. What explicit acceptance thresholds constitute Stage 0 success?
10. Can bubblewrap (or an equivalent sandbox) enforce the required policy on target Ubuntu installations?
11. What is the simplest safe worktree integration/merge policy for user edits?
12. What is the correct format and granularity for a minimal crash-reconcilable journal?
13. Which initial TUI library produces enough observability without distracting from inference experiments?
14. When do Grounded Docs and self-hosted search demonstrably improve outcomes?
15. Which concrete Serena/MAF/Ollama releases and license files will be pinned?
16. How will multiple independent remote Ollama server instances be tested for endpoint and state isolation?
17. Are independent LLM reviews beneficial when performed by the same small model, or only with a different model?
18. Which user approvals are necessary for edit, local commit, integration, push, CI dispatch, and potentially destructive operations?

---

## 15. Key risks and mitigations

| Risk | Consequence | Initial mitigation |
|---|---|---|
| Small-model tool misuse | Bad search/edit calls, stuck sessions | Tiny typed tool set, schema checks, benchmark, bounded retries |
| Context overflow | Loss of essential task state | Fresh phases, source-backed artifacts, token reserve, bounded outputs |
| False confidence from self-review | Undetected defects | Deterministic tests, independent test suite, optional fresh diff review |
| Stale project notes | Incorrect edits | Revision-aware source refs; avoid broad auto-generated memory |
| Ambiguous edit timeout | Duplicate or corrupt patches | Intent/outcome journal plus actual-file reconciliation |
| Unsafe build/test execution | Host compromise or data leakage | OS sandbox for unattended execution; no secrets in sandbox |
| User-worktree conflict | Lost or mixed modifications | Isolated task worktrees, hashes, locks, explicit integration |
| Wrong Serena root | Cross-task or cross-project edits | One instance per active worktree, root validation |
| Prompt cache loss | Excessive prefill latency | Stable prefixes, measure cache behavior, sequential execution |
| Remote Ollama failure | Interrupted reasoning, ambiguous state | Timeouts, retries for *read-only inference*, task recovery from journal |
| Hosted-service creep | Cost/privacy violations | Local-first defaults; optional outbound network only |
| Framework API churn | Compatibility and maintenance burden | Small adapter, version pins, integration contract tests |
| GPL/AGPL licensing misunderstandings | Distribution obligations | Treat local use and redistribution separately; verify exact licenses |
| Overengineering before proof | Wasted implementation work | Stage 0 gates and minimal vertical slice |

---

## 16. Questions for Claude's second review

Please challenge these claims rather than treating them as settled:

1. **Single phased loop:** Is it a sound v0 replacement for separate agents using the same 9B model? What would justify splitting into specialists?
2. **Editing primitive:** Which edit representation should be tested first, and is the proposed benchmark sufficient to select it objectively?
3. **Framework choice:** Is a minimal Microsoft Agent Framework adapter worth building at Stage 0? Is there a smaller comparison that would answer the same question?
4. **Context and caching:** How should role prompts, evidence and tool definitions be ordered to minimize prefill and context waste on Ollama?
5. **Tool inventory:** What is the correct minimal set of model-visible tools for a 9B agent, and which actions should remain coordinator-only?
6. **Repo mapping:** Is tree-sitter/aider-style mapping worth the effort in v0, or do Serena + `rg` suffice?
7. **Security:** Can bubblewrap provide meaningful unattended test/build isolation on a stock Ubuntu installation? What validation probes and fail-closed rules are necessary?
8. **Git worktrees:** Is one isolated worktree per task a good default for local workflows? How should patches be integrated without stepping on human edits?
9. **Persistence:** Is the minimal intent/outcome journal too much for v0, or the minimum necessary for safe mutations?
10. **Benchmarking:** Are the example success criteria useful? What additional metrics or controls are needed to avoid an unfair OpenCode comparison?
11. **Multi-project:** Are per-process project state and per-worktree Serena instances enough to prevent accidental cross-project actions without Docker?
12. **Roadmap:** What should be *removed* from v0, not merely deferred, to test the hypothesis faster and more accurately?

**Requested review output:**

- Separate **blocking architecture issues**, **important improvements**, and **optional future features**.
- Provide concrete, testable changes to the proposed Stage 0 protocol and v0 design.
- Point out mistakes or unsupported assumptions with primary-source references where possible.
- Distinguish design risks from implementation details that belong in the future spec.
- **Do not create the formal specification or TODO yet.**

### Suggested prompt to send Claude

> Please perform a second critical review of the attached `Local AI Coder — Revised Architecture and Response to Claude's Review`. It is a design proposal, not a spec or task checklist. Focus on whether Stage 0 is rigorous enough to establish that a small Qwen/Ollama coding model can reliably navigate, edit and verify real repositories; whether a one-loop fresh-context architecture is preferable to distinct same-model agents; whether Microsoft Agent Framework adds demonstrable value; and whether worktree isolation, Serena scoping, sandboxing, and minimal journaling are sufficient. Identify incorrect assumptions and unnecessary complexity. Recommend precise revisions and acceptance criteria, but **do not write SPEC.md or TODO.md**. Please verify version-specific technology assertions you rely upon, and distinguish verified facts from informed predictions.

---

## 17. References and evidence provenance

**Design inputs:**

- Original architecture draft: `LOCAL_AI_CODER_ARCHITECTURE_DESIGN_REVIEW_2026-10-19.md` (v0.1).
- Claude's response: `CLAUDE_REVIEW_AND_V0_OUTLINE_2026-10-19.md` (architecture critique and minimal v0).
- Subsequent discussion: analysis of Claude's review, including the decision to begin with a phase-oriented baseline and a Stage 0 benchmark.

**Primary documentation to check during Stage 0 (not independently re-verified for this revision):**

- Microsoft Agent Framework: <https://github.com/microsoft/agent-framework>
- Agent Framework / Ollama: <https://learn.microsoft.com/en-us/agent-framework/agents/providers/ollama>
- Agent Framework context propagation: <https://learn.microsoft.com/en-us/agent-framework/concepts/workflows/advanced/agent-executor>
- Agent Framework MCP: <https://learn.microsoft.com/en-us/agent-framework/agents/tools/local-mcp-tools>
- Ollama structured outputs: <https://docs.ollama.com/capabilities/structured-outputs>
- Ollama context: <https://docs.ollama.com/context-length>
- Ollama FAQ / runtime settings: <https://docs.ollama.com/faq>
- Serena MCP and current licenses: <https://github.com/oraios/serena>
- Grounded Docs: <https://github.com/arabold/docs-mcp-server>
- SearXNG: <https://github.com/searxng/searxng>
- Fetch MCP: <https://github.com/modelcontextprotocol/servers/tree/main/src/fetch>
- GitHub CLI: <https://cli.github.com/manual/>
- bubblewrap: <https://github.com/containers/bubblewrap>
- Ubuntu unprivileged user namespaces: <https://documentation.ubuntu.com/security/security-features/privilege-restriction/>

**Qualification notice:** Vendor/API documentation and repository license files can change. Stage 0 must record exact package/model/runtime versions and test actual behavior. The design does not warrant any particular memory footprint, benchmark win, tool-call reliability, safety property, or feature availability until measured.

---

**End of revision 0.2 — awaiting Claude's second review. No `SPEC.md` or `TODO.md` created.**
