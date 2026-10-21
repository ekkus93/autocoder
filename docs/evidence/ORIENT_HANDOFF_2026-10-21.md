# Truncated discovery handoff recovery — 2026-10-21

## Interrupted-session audit

The previous contract/checklist trial had already ended before the reported
interruption. Task `3afe5b4688c343ffa81fd5c91bf9aa0c` and its evidence were intact:
failed checks, no candidate commit, and a truncated replan discovery reply.
No running task was resumed or silently reclassified successful.

## Controller correction

Revision `a099efc` catches only incomplete native ORIENT discovery responses.
The entire response and all its proposed calls are discarded. The coordinator
then attempts its existing fresh structured handoff using source already observed
successfully. Schema, path, source hash, location and base-revision validation
remain mandatory. An invalid handoff still gets only the existing bounded decoding
repair; incomplete structured orientation/planning responses remain terminal.
No token/context/time/tool/repair limits were increased.

Two regression cases first failed on the prior controller. They verify that prior
successful source reads survive recovery, a proposed read in the truncated reply
never executes, valid handoffs pass and stale-hash handoffs fail closed.
`uv run ruff check .`, `uv run ruff format --check .`, `git diff --check` pass;
`uv run pytest -q`: **103 passed in 31.82 seconds**. Raw log:
`~/.local/share/autocoder/stage0/orient-handoff-verification.log`.
Frozen v5 protocol/engine checksum verification also passes unchanged.

## Fresh full-loop trial

Task `b5f12ca2c36243c49c83ed9a934ca05f`, folder
`~/.local/share/autocoder/trials/gateway-empty-read-qwen128k-v4/`.
Controller is `a099efc`; candidate source starts at the original buggy
`36d35d8c2f61cf67b507d324618d190d65cac6be` in an isolated baseline worktree.
Main's reviewed gateway fix is unchanged. Prior trial worktrees and journals are
preserved. Request bytes and policy were compared before inference: only external
repository/state locations differ from v3. The five behavior/unit/lint/format/
coverage checks, explicit contract/checklist, model/digest, context and all limits
are unchanged. The coverage gate remains the previously qualified 13-fault gate.

Installed model: `qwen35-128k:latest`, digest
`a14034a9a68498756f82d5697930cebacde180e0521b48b415238bb10d6ee4ed`.
Limits: context 32,768; 600 seconds; 98,304 input tokens; 8,192 output tokens;
60 tools, 20 per phase; three repairs. No model download, broader path access,
manual candidate correction or remote mutation was requested. This is an
exploratory known-task rerun, not registered benchmark or broad reliability proof.

### V4 outcome and subsequent repair-policy finding

V4 ended **BUDGET_EXHAUSTED**, `request_tokens`, during a replan ORIENT handoff.
Usage: 126.91 seconds, 85,018 input tokens, 5,897 output tokens, 17 tools,
three repairs. The next conservative reservation did not fit the remaining input
allowance. The source edit preserves existing nonempty behavior and fixes empty
starts. The added test passes public unit verification and catches **all 13 faults**.
Independent behavior/preservation and formatting checks also pass. Only Ruff lint
fails, on two overlong copied checklist comments. No candidate commit was created.
Diff: `99d250f7d08d0be907f514a6c8c04a442b5cac0a33d9177aa04e5bb193530b85`.

V4's early trajectory differed from v3, and it did not exercise truncated-discovery
recovery. That feature is verified by the deterministic tests, not claimed as the
cause of v4's improved behavioral result. This remains a failed full-loop trial.
All checks must pass; coverage success does not override lint failure.

The failure also revealed that unchanged **style-only** diagnostics triggered a
full architecture replan. The follow-up keeps lint/format-only failures in local
repair. Actual behavior/test failures retain the existing bounded replan rule.
Style failures still consume repairs and block acceptance; no formatter, arbitrary
command or automatic acceptance was added.

## Style-only focused repair and V5

Revision `1bccaa2` restricts architecture replanning to failures that include at
least one non-lint/non-format check. A regression test reproduced the style-only
replan, then verified local repair completes without a new orientation. Existing
semantic-failure replan coverage remains passing. Ruff lint/format and whitespace
checks pass; `uv run pytest -q`: **104 passed in 28.49 seconds**. Full log:
`~/.local/share/autocoder/stage0/style-repair-verification.log`.

A final fresh trial, `gateway-empty-read-qwen128k-v5`, task
`573deea7e22b4a779bd860d5ee1ab6cf`, uses controller `1bccaa2` and candidate base
`36d35d8`. The preparer compared request/policy to v4 before inference; only
repository/state locations changed. No change to model, context, token/time/tool/
repair limits, task requirements, qualified coverage gate, or other checks.
Neither v3 nor v4 state was resumed or edited. No source/test changes have been
made to a candidate outside the model's recorded tools.

### Final V5 outcome

V5 ended **BUDGET_EXHAUSTED**, `request_tokens`, in REPAIR. Usage: 82.10 seconds,
88,079 input tokens, 4,718 output tokens, 19 tools and one repair. The next
conservative reservation did not fit. Its source edit satisfies the trusted
behavior checks until the required-new-test assertion, but the model never
edited the test file. Candidate unit checks passed only the existing selected
test. The required new test and coverage checks therefore failed; lint/format
passed. No candidate commit or acceptance was recorded.

Diff artifact:
`0f989411256cb3223af6617787f2695b3a15892c166fa3b1d2581fd07b53f74f`.
This trajectory did not reach a style-only failure, so the style-specific policy
is verified by its deterministic regression test, not a claimed live causal win.
Likewise, incomplete-discovery recovery was not exercised in these two new live
trials. The better V4 behavioral result and worse V5 completion do not establish
causal improvement or deterioration from one sample of each policy.

Both V4 and V5 remain failed. Their policies, prompts, baselines and task worktrees
are retained. The final same-budget trial was not followed by more prompt tuning,
manual candidate edits or a larger allowance. Controller changes are committed
locally and its full suite passes 104 tests; main's reviewed source/test fixes are
unchanged. No push, remote CI, held-out acceptance or new human decision occurred.
The remaining limitation is full-loop completion: repeated source reads and
production/test work together can consume the input allowance even when a focused
test-writing call completes the same test correctly.
