# Qwen 32k context: five repeats of every task and mode (2026-10-21)

**Status:** Informal local experiment. Five tasks, small throwaway projects, known regression
scripts, no held-out oracle. It is not a Stage 0 benchmark and closes no `docs/TODO.md` item.
A pass means only that the configured regression script passed; lint, remote CI and human
acceptance were not run, and I did not review the candidate diffs for this run.

It repeats the matrix from the [32k comparison](QWEN_32K_CONTEXT_THINKING_2026-10-21.md), which
had one run per cell, to see how stable each result is. That report's follow-up sections
describe the orientation-repair changes tested on single runs.

## Setup

| Item | Value |
| --- | --- |
| Harness revision | `227617b` (includes coordinator-supplied digests and base revisions, the line-count repair message and the keep-valid wording) |
| Model | `qwen35-32k:latest`, digest `cb98bf1e233e1d1fe7abf04d09efc1f6a076740fd7e16131af6ff6138e7ac219`, explicit `num_ctx` 32,768 |
| Limits and sampling | 4,096 output tokens per call, 16,384 per task, other limits unchanged; temperature 0, seed 42; one request at a time |
| Runtime | Ollama 0.40.6, local endpoint |
| Matrix | `paginate`, `calc`, `intervals`, `report`, `shop`, each with thinking off and on |
| Repeats | Five complete sweeps, run one after another, so 50 runs in all |
| Driver | Five copies of the 32k comparison driver, one per sweep, in the ignored directory `tmp/qwen-32k-repeats-2026-10-21/run-N/` |

Every sweep used the same task order and the same alternation of thinking off and on, so the
five repeats are replicates of one setup, not draws from different run orders.

## Results

| Task | Thinking off | Thinking on |
| --- | --- | --- |
| `paginate` | **0/5**, ORIENT failure every time | 5/5 |
| `calc` | 5/5 | 5/5 |
| `intervals` | 5/5 | 5/5 |
| `report` | 5/5 | 5/5 |
| `shop` | 5/5 | **0/5**, `BUDGET_EXHAUSTED` in IMPLEMENT every time |
| **Total** | **20/25** | **20/25** |

| Mode | Mean seconds per run | Mean output tokens per run |
| --- | ---: | ---: |
| Thinking off | 17.5 | 1,103 |
| Thinking on | 45.1 | 3,314 |

Mean time per cell, thinking off then on: `paginate` 7.3 s then 52.4 s; `calc` 21.3 s then
69.1 s; `intervals` 11.4 s then 34.3 s; `report` 21.9 s then 34.2 s; `shop` 25.9 s then
35.3 s. Total time per sweep was 428 s for the first and 278-296 s for the other four; the
first sweep includes cold model loading.

## Stability

- **Pass/fail never changed between repeats.** In all ten cells, either all five repeats passed
  or all five failed. Each sweep passed 4 of 5 tasks in each mode.
- **Details did vary.** Token counts and tool-call counts differed between repeats in most
  cells. For example, `paginate` with thinking produced five distinct output-token signatures
  across five sweeps, and `calc` with thinking four. Four cells were identical every time:
  `calc`, `intervals` and `report` with thinking off, and `shop` with thinking on. So the server is not bit-for-bit deterministic
  at temperature 0 and seed 42, but the outcomes were stable here.
- **Modes fail on different tasks.** Thinking off failed only `paginate`; thinking on failed
  only `shop`. Between them every task passed in at least one mode.

## Failure analysis

### `paginate`, thinking off: orientation citations

All five runs ended with `Invalid phase artifact after one decoding repair` before any edit.
This is the failure examined in the earlier report: the model's diagnosis is right, but it cites
lines past the end of the 12-line `src/pager.py`, and the repair message with the real line
count did not change that. The line-count and keep-valid message changes did not fix this cell.

### `shop`, thinking on: a whitespace mismatch in an edit

All five runs stopped in IMPLEMENT with "duplicate tool operation without source progress".
In the two sweeps I inspected, the first `apply_edit` failed with a `ValueError`. The model sent
an `old` string for `money.py` that had one blank line between the module docstring and the
`def`, while the file has two. It then re-read the file and repeated the same edit, and the
no-progress guard stopped the task. This is the same exact-match edit failure that stopped
`qwen3.5:9b` on this task in the very first scratch comparison. I did not inspect the other three
sweeps in detail.

## Comparison with the single-run results

The single 32k run from the earlier report gave `shop` thinking off a failure (ORIENT) and
thinking on a pass. Under the repeats it is the reverse for both: 5/5 off and 0/5 on. Between
those runs the orientation repair message changed, and the run order differed. I did not isolate
which of these caused the flips, and the earlier single-run result for each cell is not
evidence of how often it passes. One tentative reading is that small differences in the
prompts or server state can flip a borderline cell, but the data here do not test that.

The other eight cells agreed with their earlier single runs.

## Limits

- Five replicates of one setup measure repeatability, not generalization. Five small tasks, all
  authored in the same session as the harness, with the regression scripts as the only oracle.
- Pass rates of 0/5 and 5/5 are consistent with a wide range of true rates; they do not give
  reliable percentages.
- Only the `shop`/thinking-on failure was inspected for cause, and in two of five sweeps.
- Earlier in this session I said single runs were noisy and that the server was not
  deterministic. The more accurate statement is that pass/fail was stable across replicates
  here, while token-level details varied.

## Possible follow-ups

1. Return an actionable error for an exact-match `apply_edit` failure (for example the nearest
   matching lines and their blank-line count). It would address the `shop` thinking failure and
   the failure that stopped the very first `qwen3.5:9b` run.
2. Look again at the `paginate` orientation failure with thinking off, for example by providing
   the line count in the first request as well as in the repair.
3. Review the passing candidate diffs, since a green regression script does not establish
   correctness.
