# Reviewed merge and second live task — 2026-10-20

## Approved report-phase merge

The owner approved merging the corrected `review/tui-report-phase` patch and
running another small bug through autocoder. Local merge
`041655f78d5630e6d0e6538d547cfe32769d81a5` contains generated commit `d64b995`
and review correction `eab9275`. The main checkout now updates report phases
without changing original status semantics and includes the regression test.
No remote push was performed. Original task journals remain unchanged; approval
of the corrected branch was not substituted for a decision on the original diff.

Merged checkout verification: `uv run ruff check .`,
`uv run ruff format --check .`, `git diff --check` pass;
`uv run pytest -q`: **92 passed in 23.80 seconds**. Raw log:
`~/.local/share/autocoder/stage0/report-phase-merged-verification.log`.

## Second bug and fixed trial policy

`Terminal.key` checks the input byte count before adding a printable character.
On the merged base, 8,191 ASCII bytes followed by `é` produces **8,193 bytes**,
exceeding the documented 8,192-byte prompt limit. Submission then rejects the
prompt. This reproduction requires no subprocess or model inference.

Task `9fea8f7caacb4ad9bea39059c0d6e699` asks for atomic rejection of overflowing
characters, exact UTF-8 boundary acceptance, unchanged backspace/Escape behavior,
and an added `test_prompt_utf8...` regression test. Editable/readable paths are
only `src/autocoder/v0/tui.py` and `tests/test_v0_tui.py`; test edits are explicitly
approved. Existing test functions and all source functions other than
`Terminal.key` are AST fingerprinted in trusted verification and must be preserved.

Frozen per-trial policy and request, journal, runtime pin and source snapshots:
`~/.local/share/autocoder/trials/tui-prompt-utf8-qwen128k-v1/`.
Model: installed `qwen35-128k:latest`, digest
`a14034a9a68498756f82d5697930cebacde180e0521b48b415238bb10d6ee4ed`;
endpoint `http://127.0.0.1:11434`; application context 32,768.
Limits: 600 seconds, 98,304 input tokens, 8,192 output tokens, 60 tool calls,
20 calls per phase and three repairs. No pull/download was requested.

Named checks cover independent two/four-byte boundaries and controls, AST
preservation, a public pytest subset, Ruff lint and Ruff formatting. The reviewed
uv check runtime is the existing complete venv mounted read-only at `/toolchain`,
digest `48e04dae3af7d15e6c845b9700ed47870c2d90bc1901a1d6694de791159d0f50`.
This exposes the pinned Ruff binary as well as site-packages. Baseline behavior
fails exactly `UTF-8 prompt byte limit exceeded`; unit/lint/format checks pass.

This is another exploratory task in the same TUI module, not a cross-project
benchmark or evidence of broad generalization. Frozen Stage 0 registrations are
unchanged. Held-out, remote CI and human acceptance of the second patch are not
claimed.

## Second-task outcome

**BUDGET_EXHAUSTED**, detail `request_tokens`; final phase ORIENT during the
single permitted replan. Usage: 83.66 seconds, 87,236 input tokens, 4,924 output
tokens, 19 tool calls, two repairs. A conservative next-request reservation did
not fit the remaining aggregate allowance; counters never exceeded the limit.

The model applied the intended UTF-8 boundary fix to the source, but its response
attempting companion work was truncated. The new `INCOMPLETE_RESPONSE` recovery
was exercised live: discard the complete model response, run independent checks,
and enter bounded fresh repair. Two candidate check rounds both found the added
regression test missing, a long source line (Ruff E501), and unformatted source.
The public pytest subset passed only its three existing selected tests. No test
file edit occurred. A subsequent repair/replan could not fit another reservation.
No candidate commit, verification success or human acceptance was recorded.

Diff artifact:
`fda689e8a5d7f99e6f345a4308d7dbe4464f8d8f03ab34df79a923790907cfb4`.
The incomplete candidate remains only in its retained worktree; it was not merged.
The main checkout retains the Unicode bug for a future controlled trial. The
owner-authorized first patch is merged; this second experiment demonstrates
recovery and honest rejection, not reliable autonomous completion of the new bug.
No further prompt/budget tuning was performed after observing this result.

Inspect without inference using the task's external launcher or the CLI:

```sh
uv run autocoder-task --config \
  ~/.local/share/autocoder/trials/tui-prompt-utf8-qwen128k-v1/project.json \
  status 9fea8f7caacb4ad9bea39059c0d6e699
```

## Repair-efficiency follow-up

Owner-authorized revision `da3517e` addresses two observed inefficiencies:

- Public diagnostics now identify every failing check within the same 4,096-character
  allowance. Space is reserved for each check header and divided between output
  excerpts, so a verbose first failure cannot hide lint, format or integrity failures.
  Only public verification records enter repair; held-out results remain terminal.
- During a running task, bounded source-range hints survive phase resets. Repair
  prompts re-read current source and hashes only for planned files, preserve explicit
  method focus, and clamp ranges after file shortening. Source body limits remain
  unchanged; prior assistant/tool transcripts are not inherited. Restart recovery
  still follows the normal bounded replan rather than restoring transient hints.

Regression tests first reproduced the lost later diagnostics and lost companion
excerpt. They cover 12 simultaneous verbose failures, stdout/stderr sharing,
tracked-input changes, truncated output, current hashes after edits, shortened
files, unplanned path exclusion, and transcript exclusion. Verification:
`uv run ruff check .`, `uv run ruff format --check .`, `git diff --check` pass;
`uv run pytest -q`: **95 passed in 24.85 seconds**. Raw log:
`~/.local/share/autocoder/stage0/repair-efficiency-verification.log`.
Frozen v5 protocol/engine checksum verification also passes unchanged.

A new trial, `tui-prompt-utf8-qwen128k-v2`, task
`dd21c26b2c1f45c8bec2fa320a7148b7`, uses base `da3517e`. Its request bytes and
project policy are identical to v1 except the external state directory; this
identity was checked before starting inference. Model, digest, application context,
98,304 input allowance, other limits, checks and runtime pin are unchanged. V1
policy, task worktree and all evidence remain preserved. No download or budget
increase was requested. This is an exploratory comparison, not a frozen benchmark
or a controlled claim of causal improvement from one stochastic run.

### V2 outcome

**BUDGET_EXHAUSTED**, detail `request_tokens`; final phase ORIENT during the
bounded replan. Usage: 94.98 seconds, 87,190 input tokens, 5,307 output tokens,
20 tool calls and two repairs. As in v1, the next conservative reservation did
not fit the remaining allowance. No budget increase or additional trial followed.

The live journal demonstrates the new prompt content: the first fresh REPAIR
request has a 1,304-character diagnostic naming `regression`, `lint`, and `format`.
Its current source frames cover `tui.py` lines 220–280 and the most recently
observed companion range, test lines 1–35. A truncated IMPLEMENT response was
fully discarded, checks ran, and repair started from this fresh public evidence.

The model added the required regression test and formatted both source edits and
new test. The second candidate verification passed independent UTF-8 behavior,
existing-test/unrelated-function preservation, Ruff lint and Ruff formatting.
However, public pytest failed: new `test_prompt_utf8` calls `Terminal()` without
its required `config` argument. Inspection also finds that the test does not open
an input prompt before exercising printable input. The constructor failure is the
observed runtime failure; subsequent assertions did not execute. No complete
candidate verification or candidate commit was recorded.

Diff artifact:
`1fef7eae91d45777947992692307b8473a6559b16aacd730ec1eb079825d6b3b`.
Both edited files remain in the private task worktree; the main checkout's
Unicode bug is deliberately unchanged. V1 failed with missing test/lint/format;
v2 passes behavior/lint/format but has an invalid test setup. This is progress
in the retained artifacts, not successful autonomous completion or proof of
causal improvement from a single comparison. Held-out, remote CI and human
acceptance remain `not_run`. No merge or push occurred.

### Later reviewed completion

Following owner approval, the Unicode patch was manually completed, fully tested
and merged locally as `b808060`. The original v1/v2 model trials remain failed.
See the [review/interface checkpoint](INTERFACES_AND_GATEWAY_2026-10-20.md) for the
reviewer's test corrections, 96-test gate, and separate third-task outcome.
