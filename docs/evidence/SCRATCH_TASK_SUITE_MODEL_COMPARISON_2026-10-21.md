# Scratch task suite: `qwen3.5:9b` vs `devstral-small-2:24b` (2026-10-21)

**Status:** Informal local comparison. Not a Stage 0 benchmark, not pre-registered, and
not acceptance evidence for any `docs/TODO.md` item. It extends the
[earlier scratch-project report](SCRATCH_PROJECT_MODEL_COMPARISON_2026-10-21.md).

## Purpose

The earlier report found `devstral-small-2:24b` fixing a three-file task that
`qwen3.5:9b` could not, from one task. This run adds four tasks of different shapes to
see whether that gap generalizes.

## Setup

| Item | Value |
| --- | --- |
| Harness revision | `96942a0` (`autocoder-task start`, v0 defaults) |
| Endpoint | `http://127.0.0.1:11434` (local Ollama, one request at a time) |
| Models | `qwen3.5:9b` (digest `56671c2ab938`, Q4_K_M) and `devstral-small-2:24b` (digest `24277f07f62d`, Q4_K_M) |
| Run order | All four qwen tasks, then all four devstral tasks, so the models never swapped on the GPU |
| Runs per cell | One. Earlier reruns showed qwen is effectively deterministic here, so repeating was not done |
| Tasks | Four throwaway Python projects under `tmp/tasks/` (ignored by Git, nested repos) |

Each task is a small project with a regression script that prints the literal signature
`expected regression failure` on each failing check. Each baseline fails, and a
hand-written reference fix passes (verified before the runs). The task text describes
symptoms only, never files or fixes. All source files in the project were readable and
editable. The runs used an untracked generator script from the session scratchpad. It
has since been rewritten and committed as `scripts/make_scratch_tasks.py`, which
recreates the same four tasks (`uv run python scripts/make_scratch_tasks.py --output
tmp/tasks`). The committed version was re-typed rather than copied, so the projects it
produces are intended to match the ones run here but are not guaranteed byte-identical.
Its policy files are also named differently (for example `paginate.qwen3-5-9b.json`).

| Task | Shape | Bugs |
| --- | --- | --- |
| `paginate` | 1 file | Page count truncates instead of rounding up; page numbers treated as 0-based; page 0 and negative pages not rejected |
| `calc` | 2 files | Tokenizer rejects decimals (`3.5`); evaluator treats `+ - * /` at one precedence level |
| `intervals` | 1 file | Unsorted input not sorted; touching intervals (`(1, 2)`, `(2, 3)`) not merged |
| `report` | 3 files | `median` wrong for even counts (`stats.py`); `max` uses the last value (`report.py`); `formatting.py` is correct and the task says so |

## Results

`VERIFIED_LOCAL` means only that the configured regression script passed. Lint, format,
held-out oracle, review, remote CI and human acceptance were all `not_run`.

| Task | `qwen3.5:9b` | `devstral-small-2:24b` |
| --- | --- | --- |
| `paginate` | `VERIFIED_LOCAL`; 6 tool calls, 1 repair, 39 s | `VERIFIED_LOCAL`; 1 tool call, 0 repairs, 84 s |
| `calc` | `FAILED_VERIFICATION` in ORIENT; 0 edits, 11 s | `BUDGET_EXHAUSTED` in VERIFY (tests fail after 3 repairs); 14 tool calls, 575 s |
| `intervals` | `VERIFIED_LOCAL`; 3 tool calls, 0 repairs, 16 s | `VERIFIED_LOCAL`; 1 tool call, 0 repairs, 71 s |
| `report` | `VERIFIED_LOCAL`; 5 tool calls, 0 repairs, 21 s | `FAILED_VERIFICATION` in ORIENT; 0 edits, 59 s |

Including the earlier three-file `shop` task (`qwen3.5:9b` stuck, `devstral-small-2:24b`
passed), each model passed 3 of 5 distinct tasks. The two models failed on different
tasks, so this set does not show that one model is better.

### Diff review of the passing runs

All six passing diffs touched only the files that needed changes, and no protected files
changed. Findings from reading them:

- `qwen3.5:9b` / `paginate`: correct, but with redundant code (a `page == 0` branch
  followed by an equivalent `page < 1` branch, plus explanatory comments).
- `devstral-small-2:24b` / `paginate`: correct, but it added an unrequested
  `ValueError` for `per_page <= 0` in both functions. That is a behavior change outside
  the task.
- `intervals` (both models) and `report` (`qwen3.5:9b`): minimal and correct.
  `report` left `formatting.py` untouched as instructed.

## Failure analysis

### Both ORIENT failures were a mis-copied SHA-256, not a wrong diagnosis

Both `FAILED_VERIFICATION` runs ended with `ValueError: Invalid phase artifact after one
decoding repair`, after two ORIENT responses and no edits. The harness requires each
orientation finding to carry the file's full 64-character `sha256`. Comparing the cited
hashes with the real ones:

| Run | File | Cited hash vs actual |
| --- | --- | --- |
| `calc` / `qwen3.5:9b` | `evaluator.py` | Identical for the first 20 characters, then wrong |
| `report` / `devstral-small-2:24b` | `report.py` | Identical for the first 15 characters, then wrong |

The other cited hashes matched exactly, as did the base revisions. The `report`
diagnosis from `devstral-small-2:24b` was exactly right (median averaging and
`max(values)`). The `calc` diagnosis from `qwen3.5:9b` was only half right: it found the
decimal tokenizer bug but called the evaluator's precedence handling correct. I did not
check why the repair attempt also failed, so I cannot say whether it repeated the same
hash error.

The hash exists so the coordinator can reject findings that are not anchored to current
source, which is a sound goal. Having the model transcribe 64 hex characters is the weak
part. The coordinator already knows the true hash for any path the model read, so it
could fill it in and validate only the path and line range. This suggestion is not
verified against the code beyond reading `Orientation`, `Finding` and the `validate`
function in `src/autocoder/v0/coordinator.py`.

### `devstral-small-2:24b` on `calc`: one fix, one regression

Its evaluator change was correct (`expr` now uses `term` and handles only `+` and `-`).
Its tokenizer change removed the plain-integer alternative from the regex, leaving only
decimal forms, so integers no longer tokenize. It also added unrequested unary-minus
handling with broken logic. Three repairs and 575 s did not recover. This is a model
failure and not a harness one.

## Observations and limits

- **Speed.** Passing runs took 16-39 s for `qwen3.5:9b` and 71-84 s for
  `devstral-small-2:24b`. When devstral succeeded it needed fewer tool calls (1 on
  both single-file tasks vs 3-6).
- **Small sample.** Five tasks, one run per cell, tasks authored in the same session as
  the harness-facing tests. No held-out cases, and contamination is not controlled. The
  models' pass counts are tied, which is all this supports.
- **Noise from the handoff check.** Two of the four non-passes never reached the edit
  phase. They measure hash copying and not coding ability, so a model comparison should
  treat them separately from edit failures.

## Possible follow-ups (not verified against the code)

1. Done: the coordinator now supplies each finding's `sha256` instead of asking the model
   to copy it, and keeps the anchoring check on path and line range (see the follow-up
   section below).
2. Done: both ORIENT failures were re-run after that change (see below).
3. Add a distinct status for the no-progress and handoff-validation stops. The earlier
   report also noted `BUDGET_EXHAUSTED` is misleading for the duplicate-operation stop.
4. Done: the task generator is now under version control as
   `scripts/make_scratch_tasks.py`, with a test in `tests/test_scratch_tasks.py`.

Relevant TODO item: P8-06 (alternate models) is the closest. These results do not close
it.

## Follow-up: coordinator-supplied digests (harness change)

Orientation findings are now emitted by the model as `path`, `start`, `end` and
`summary` only (`ModelOrientation` in `src/autocoder/v0/schema.py`). The coordinator
attaches each file's SHA-256 from the file it observed and rejects a finding whose line
range was not read at that file's current digest. The rejection message now names the
path, the cited range and the ranges that were observed, which gives the repair attempt
something to act on. The validated `Orientation` artifact, the plan's staleness check and
the journal are unchanged apart from the recorded handoff type name.

The two ORIENT failures were re-run with the same models and tasks (one run each):

| Task | Model | Status | Tool calls | Time |
| --- | --- | --- | --- | --- |
| `calc` | `qwen3.5:9b` | `VERIFIED_LOCAL`, both files fixed | 6 | 31 s |
| `report` | `devstral-small-2:24b` | `VERIFIED_LOCAL`, both files fixed | 4 | 104 s |

Both diffs were correct and limited to the bugs. `qwen3.5:9b`'s tokenizer pattern also
accepts forms such as `3.` and `.5`, which is broader than necessary but harmless here.
Updated pass counts over the five distinct tasks: `qwen3.5:9b` 4 of 5 (still missing the
`shop` task), `devstral-small-2:24b` 4 of 5 (still missing `calc`). This is still one
run per cell on small throwaway tasks, so it shows the handoff no longer blocks these
runs and nothing more. The test suite (106 tests) passes. The unit test that used a bad
hash to prove stale-handoff rejection now cites a line range that was never read.

### Second step: base revision

The `base_sha` field had the same transcription risk in both handoffs, although no run
had failed on it. `ModelOrientation` and the new `ModelPlan` no longer contain it. The
coordinator now builds `Orientation` and `Plan` with its own base revision, so the old
"cites a stale revision" checks are gone because there is nothing left to cite wrongly.
`Plan` now extends `ModelPlan` with the coordinator-supplied field. A new unit test checks
that a model-supplied `base_sha` is rejected and absent from both JSON schemas. The
suite now has 107 tests.

Spot re-runs after this change, one run each: `paginate` and `report` with
`qwen3.5:9b` and `intervals` with `devstral-small-2:24b` all finished `VERIFIED_LOCAL`
(2, 6 and 1 tool calls). This is a regression check on the handoff change, not a new
measurement.
