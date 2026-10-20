# Context recovery checkpoint — 2026-10-20

## Scope and original failure

The owner's task `bce0ffb0e42f41e3a45c465681534cb7` stopped in ORIENT:
`BUDGET_EXHAUSTED`, context reserve exceeded after three successful reads.
It used 14,514 input tokens, 521 output tokens and about 14 seconds; this was
not a wall-time exhaustion. No source edits were made.

The task asks the model to repair non-event report phase handling in
`CommandClient.consume` and add a regression test while preserving existing tests.
The application bug remains in the original checkout for independent task review.

## Controller changes

Local revisions `cbeee14`, `90996b9`, `ebf6d13`, `fdbbb51` and `c21721f`:

- Bound ORIENT history before context/input reservation failure; retain explicitly
  named Python methods ahead of incidental source matches.
- Allow validated planning over approved companion files actually observed by
  tools, even when the model omits them from its orientation summary.
- Compact implementation history against both context and aggregate input limits;
  preserve observed edits, unfinished source and bounded operation summaries.
- Label diagnostics from before edits as historical. Omit already changed source
  bodies when necessary to retain unfinished files within the next reservation.
- Block duplicate reads before execution, then hand off orientation or run real
  candidate verification. Run verification after edits when inference cannot fit.
  Failed checks still require bounded repair; these paths never imply success.

Deterministic regression coverage includes incorrect candidates, unseen edit paths,
repeated reads and compacted progress. `uv run ruff check .` and
`uv run ruff format --check .` passed; `uv run pytest -q` passed **86 tests**
in 20.50 seconds. Raw log:
`~/.local/share/autocoder/stage0/orientation-context-verification.log`.
Frozen v5 protocol/engine checksums still pass; no Stage 0 registration changed.

## Live trials and limitations

All retries use installed `qwen35-128k:latest`, digest
`a14034a9a68498756f82d5697930cebacde180e0521b48b415238bb10d6ee4ed`,
through the single available Ollama endpoint. No model download was requested.
Context is 32,768; the model name does not change the configured context.
Default trial limits are 600 seconds, 49,152 input tokens, 8,192 output tokens,
60 tool calls and three repairs. These are exploratory trials, not scored benchmarks.

Retained folders under `~/.local/share/autocoder/trials/`, prefix
`tui-report-phase-qwen128k-context-fix`:

| Suffix | Result | Observation |
| --- | --- | --- |
| none | NEEDS_USER | Original mutable check runtime digest changed; no inference. |
| `-v2` | FAILED_VERIFICATION | Planner omitted an already observed companion file. |
| `-v3` | BUDGET_EXHAUSTED | Source edit applied; next input reservation did not fit. |
| `-v4` | BUDGET_EXHAUSTED | Duplicate read after compaction. |
| `-v5` | BUDGET_EXHAUSTED | Duplicate orientation read. |
| `-v6` | BUDGET_EXHAUSTED | Source fixed; required added test absent. |
| `-v7` | BUDGET_EXHAUSTED | Progress metadata retained, but repeated fresh reads still exhausted input before adding test. |

From v2 onward checks use a separate uv-created, hash-locked runtime, mounted
read-only. Its site-packages digest is
`b3469bbec80d2769a2f46757c4a2911ffb3ff0369a189e7fbb27efeb7ac0c049`.
From v5 onward scope is the two editable files and the request explicitly identifies
the non-event branch. Old task policies and evidence are preserved unchanged.

A separately recorded v8 trial increases only the input allowance to **98,304**
to test whether preserving more native conversation avoids premature resets.
Success at this allowance would not establish completion at the original budget.
No held-out, remote CI or human patch acceptance is claimed for these trials.

### Final v8 outcome

Task `c2ecf6b1c8b1495fabff5ec9212ae573`, base `c21721f`, ended
`BUDGET_EXHAUSTED` in IMPLEMENT: **Model response incomplete or output allowance
exhausted**. Usage was 83.01 seconds, 54,685 input tokens, 6,034 output tokens,
12 tool calls and zero repairs. The final response reached its individual
1,536-token cap; the larger aggregate input allowance did not establish success.
Both approved files were edited. A model-requested trusted behavioral/preservation
check passed, but full verification did not run. Inspection of the added test
also found unsupported `launch` arguments, so this is not a verified candidate.
Diff artifact: `5e35a0994e300d679fe7d7464d5f9b09847692e8799efea8a58cf908ff25ff85`.

The original checkout's target files remain unchanged. No patch was merged,
no task was marked accepted, and the existing user launcher still reattaches the
original failed task. All eight retry folders remain available for inspection.
Further live tuning is pending an operator decision; no reliable completion claim
for this model/task follows from these exploratory runs.

## Incomplete response recovery

Revision `619a97f` distinguishes an unfinished/truncated model response from a
hard aggregate budget failure. The backend still rejects the entire response,
including syntactically complete calls within it. During IMPLEMENT or REPAIR the
coordinator records `INCOMPLETE_RESPONSE`, returns to deterministic verification,
and uses the usual bounded fresh repair prompt if public checks fail. No partial
response or tool arguments enter repair context. Orientation/planning still fail
closed. Global time/token/tool/repair limits and private acceptance are unchanged.

Five regression cases first reproduced the terminal behavior, then verified:
correct edits pass real checks; incorrect edits require actual repair; tool calls
in truncated and unfinished responses never execute; repeated incomplete replies
without edits exhaust the repair budget rather than produce false success.

`uv run ruff check .` and `uv run ruff format --check .` pass;
`uv run pytest -q` reports **91 passed in 23.36 seconds**. Log:
`~/.local/share/autocoder/stage0/truncated-response-verification.log`.
Frozen v5 protocol/engine verification remains unchanged and passes.

A new v9 trial retains v8's model, digest, two-file request, checks and limits
(including its 98,304-input allowance). Task:
`b5ca38e35fd448afad3738e91f4cd8e7`; folder suffix `-v9`; base `619a97f`.

### V9 result and review

V9 completed **VERIFIED_LOCAL** in 56.41 seconds: 66,202 input tokens, 2,972
output tokens, 16 tool calls and zero repairs. Candidate checks passed:
trusted behavior/test-preservation check, pytest subset (3 passed/4 deselected),
and source/test parse check. Baseline failed the intended phase signature.
Generated commit: `d64b99583f340f0629f3e4802d965cc957555f4b`.
Diff artifact: `db2e182adfa363e8efc120ca404fcbf0e505b054d72fd3efb3d005395e87121a`.
No incomplete-response recovery occurred in this live run; that behavior is
verified by deterministic tests, not claimed as the cause of this completion.
Completion used more than the original 49,152-token allowance.

Review found an incidental status-semantics change and unformatted test code.
A separate worktree/branch, `review/tui-report-phase`, preserves the generated
result and adds review correction `eab92754c540ee4937de66c3a7532548da50ba6d`:
restore original status handling and format the added test. The resulting source
diff is only the intended phase assignment; existing test functions are preserved.
This correction was made by the reviewer, not attributed to Ollama.

The corrected branch passes Ruff lint, Ruff formatting, `git diff --check`, and
its complete suite: **92 passed in 23.46 seconds**. The complete suite was run
with the locked main uv environment and `PYTHONPATH` pointing explicitly at the
review worktree's `src`, so it imports the corrected candidate. Log:
`~/.local/share/autocoder/stage0/tui-phase-review-verification.log`.

The existing launcher now opens the original verified v9 task; `--check` confirms
its model and pinned runtime without inference. `--review-diff` prints the corrected
review branch diff. These are different artifacts: TUI approval would refer to the
original generated commit, not the corrected review branch. No human decision,
merge, push, remote CI, or held-out acceptance was recorded. The main checkout's
target source/test files remain unchanged; `AGENTS.md` is untouched.
