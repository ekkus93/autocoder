# Handoff: Qwen3.5 coding experiments, 2026-10-21

## Session context and stopping point

These Autocoder experiments were requested and completed from the Kaggle conversation
by mistake. The user noticed the session mix-up and requested this handoff so work
can resume in the Autocoder session. The experiments themselves ran in
`/home/phil/work/autocoder`. All runs are finished; no experiment process remains
running. No further Autocoder work is pending in the Kaggle session.

The user asked whether the earlier Qwen coding tests used thinking, requested a
thinking/non-thinking comparison, then requested the same comparison on the installed
128k and 256k variants. No production default was changed and no candidate fix was
merged. Suggested next steps below are proposals, not completed work or instructions
to automatically change defaults.

## What we did and found

### 1. Checked the earlier tests

Earlier tests used `qwen3.5:9b` with thinking **off**: `infer` defaults to
`think=False`, and `ModelBackend` does not override it. Native Ollama requests
explicitly send that value. The harness explicitly requested **32,768 context tokens**,
so those runs did not use a 4k context default. The 768/1,024/1,536-token phase limits
were output limits, separate from context capacity.

### 2. Repeated the five-task suite with thinking off/on

Tasks: pagination, decimal calculator/operator precedence, interval merging,
report median/maximum, and the three-file shop package. Fresh isolated worktrees
started from the same original fixture revisions.

| `qwen3.5:9b`, 32k context | Passed | Total seconds | Output tokens |
| --- | ---: | ---: | ---: |
| Thinking off, original output limits | 3/5 | 90.1 | 5,830 |
| Thinking on, original output limits | 4/5 | 191.2 | 14,559 |

Thinking solved the shop task that non-thinking failed. Thinking hit the 1,024-token
orientation cap on the calculator. We reran only that pair with 4,096 output tokens
per call and 16,384 total output tokens: thinking passed in 247.2 seconds using
14,403 output tokens; non-thinking stopped without progress after 32.6 seconds.
This targeted follow-up is not a five-task result under expanded limits.

Detailed evidence:
[QWEN_THINKING_COMPARISON_2026-10-21.md](evidence/QWEN_THINKING_COMPARISON_2026-10-21.md).

### 3. Tested the installed 128k and 256k variants

Used `qwen35-128k:latest` at **131,072** context tokens and
`qwen35-256k:latest` at **262,144**. For all four configurations, output limits were
4,096 tokens per call and 16,384 per task; other limits remained 600 seconds,
49,152 input tokens, 60 tool calls and three repairs. Temperature 0, seed 42,
local Ollama 0.40.6, one request/task at a time.

| Variant | Thinking | Passed | Total seconds | Output tokens |
| --- | --- | ---: | ---: | ---: |
| 128k | Off | 3/5 | 79.3 | 4,118 |
| 128k | On | **5/5** | 340.3 | 25,163 |
| 256k | Off | 2/5 | 194.9 | 5,380 |
| 256k | On | 3/5 | 439.2 | 14,701 |

| Task | 128k off | 128k on | 256k off | 256k on |
| --- | --- | --- | --- | --- |
| Pagination | ORIENT failure | Pass | ORIENT failure | Pass |
| Calculator | Pass | Pass | Input budget exhausted | Duplicate operation/no progress |
| Intervals | Pass | Pass | Pass | Pass |
| Report | Pass | Pass | Pass | Pass |
| Shop | ORIENT failure | Pass | ORIENT failure | ORIENT failure |

All **124** response snapshots confirmed the requested runtime context and pinned
model digest. All 70 thinking-mode responses contained thinking text; the 54
non-thinking responses contained none. No silent 4k fallback was observed.

Five of seven failures stopped before editing because the model cited lines outside
the source file, even after the decoding repair. The two remaining failures were the
256k calculator attempts: thinking fixed decimals but repeatedly missed the precedence
edit; non-thinking introduced a broken tokenizer capture-group pattern and ran out of
input budget during recovery. The `BUDGET_EXHAUSTED` status can also denote duplicate
operations/no progress, so read `detail` rather than treating every such status as
literal token exhaustion.

The 128k runtime reported 9.35 GiB, all in GPU memory. The 256k runtime reported
15.05 GiB total, with 12.47 GiB in GPU memory. Runtime placement and execution paths
differed, so the results do not establish that larger contexts impair reasoning.

Detailed evidence, full digests, timings and failure analysis:
[QWEN_CONTEXT_THINKING_COMPARISON_2026-10-21.md](evidence/QWEN_CONTEXT_THINKING_COMPARISON_2026-10-21.md).

## Important limits and implementation details

- These are informal experiments: one run per task/configuration, known regression
  scripts, no held-out oracle and no confidence intervals. A pass means the configured
  regression script passed. Candidate lint, remote CI and human acceptance were not run.
- The largest prompts in the context comparison were only 6,469 tokens (128k) and
  5,948 (256k). This tests coding behavior with those configured capacities, not
  long-context recall or capacity under a full window.
- Both custom tags share the same underlying model blob. The earlier `qwen3.5:9b`
  tag points to different blobs. Comparing the earlier generic tag with these custom
  tags does not isolate context size. Installed `qwen35-32k:latest` was discovered
  but was not tested in this session.
- Production `Project.context` currently allows at most 65,536. The comparison driver
  used a local subclass permitting 262,144, and a local `ModelBackend` subclass for
  expanded output allocation. Those subclasses reserve/check/journal the actual
  allowance; they do not silently override a smaller recorded allowance in transport.
- Production thinking remains off by default. Selecting a 128k tag alone does not
  make the existing harness use 128k: it explicitly sends its configured `num_ctx`.

## Files, artifacts and repository state

Repository HEAD during the experiments:
`114aa9891f0bdfa0753b89cc281f5bbeb1a5af15`, plus pre-existing uncommitted changes
that make the coordinator supply source hashes and base revisions.

These tracked files were already modified before these experiments and remain so:

```text
docs/V0.md
docs/evidence/SCRATCH_TASK_SUITE_MODEL_COMPARISON_2026-10-21.md
src/autocoder/v0/coordinator.py
src/autocoder/v0/schema.py
tests/test_v0.py
tests/test_v0_context.py
```

Do not reset those changes. Their captured tracked diff has SHA-256
`6594382c8d2a79a538da43f76677bb1916a4dbb7002e2eaa7dfc694742d13d6d`;
it was verified unchanged after the experiments. No commit was made here. This
handoff and the two Qwen evidence reports are new, uncommitted documentation.

Local ignored artifact directories, relative to the Autocoder root:

```text
tmp/thinking-comparison-2026-10-21/
tmp/thinking-comparison-2026-10-21-expanded/
tmp/qwen-context-comparison-2026-10-21/
```

They contain the runnable drivers (`run.py`), logs, manifests, captured harness patch,
results JSON, policy/request files, per-call metrics, candidate diffs and complete
task journals/worktrees under `state/`. The context comparison also saves model
definitions and per-response `/api/ps` snapshots. These artifacts are local, ignored
by Git, and must be preserved if needed for reproducibility. The drivers refuse to
overwrite results; copy a driver into a fresh sibling directory under `tmp/` to repeat.

Original fixtures remain clean at `tmp/tasks/{paginate,calc,intervals,report}` and
`tmp/testproj2` (shop). Earlier reports are under `docs/evidence/`; the four-task
fixture generator is `scripts/make_scratch_tasks.py`.

Validation performed: baseline failures, final statuses, budget/token totals,
context/model identity snapshots, identical fixture bases, source-only candidate
changes, clean original checkouts, unchanged tracked production diff and documentation
whitespace. Production unit tests were not rerun because these experiments did not
change production source. Prior reports mention a 107-test suite; that is historical,
not a fresh test result from this handoff.

## Suggested continuation in the Autocoder session

1. Read this handoff and both linked evidence reports; preserve the current working
   tree and ignored artifacts before changing the harness.
2. If continuing context comparisons, include `qwen35-32k:latest` with the same
   expanded output limits to compare three tags sharing the same underlying weights.
   Repeat on more tasks and separate true long-context tests from small coding tasks.
3. Investigate the remaining source-line citation failures without weakening source
   anchoring. Also distinguish no-progress stops from actual budget exhaustion in
   reporting. These were identified, not implemented in this session.
4. If adopting thinking or larger contexts, expose them as explicit production policy
   settings, preserve budget/context checks, and add appropriate tests. The 128k
   thinking configuration is the strongest candidate from this small sample, not an
   already-selected production default.
