# Claude Review of the Local AI Coder Architecture Proposal, and a v0 Minimal Architecture Outline

**Date:** 2026-10-19
**Reviewed document:** `LOCAL_AI_CODER_ARCHITECTURE_DESIGN_REVIEW_2026-10-19.md`
**Status:** Review feedback plus a proposed v0 outline. Not an implementation spec or TODO.

**Caveat.** Version-specific claims in the reviewed document (Qwen3.5, Serena v2 licensing, Agent Framework `context_mode`, Grounded Docs behavior) were not independently verified in this review. Treat them as unconfirmed until Stage 0 validates them.

---

## Part 1: Review

### What is good

- **Context is treated as the scarce resource.** This is the right problem for a 9B-class model.
- **The coordinator is deterministic code, not an LLM.** Not asking a 9B model whether a failed test is a pass is the central sound idea.
- **Verification outranks model opinion.** Keeping test pass, review pass, CI pass and human acceptance as separate states is a good habit, and the outcome states in section 10.3 are honest.
- **Permissions are enforced in the tool gateway, not the prompt.** The document also covers SSRF, prompt injection from fetched content, and not sending source code to web search.
- **It is honest about limits.** It states that requested `num_ctx` is not actual `num_ctx`, that the multi-agent hypothesis is untested, and that a larger quantized model may lose. The staged rollout with a baseline comparison is right.
- **Side effects are journaled.** Recording intent and expected revision before an action, then reconciling after a crash, is the correct answer to "framework checkpoints are not transactional with the filesystem."

### Concerns

1. **Scope is far ahead of evidence.**
   - The design includes about 14 entity tables, a leasing and heartbeat protocol, MCP and model manager UIs, SearXNG, a Grounded Docs lifecycle and five memory tiers.
   - None of it matters if a 9B model cannot reliably call tools and produce edits.
   - The riskiest assumption sits in open question 4. It should be the Stage 0 go/no-go gate.
2. **The multi-agent premise is weaker than it reads.**
   - Four agents on one model are four prompts. The real benefit is fresh context per phase, which a single loop with context resets also provides.
   - A same-model Reviewer has correlated blind spots, and a 9B model reviewing a diff is a weak signal. Linters, static analysis and tests catch more.
   - Section 15 half-admits this, but the architecture and config still commit to four roles.
3. **Agent Framework as the backbone is questionable.**
   - The coordinator is hand-written deterministic Python, and a custom journal is needed anyway because framework checkpoints do not cover side effects.
   - That leaves the framework providing little, while adding API churn and defaults to fight (`context_mode="full"`).
   - If used, keep it behind a thin interface of our own.
4. **Tool-schema overhead is not budgeted.** Serena exposes many tools. Each schema costs tokens and degrades small-model tool selection. Count schema tokens explicitly and cap the tools per agent.
5. **The edit format is never discussed.** For small models this matters more than almost anything else in the design. Serena symbol edits, search/replace blocks and unified diffs have very different failure rates and should be measured early.
6. **Fresh context per invocation fights Ollama's prefix/KV caching.** Prompt processing at 9B speed adds real latency. Prompts should have a stable prefix, with variable evidence last.
7. **Security is optional where it should not be.** `cargo test`, `pytest` and `build.rs` execute arbitrary repository code, so a command allowlist contains little once tests run. For unattended operation, an OS sandbox (e.g. bubblewrap) should be a default, not a later investigation.
8. **Memory is over-designed.** LLM-written architecture notes go stale and mislead agents. Persist little beyond task state and human-curated conventions.

### Missing pieces

- **Reproduce-first.** For bug fixes, the first step should be a failing test, the strongest signal a small model can get. Run a baseline test pass before editing so pre-existing failures are not blamed on the patch.
- **Repo map.** An aider-style tree-sitter map is a cheap, language-agnostic retrieval layer that does not depend on Serena working.
- **Schema-constrained output.** Ollama supports a schema-constrained `format`. Use it for handoffs rather than hoping the model emits valid YAML.
- **Qwen thinking mode.** Thinking tokens consume the output budget. Decide per role whether to enable them.
- **Baseline pre-flight.** OpenCode's pain with small models may come largely from a too-small `num_ctx` or a weak edit tool. Fix and measure that before building anything.

### Recommendations by severity

**Blocking: resolve before writing a spec**
- Make a tool-calling and edit-format benchmark on the actual Qwen/Ollama combination the Stage 0 gate, with explicit pass thresholds.
- Decide whether Agent Framework earns its place. Current lean: plain asyncio plus a thin provider interface, with the framework optional.
- Make sandboxing a v1 requirement for any unattended mode.

**Important**
- Default to a **git worktree per task**. This removes most dirty-tree, lease and external-edit complexity and allows safe concurrency.
- Start with one agent loop using phase-based context resets (configuration B). Split roles only when the benchmark shows a gain.
- Cap tools per agent and count schema tokens in the context budget.
- Make review deterministic-first (lint, static analysis, tests), with the LLM review as a final pass, ideally on a different model.

**Optional**
- SearXNG, embeddings, multi-project status view, MCP and model manager screens.

### Answers to selected open questions (section 16)

| Q | Answer |
|---|---|
| Q1 Agent count | Start with one loop, then three roles. Split only if a role's context overflows or its eval scores plateau. |
| Q6 / Q14 Leases, GPU coordination | A lockfile per worktree, plus Ollama's own queue and a per-process semaphore. No daemon. |
| Q9 / Q10 Docs, SearXNG | Grounded Docs only. Defer SearXNG. |
| Q11 Serena scoping | One instance per project. Enforce read-only vs write in our gateway rather than with separate clients. |
| Q13 State | SQLite is the source of truth. Framework checkpoints are a convenience at most. |
| Q15 Licensing | Running Serena as a separate MCP process is the cleanest arrangement. Obtain legal advice before distributing anything. |

---

## Part 2: v0 minimal architecture outline

**Goal of v0:** answer one question cheaply: *can a 9B local model, given a good harness, complete real multi-file tasks reliably?* Everything else waits on that answer.

### Shape

```text
TUI (minimal) -> single coordinator loop (asyncio, deterministic)
                   |-- model client (Ollama, thin interface, schema-constrained output)
                   |-- tool gateway (typed tools, per-phase allowlist, bounded output)
                   |-- git worktree per task (lockfile)
                   |-- SQLite event log (append-only) + evidence files
```

One model, one loop. "Roles" are **phases** that each run in a fresh context with a stable prompt prefix and a curated, bounded evidence block.

### Phases (each a fresh context)

1. **Orient.** Build the repo map and gather the relevant symbols with `rg` and Serena (read-only). Output: a schema-validated evidence artifact.
2. **Reproduce / plan.** For bug fixes, write or locate a failing test. Run a baseline test pass to record pre-existing failures. Produce a short ordered plan.
3. **Implement.** One bounded subtask per context, using the single edit format chosen at Stage 0.
4. **Verify (deterministic).** Format, lint, compile and run targeted tests. The coordinator interprets the exit codes and diagnostics. No LLM is involved.
5. **Repair.** Bounded attempts with the first relevant diagnostic only. Detect repeated identical failures, then stop or re-plan.
6. **Review (optional in v0).** Deterministic checks first, then an LLM pass over the actual diff plus requirements. Defer until Stage 0/1 data justifies it.

### In v0

- Git worktree per task, captured base revision, and a lockfile.
- A small typed tool set: `read_symbol`, `find_references`, `search_text`, `apply_edit`, `run_named_test`, `get_diff`. Cap tools per phase and count schema tokens.
- Schema-constrained handoffs validated with Pydantic.
- A stable prompt prefix to benefit from KV caching.
- An append-only SQLite event log with an intent/outcome journal around file and git side effects. Raw logs go in evidence files.
- A sandbox (bubblewrap or equivalent) for any test or build execution beyond a supervised session.
- A minimal TUI: task prompt, current phase, tool calls, diff, approve/reject, stop.
- Explicit outcome states: tests pass / review pass / CI pass / human acceptance kept separate.

### Out of v0 (deferred until measured)

SearXNG and Fetch MCP, embeddings and vector retrieval, multi-project dashboard, MCP and model manager UIs, separate Researcher/Architect roles, five-tier memory, framework-level checkpointing, CI dispatch via `gh`, and a Grounded Docs lifecycle (add one docs source only if tasks need it).

### Stage 0: gate before building

Run on the actual Qwen/Ollama setup, with a fixed task set:

| Measurement | Why |
|---|---|
| Tool-call validity rate with N tools exposed (e.g. 4 vs 8 vs 20) | Sets the per-phase tool cap |
| Edit success rate: symbol edit vs search/replace vs unified diff | Picks the one edit format |
| Actual allocated `num_ctx`, speed and VRAM at 16K / 32K / 64K | Sets real context budgets |
| Thinking on vs off, per phase | Output-budget and quality tradeoff |
| Baseline: OpenCode with a corrected `num_ctx`, repo guidance file and equivalent tools | Determines how much the harness adds beyond fixing configuration |

**Go / no-go.** Set quantitative thresholds from these measurements before committing to the harness. If the tool-call or edit success rate is too low, fix that (model, format, constrained decoding) before building further.

### Staging after the gate

1. Single-loop vertical slice (above), end to end on one real task.
2. Compare against the corrected OpenCode baseline on the same tasks.
3. Add a role or phase split (e.g. separate planner, LLM reviewer) only if it measurably helps.
4. Add persistence and crash reconciliation, then multi-project and multi-host support.
5. Add optional integrations (search, docs, `gh` CI) as measured needs arise.

### Suggested questions for the next reviewer

- Is "one loop with fresh-context phases" a sound substitute for separate agents on a single 9B model?
- Which edit format is likely to be most robust for Qwen-class models, and how should it be tested?
- Is dropping Agent Framework as the backbone the right call, or is there a reason to keep it?
- What is missing from the Stage 0 measurement list?
- Is the v0 sandbox requirement realistic on a stock Ubuntu setup (unprivileged user namespaces, bubblewrap)?
