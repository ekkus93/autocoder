# Qwen3.5:9b thinking versus non-thinking (2026-10-21)

**Status:** Informal local coding experiment, one run per task and mode. Not a
pre-registered benchmark or acceptance evidence for any TODO milestone.

Follow-up: [128k and 256k variants with thinking on/off](QWEN_CONTEXT_THINKING_COMPARISON_2026-10-21.md).

## Was thinking enabled before?

No. The earlier Autocoder scratch tests used the native Ollama transport through
`ModelBackend`, which does not pass a `think` argument. `infer` defaults to
`think=False` and explicitly includes that value in the `/api/chat` payload.

This experiment explicitly passed `think=False` or `think=True` through a transport
wrapper. The default-limit runs returned thinking text in all 25 thinking-mode
responses, and zero thinking characters in the non-thinking responses. Only counts
are reproduced here; full transport responses remain in the local task journals.

## Matched setup

- Model: `qwen3.5:9b`, Q4_K_M, digest
  `56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90`.
- Local Ollama `0.40.6`, `http://127.0.0.1:11434`, one task/request at a time.
- Harness HEAD: `114aa9891f0bdfa0753b89cc281f5bbeb1a5af15`, plus the existing
  uncommitted coordinator-supplied hash/base-revision changes. The exact tracked diff
  was captured in `harness.patch`; SHA-256 of the captured text:
  `6594382c8d2a79a538da43f76677bb1916a4dbb7002e2eaa7dfc694742d13d6d`.
- Same fixture baseline, task request, source policy, checks and harness for each pair.
  Fresh task IDs and isolated worktrees; original scratch checkouts remained clean.
- Context: 32,768; temperature: 0; seed: 42. No production source was changed for this
  experiment, and no candidate was integrated into its original project.
- Default limits: 600 seconds, 49,152 input tokens, 8,192 total output tokens,
  60 tool calls, three repairs. Per-call caps remained 768/1,024/1,536 as selected by
  the existing harness. Reasoning and final output share the output allowance.
- Order: paginate off/on, calc on/off, intervals off/on, report on/off, shop off/on.
  No warmup; the first off run includes about 2.5 seconds of model load time.

Tasks are the existing fixtures described in the
[four-task suite](SCRATCH_TASK_SUITE_MODEL_COMPARISON_2026-10-21.md) and
[shop comparison](SCRATCH_PROJECT_MODEL_COMPARISON_2026-10-21.md).
All ten default-limit runs reproduced a failing baseline before attempting changes.

## Default-limit results

Times include the full harness run. Output counts are Ollama's `eval_count`, including
thinking. A pass means `VERIFIED_LOCAL`: the configured regression script passed.

| Task | Thinking off | Off seconds | Off output tokens | Thinking on | On seconds | On output tokens |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| Pagination: page count and indexing | Pass | 20.7 | 1,151 | Pass | 43.4 | 3,324 |
| Calculator: decimals and precedence | No progress | 29.3 | 2,032 | Truncated in ORIENT | 15.4 | 1,024 |
| Intervals: sort and merge touching ranges | Pass | 15.8 | 1,076 | Pass | 35.4 | 2,777 |
| Report: even median and maximum | Pass | 18.1 | 1,220 | Pass | 37.8 | 2,928 |
| Shop: money, discounts and quantities | Invalid ORIENT artifact | 6.2 | 351 | Pass | 59.3 | 4,506 |
| **Total** | **3/5 pass** | **90.1** | **5,830** | **4/5 pass** | **191.2** | **14,559** |

Thinking used 2.50 times the output tokens and 2.12 times the elapsed time across
this suite. These totals include early stops, so they are not a speed comparison at
equal success. On the three tasks both modes passed, thinking took about twice as long.

### Failure details and diff review

- Calculator/off: corrected precedence in `evaluator.py`, but failed to change the
  tokenizer. The harness stopped a repeated tool operation without source progress
  in IMPLEMENT (`BUDGET_EXHAUSTED`). This status did not mean the token budget ran out.
- Calculator/on: hit the 1,024-token ORIENT cap with `done_reason=length`, before any
  tool calls or edits. The harness rejected the incomplete response as designed.
- Shop/off: cited invalid source line ranges during ORIENT. Its repair cited lines
  6–8 of `money.py`, which has only seven lines. It failed validation before any edit
  (`FAILED_VERIFICATION`), despite identifying the main issues in the initial response.
- Shop/on: fixed all three defects with small edits: two-digit cents formatting,
  integer half-up discount rounding, and multiplication by item quantity. The tax
  function remained unchanged.
- The other passing diffs implement the requested fixes. Both report runs left the
  correct `formatting.py` unchanged. Neither mode changed tests or protected files.

## Larger-allowance follow-up

The calculator pair was repeated because its thinking run was truncated. This is a
targeted diagnostic follow-up, not another five-task aggregate. Both modes received
4,096 output tokens per call and 16,384 total output tokens; context, input budget,
time, tools, repair limits and task fixtures remained unchanged. Order was off/on.

An experiment-local `ModelBackend` subclass changes allocation before reservation,
context checking and journaling. It does not silently increase `num_predict` beyond
the harness's recorded allowance. Production code remains unchanged.

| Calculator mode | Result | Seconds | Input tokens | Output tokens | Truncated responses |
| --- | --- | ---: | ---: | ---: | ---: |
| Thinking off | No progress in IMPLEMENT | 32.6 | 20,936 | 1,606 | 0 |
| Thinking on | Pass | 247.2 | 32,223 | 14,403 | 2 |

The thinking orientation response finished at 1,025 output tokens, just beyond the
original cap. Two later responses hit the 4,096-token implementation/repair limit
without an executable edit and were discarded. The harness recovered through two
repairs and a renewed orientation/plan, eventually fixing both precedence and decimal
tokenization. The final diff was limited to those two changes; tests were unchanged.
Non-thinking again fixed precedence but stopped on a duplicate operation without
repairing the tokenizer.

This does not establish a five-of-five result under the expanded limits: only the
calculator pair was rerun under those limits. It shows that thinking can solve this
task when allowed considerably more output and recovery time.

## Practical next step

Keep the current non-thinking default until thinking mode and per-phase output
allowances are explicit configuration, covered by transport/budget checks. Thinking
is worth testing as an opt-in mode for harder tasks, with a larger output allowance
and a clear time limit. Repeat on additional, held-out tasks before choosing a default
or comparing overall cost per successful fix. The small sample favors thinking's
success rate here, while also showing a substantial latency and token cost.

## Artifacts and reproduction

Local artifacts (ignored by Git) are under:

```text
tmp/thinking-comparison-2026-10-21/
tmp/thinking-comparison-2026-10-21-expanded/
```

Each contains `run.py`, `run.log`, `manifest.json`, `harness.patch`, `results.json`,
per-cell policy/request/call metrics/result files, `candidate.diff` snapshots, and
complete task journals under `state/`. Result files carry
task IDs, fixture base commits, worktree paths and evidence directories.

Commands used from the Autocoder root:

```sh
.venv/bin/python tmp/thinking-comparison-2026-10-21/run.py \
  > tmp/thinking-comparison-2026-10-21/run.log 2>&1
.venv/bin/python tmp/thinking-comparison-2026-10-21-expanded/run.py \
  > tmp/thinking-comparison-2026-10-21-expanded/run.log 2>&1
```

The drivers refuse to overwrite existing results. To repeat, copy a driver into a
fresh sibling directory under `tmp/` and run that copy against the preserved fixtures.
The manifests and captured patch describe the harness used here; a later harness
revision would be a new experiment. Raw artifacts are local and are not committed.

## Limits

These are small, known regression tasks with one run per cell, no held-out tests and
no statistical confidence estimate. Historical non-thinking results are not used as
the control: both modes were rerun against the same current working tree. Fresh
results differ from some historical runs, so do not assume determinism from a fixed
seed alone. This supports a local harness decision, not a general model ranking.

The result review checked baseline failures for all ten primary runs, output totals
against recorded budget usage for all twelve runs, passing regression statuses, and
unchanged protected paths. Both expanded runs also reproduced the baseline failure.
Only configured regression checks and diff review support the candidate findings.
No held-out oracle, remote CI or human acceptance was performed. The experiment made
no production code changes. `git diff --check` and whitespace validation of this new
report passed; the production unit suite was not rerun for this experiment-only change.
