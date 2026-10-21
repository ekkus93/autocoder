# Scratch-project smoke tests and model comparison (2026-10-21)

**Status:** Informal local smoke tests. Not a Stage 0 benchmark, not pre-registered,
and not acceptance evidence for any `docs/TODO.md` item.

## Purpose

Check that the persistent v0 task runner (`autocoder-task`) completes real bug-fix
tasks end to end against the local Ollama server, using small throwaway projects
instead of a new repository. Then compare `qwen3.5:9b` with `devstral-small-2:24b`
on a harder multi-file task.

## Setup

| Item | Value |
| --- | --- |
| Harness revision | `2f860188af6e485f38909889dcdd5106063963b3` (working tree also had an uncommitted `.gitignore` change and untracked `AGENTS.md`) |
| Endpoint | `http://127.0.0.1:11434` (local Ollama, one request at a time) |
| `qwen3.5:9b` | digest `56671c2ab938`, 9.0B, Q4_K_M |
| `devstral-small-2:24b` | digest `24277f07f62d`, 24.0B, Q4_K_M |
| Context | v0 default (32,768 as logged in `MODEL_REQUEST` events) |
| Sandbox probe | `VERIFIED_LOCAL`; all five checks passed |
| Scratch projects | `tmp/testproj/` and `tmp/testproj2/` (separate nested Git repos, ignored by the main repository via `tmp/`) |
| Scratch revisions | `testproj` `8669a08`; `testproj2` `06aac6d` |

The scratch projects and their JSON policies are not tracked, so the runs can only be
reproduced by recreating them from the descriptions below. Task state lives under
`tmp/state/`.

## Test 1: single-file bug (`tmp/testproj`)

`src/stats.py` had `mean()` dividing by `len(values) - 1`. One editable file and one
regression script that fails with the literal signature `expected regression failure`.

| Model | Status | Tool calls | Repairs | Time | Tokens in/out |
| --- | --- | --- | --- | --- | --- |
| `qwen3.5:9b` | `VERIFIED_LOCAL` (tests pass) | 3 | 0 | ~17 s | 8,534 / 803 |

The diff changed only `len(values) - 1` to `len(values)`. The fix was committed on a
task branch; the original checkout was untouched and nothing was merged.

## Test 2: three-file bugs (`tmp/testproj2`)

A small `shop` package (`money.py`, `pricing.py`, `cart.py`) with three independent
bugs and one correct distractor. All three source files were readable and editable.

| Bug | File | Fix |
| --- | --- | --- |
| Cents not zero-padded (`$5.5`) | `money.py` | `{remainder:02d}` |
| Discount truncated instead of rounded half up | `pricing.py` | `(cents * percent + 50) // 100` |
| Quantity ignored in subtotal | `cart.py` | `price * qty` |
| `add_tax` already correct (task says not to change it) | `pricing.py` | none |

The baseline fails seven assertions across all three files. A hand-fixed scratch copy
passes, so the regression script is satisfiable. The task text described only symptoms,
not files or fixes.

### Results

| Model | Runs | Status | Files fixed | Tool calls | Time | Tokens in/out |
| --- | --- | --- | --- | --- | --- | --- |
| `qwen3.5:9b` | 1 + 5 reruns | `BUDGET_EXHAUSTED`, "duplicate tool operation without source progress" (all six) | 2 of 3 (`cart.py` missed) | 5 | ~30 s | 19,959 / 2,142 |
| `devstral-small-2:24b` | 1 | `VERIFIED_LOCAL` (tests pass) | 3 of 3 | 6 | 194 s | 19,087 / 1,320 |

An earlier attempt was blocked in preflight (`ConnectionResetError`) because Ollama had
stopped. It made no model call and is excluded.

### Qwen failure mode

The `money.py` and `pricing.py` edits applied. The `cart.py` edit raised `ValueError`:
the model's `old` text began with `def subtotal_cents(self):` at column 0, but the file
indents it four spaces inside the class, so the exact match failed. The intended
replacement and `expected_sha256` were correct. The model then re-read the file and
repeated the same edit, and the duplicate-operation guard ended the task. No
verification ran, so `tests` is `not_run` for these runs.

### Devstral result

The diff fixed all three bugs, left `add_tax` unchanged, touched no protected files, and
passed the configured regression check. It used the same editing interface without a
matching failure.

## Observations and limits

- **Qwen runs are one sample, not six.** All six used identical token counts
  (19,959 in, 2,142 out) and failed at the same step, so sampling is effectively
  deterministic in this configuration. "Failed 6 of 6" means "fails deterministically on
  this task". It does not estimate a failure rate. Measuring one needs a different seed
  or temperature, or more tasks. Whether the harness exposes either was not checked.
- **Devstral is a single run.** It succeeded once and took about six times as long as
  qwen's failed run. Timings were taken on an otherwise idle GPU, with the qwen reruns
  finished first to avoid model swapping.
- **One task, two models.** The result supports "the 24B model recovered where the 9B
  model got stuck on an exact-match edit". It does not support a general ranking.
- **Local scope only.** `VERIFIED_LOCAL` means the configured regression check passed.
  Lint, formatting, held-out oracle, review, remote CI and human acceptance were all
  `not_run`. No held-out cases were configured, and the tasks were authored by the same
  session that wrote the harness-facing tests, so contamination is not controlled.

## Possible harness follow-ups (not verified against the code)

1. When the duplicate-operation guard stops a task that already has edits, run the
   configured verification and one repair pass instead of ending in `IMPLEMENT`. The
   remaining `cart quantity` failure was visible to a deterministic check.
2. The status `BUDGET_EXHAUSTED` is misleading when only ~30 s and 5 tool calls were
   used. A distinct no-progress status would be clearer.
3. On an exact-match `apply_edit` failure, return an actionable error (for example the
   closest matching lines and their indentation) rather than a bare `ValueError`.

Relevant TODO items: P8-06 (model routing and alternate models) is the closest. None
of these results close it.
