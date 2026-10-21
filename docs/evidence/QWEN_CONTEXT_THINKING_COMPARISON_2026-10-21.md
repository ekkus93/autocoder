# Qwen3.5 128k and 256k: thinking comparison (2026-10-21)

**Status:** Complete: 20 runs. Informal experiment, one run per task/configuration;
not a pre-registered benchmark or TODO milestone acceptance evidence.

## Context correction and model identities

The [earlier comparison](QWEN_THINKING_COMPARISON_2026-10-21.md) used
`qwen3.5:9b` with an explicit `num_ctx=32768`. It did not use a 4k default. Its
768/1,024/1,536-token limits were output limits, separate from context capacity.

This experiment uses the two installed custom tags at their configured capacities:

| Tag | Explicit context tokens | Model digest |
| --- | ---: | --- |
| `qwen35-128k:latest` | 131,072 | `a14034a9a68498756f82d5697930cebacde180e0521b48b415238bb10d6ee4ed` |
| `qwen35-256k:latest` | 262,144 | `b528609af3c0d8337a0fa6e27e6ffb54d3d25b23531abc37c38a5155fbcf2961` |

Both custom tags use the same underlying Q4_K_M model blob:
`dec52a44569a2a25341c4e4d3fee25846eed4f6f0b936278e3a3c900bb99d37c`.
Their saved definitions differ in the context parameter. They share the Qwen3.5
renderer/parser and the same sampling defaults. The earlier `qwen3.5:9b` tag points
to different model blobs, so changes from that earlier result cannot be attributed
solely to context size. The custom tags report 9.7B parameters; the earlier tag
reports 9.0B.

## Controls and procedure

- Same five fixtures, requests, editable-source policies and regression scripts as
  the earlier test: pagination, calculator, interval merging, report formatting,
  and the three-file shop project.
- Same harness HEAD `114aa9891f0bdfa0753b89cc281f5bbeb1a5af15` plus the existing
  uncommitted coordinator-supplied hash/base-revision changes. Captured tracked diff
  SHA-256: `6594382c8d2a79a538da43f76677bb1916a4dbb7002e2eaa7dfc694742d13d6d`.
- Local Ollama 0.40.6 at `http://127.0.0.1:11434`; native `/api/chat`; one request
  and one task at a time. Both tags loaded using the `llamacpp` runtime.
- Explicit `think=False` or `think=True`, `num_ctx=131072` or `262144`,
  temperature 0 and seed 42 on every inference request.
- Equal output limits for all four configurations: 4,096 tokens per call, subject
  to the remaining 16,384-token total output budget. Both reasoning and final output
  count toward this allowance. Other limits: 600 seconds, 49,152 input tokens,
  60 tool calls, three repairs.
- All 128k runs first, then all 256k runs, to avoid swapping models between tasks.
  Within each tag: paginate off/on, calculator on/off, intervals off/on, report
  on/off, shop off/on. One run per cell; no warmup; model-load durations saved.
- Fresh isolated task worktrees, anchored to the same fixture base commits for
  each pair. No candidate is merged into its original project.
- `/api/ps` captured after every successful inference response. The driver rejects
  any response if the loaded model does not report the requested context length.

Production `Project` policies currently cap context at 65,536. An experiment-local
subclass raises that field's ceiling to 262,144; another local subclass supplies the
larger output allocation before reservation, context checks and journaling. No
production source or production default was changed to run this experiment.

## Results

A pass means `VERIFIED_LOCAL`: the configured regression script passed. Elapsed
time includes the full harness run, including model loading and verification.
Output tokens include reasoning.

| Context | Mode | Passed | Total seconds | Input tokens | Output tokens | Truncated responses |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 128k | Thinking off | 3/5 | 79.3 | 55,868 | 4,118 | 0 |
| 128k | Thinking on | 5/5 | 340.3 | 111,254 | 25,163 | 1 |
| 256k | Thinking off | 2/5 | 194.9 | 63,585 | 5,380 | 0 |
| 256k | Thinking on | 3/5 | 439.2 | 63,311 | 14,701 | 0 |

Per-task outcomes and elapsed seconds:

| Task | 128k off | 128k on | 256k off | 256k on |
| --- | --- | --- | --- | --- |
| paginate | ORIENT fail, 23.2 s | Pass, 52.4 s | ORIENT fail, 21.2 s | Pass, 90.3 s |
| calc | Pass, 20.8 s | Pass, 173.0 s | Input budget, 99.1 s | No progress, 141.8 s |
| intervals | Pass, 10.9 s | Pass, 35.6 s | Pass, 24.8 s | Pass, 91.8 s |
| report | Pass, 20.3 s | Pass, 32.2 s | Pass, 39.7 s | Pass, 82.4 s |
| shop | ORIENT fail, 4.1 s | Pass, 47.1 s | ORIENT fail, 10.0 s | ORIENT fail, 32.8 s |

Runtime context matched the requested value for **all 124 recorded responses**.
All 70 thinking-mode responses contained thinking text; all 54 non-thinking responses
contained zero thinking characters. The largest individual prompts were 6,469 tokens
at 128k and 5,948 tokens at 256k, far below either configured capacity.

Loading time summed to 15.10 seconds for 128k/off, 0.06 for 128k/on, 6.63 for
256k/off, and 0.03 for 256k/on. Aggregate times include early failures and different
amounts of completed work, so their ratios are not equal-success speed comparisons.

### Failures and candidate review

- Five of the seven failed runs stopped in ORIENT before editing. Both non-thinking
  pagination runs cited lines 13–16 of a 12-line file. Both non-thinking shop runs
  still cited through line 8 of the seven-line `money.py` after their decoding repair.
  The 256k thinking shop run also cited lines 6–8 of that file in both attempts.
  These are source-line validation failures, not evidence of an attempted fix failing.
- The 256k thinking calculator run corrected decimal tokenization but could not apply
  the precedence edit. A repeated operation without source progress stopped it in
  IMPLEMENT, with status `BUDGET_EXHAUSTED`; it did not exhaust its token allowance
  or truncate a response.
- The 256k non-thinking calculator run modified both files, but its tokenizer regex
  put numbers and operators into different capture groups while the tokenizer still
  reads group 1. It also introduced a redundant `term` definition. Regression checks
  failed, and the next conservative request reservation could not fit the remaining
  input budget (`BUDGET_EXHAUSTED: request_tokens`). Its last settled input usage
  was 43,020 tokens; the 49,152 cap need not be reached exactly for a reservation
  to be refused.
- The 128k thinking calculator run recovered after one 4,096-token truncation and
  two repairs, eventually fixing both bugs. It used 12,850 output tokens and 173.0
  seconds. Its non-thinking counterpart passed in 20.8 seconds with 1,382 output
  tokens; that tokenizer uses a broader numeric regex, with conversion still
  rejecting malformed numbers.
- Passing diffs implement the requested fixes. All report runs left the correct
  `formatting.py` unchanged. The passing 128k shop run fixed all three defects and
  left tax calculation unchanged. Tests and protected files remained unchanged.

### Interpretation

**128k with thinking was the strongest configuration in this small sample:** all five
regression tasks passed, in 340.3 seconds total. Non-thinking was much faster on its
successful tasks but more vulnerable to invalid source-line citations.

The 256k configuration provided no observed success-rate benefit and used more runtime
memory. This does not establish that larger contexts reduce reasoning quality: there
was only one run per cell, execution paths differed, and runtime memory placement also
differed. The context capacities themselves were not stress-tested. A reasonable next
comparison would repeat with additional held-out tasks and separately measure
long-context retrieval before changing production defaults.

## Runtime memory

Representative `/api/ps` snapshots after each model's first call:

| Context | Reported runtime size | Reported GPU size |
| --- | ---: | ---: |
| 128k | 9.35 GiB | 9.35 GiB |
| 256k | 15.05 GiB | 12.47 GiB |

These are Ollama's reported allocations, not measured peak memory or proof that all
context slots were filled. The 256k configuration has a larger allocation and some
of its reported size is outside GPU memory. Timings reflect these local conditions.

## Artifacts and reproduction

Local ignored artifacts are under `tmp/qwen-context-comparison-2026-10-21/`:

- `run.py`, `run.log`, `manifest.json`, `harness.patch`, and `results.json`.
- Full `/api/show` definitions for both tags.
- Per-cell policy, request, call metrics, result, `candidate.diff`, and per-call
  runtime snapshots.
- Complete task journals and full response artifacts under `state/`.

From the Autocoder root:

```sh
.venv/bin/python tmp/qwen-context-comparison-2026-10-21/run.py \
  > tmp/qwen-context-comparison-2026-10-21/run.log 2>&1
```

The driver refuses to overwrite existing results. Copy `run.py` into a fresh sibling
directory under `tmp/` to repeat against the preserved fixtures. Later harness/model
revisions constitute a new experiment; use the captured manifests and definitions
to identify the versions tested here. Raw artifacts are local and not committed.

## Limits

These are small coding tasks. Enlarging the configured context does not fill it;
this is not a 128k/256k recall or long-context stress test. Input-token counts measure
actual prompt use, independently of the configured capacity.

One run per cell, known regression scripts, no held-out cases, no confidence intervals.
`VERIFIED_LOCAL` means the configured regression script passed, not independent
acceptance or production readiness. No candidate lint, remote CI or human acceptance
was performed. Functional passes can still contain style issues; for example the
thinking interval fixes at both context sizes add trailing whitespace.

Result review validated all 20 failing baselines, final statuses, token totals against
budget usage, identical fixture bases, and changes limited to declared editable files.
All 124 response runtime snapshots matched the requested context and pinned model
digest. Original fixture checkouts remained clean, and the pre-existing tracked
production diff remained unchanged. Documentation whitespace checks passed; the
production unit suite was not rerun for this experiment-only change.
