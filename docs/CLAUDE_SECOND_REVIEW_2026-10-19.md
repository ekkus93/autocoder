# Claude Second Review: Local AI Coder Revised Architecture (v0.2)

**Date:** 2026-10-19
**Reviewed document:** `LOCAL_AI_CODER_REVISED_ARCHITECTURE_CLAUDE_REVIEW_2026-10-19.md` (revision 0.2)
**Status:** Review feedback only. Not a spec or TODO.

**Caveat.** Version-specific claims about Ollama, Qwen, Serena, bubblewrap and Agent Framework were not verified in this review. Where behavior is described below, it comes from prior knowledge and should be treated as a prediction to test in Stage 0.

---

## What improved

- **The architecture matches the evidence.** One deterministic loop with fresh-context phases is the right v0, and the role-to-phase mapping in section 4.2 is clear.
- **Stage 0 is a real gate.** It has pre-registered tasks, separated metrics (valid edit, applied edit, correct target, task success), a go/no-go rule, and an explicit "reassess the product if corrected OpenCode is enough" outcome. That last point is the most honest sentence in either document.
- **Security fails closed.** Unattended execution requires a validated sandbox, and the bubblewrap/AppArmor caveat is called out.
- **The journal pushback is fair.** Recording intent and outcome from the first mutation is cheap, and the reasoning is accepted.
- **The decision log separates fixed, adopted and open items.** This makes the document much easier to review.

## Concerns

1. **Stage 0 is too large to finish.** It has ten experiment families, 20-30 tasks, three languages and repeated runs.
   - It is effectively a research project. Without a time-box it will swallow the project.
   - With about 25 tasks the confidence intervals are wide. A 60% vs 70% difference is not distinguishable, so small-effect comparisons should not be planned.
2. **The 95% thresholds are framed per call, but failures compound.**
   - At 95% per call, a 20-call task has only about a 36% chance of zero invalid calls.
   - What matters is the rate of *unrecoverable* failures after retries. Measure first-try failures and recovered failures separately.
3. **Per-phase tool subsets conflict with prefix caching.**
   - In most chat templates the tool schemas are rendered at the top of the prompt. Changing the tool set between phases changes the prefix and loses the cache hit.
   - Benchmark a fixed 5-6 tool set across all phases, with permissions enforced in the gateway, against per-phase subsets.
   - Keep `num_ctx` constant across calls to an endpoint. As far as is known, changing it per request can force Ollama to reload the model.
4. **The inner loop of each phase is underspecified.**
   - Implement and Repair are multi-turn tool loops, and context grows inside them.
   - The document needs a step cap per phase, a policy for truncating or dropping old observations, and detection of tool-call loops. The cross-attempt repeat detection it has does not cover these.
5. **Task worktrees have costs the document does not mention.**
   - Each worktree means a cold Serena/LSP index (rust-analyzer especially) and a cold build cache (`target/`, `node_modules`, venvs).
   - A no-network sandbox also needs dependencies prepared first, for example `cargo fetch` or `uv sync` outside the sandbox. This is a real design step and it is missing.
   - Detached HEAD is risky because commits can be garbage-collected. Use a local branch such as `autocoder/task-N`. The integration policy (Q11) then becomes "the user merges that branch."
6. **Test tampering is not addressed.**
   - A model under pressure will edit or delete failing tests. Add a policy that flags diffs touching existing tests, test config or CI files.
   - Held-out oracle tests must be invisible to the worktree and the model, not just "hidden from prompts."
7. **Reproduce-first has a trap.** A 9B model writing its own regression test may write a vacuous one. Require that the test fails at the base revision and fails with the expected error signature before moving on.
8. **Benchmark contamination.** Popular public repositories are likely in Qwen's training data. Prefer your own repositories at older commits, or injected bugs, alongside any public set.
9. **The OpenCode baseline is necessary but not sufficient.** Also include **Aider** as a reference, since it has a built-in repo map and edit formats tuned for weak models, which covers two of the planned experiments. Give all baselines equal token and wall-clock budgets, and blind the scoring where possible.
10. **The Agent Framework comparison is too expensive as a benchmark arm.** A time-boxed spike answers it: can it do Ollama tool calls, MCP, and fully custom context handling without fighting defaults? If not, drop it.
11. **Tool calling may fail below the harness.** Ollama's Qwen tool-call parsing, its native vs OpenAI-compatible endpoints, and the chat template can each affect results. Test both endpoints, and consider llama.cpp's server as an alternative backend. This is a prediction, not a verified fact.
12. **The TUI should not be on the Stage 0/v0 critical path.** Make the coordinator headless and emit an event stream. A CLI runner is needed for benchmarking anyway, and the TUI becomes a client of the same events. This still satisfies the TUI requirement.

## Recommendations by severity

**Blocking (resolve before the spec)**
- Time-box Stage 0 and run it in tiers: cheap micro-benchmarks first (tool-call suite, edit-format suite, context/VRAM probe, sandbox probe), then the end-to-end comparison on a smaller task set.
- Define the in-phase loop: step caps, observation truncation, loop detection, per-task token budget.
- Add anti-tampering rules and hidden oracles.
- Add the dependency-preparation step for the sandbox, and specify the worktree lifecycle (local branch, cache sharing, Serena startup cost).

**Important**
- Reframe the tool-call thresholds as per-task unrecoverable-failure rates.
- Test fixed vs per-phase tool sets for cache behavior, and keep `num_ctx` stable.
- Add Aider as a baseline, and use uncontaminated tasks.
- Require that regression tests fail for the right reason at base.
- Run the Agent Framework decision as a spike, not a benchmark arm.
- Build the coordinator headless first.

**Optional**
- Kotlin/Android tasks (start with Python and Rust).
- Tree-sitter repo map, if the Aider baseline shows it matters.
- The alternate-model reviewer.

## Answers to the questions in section 16

1. **Single loop vs agents:** The loop is a sound v0. Split a specialist out only when a phase's context regularly overflows, or when a phase's measured failure rate stays high after prompt and tool fixes.
2. **Edit primitive:** Test search/replace first (simplest and most repairable), then Serena symbol edits, then unified diff. The benchmark is adequate if the same edit tasks are used across all three and the metrics are reported separately.
3. **Agent Framework:** No Stage 0 arm. Do the time-boxed spike described above.
4. **Prompt ordering:** Tools and stable instructions first, then the task prefix, then evidence, then recent observations. Keep the tool set and `num_ctx` constant.
5. **Minimal tools:** `search_text`, `read_symbol` or `read_file_range`, `find_references`, `apply_edit`, `run_named_check`. Make the repo map and diff coordinator-injected context rather than tools.
6. **Repo map:** Not in v0 unless the Aider baseline shows it helps. Serena plus `rg` is the first thing to measure.
7. **Bubblewrap:** Probe it early. If Ubuntu's userns/AppArmor restrictions block it, alternatives include Landlock or systemd-run user scopes. Otherwise stay supervised-only.
8. **Worktrees:** Yes, as local branches. Integration is a user-controlled merge.
9. **Journal:** The intent/outcome record is the right minimum, but since worktrees are disposable, an append-only JSONL event log plus the git base SHA may be enough for v0.
10. **Success criteria:** Add per-task unrecoverable-failure rates, repeated runs for variance, equal budgets, and a failure taxonomy.
11. **Multi-project:** Per-process state plus per-worktree Serena is enough. Add root validation in the gateway, and defer everything else.
12. **What to remove from v0:** The SQLite schema (use JSONL), the optional review phase, multi-project config machinery, and the TUI as a critical-path item.
