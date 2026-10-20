# Unicode review, interface retrieval and gateway trial — 2026-10-20

## Manually completed Unicode patch

The owner authorized finishing the Unicode fix, reviewing it before merging, and
continuing interface retrieval work. Reviewed commit `6e1e33f`, merged locally as
`b808060`, retains the model's byte-boundary source fix and manually corrects its
new test: supply a temporary unused config path, open a prompt, exercise the
one-byte overflow case, and send one ASCII key for an exact fit. No subprocess
or inference is needed for this test. This is a reviewer-assisted completion;
failed model trials and journals were not edited or relabeled successful.

Before merge, Ruff lint, Ruff formatting and `git diff --check` pass;
`uv run pytest -q`: **96 passed in 25.17 seconds**. Raw log:
`~/.local/share/autocoder/stage0/unicode-reviewed-verification.log`.
The corrected patch was reviewed locally and merged; no remote push occurred.

## Bounded class interfaces

Revision `36d35d8` adds observed class context when retrieval focuses a Python
method. AST parsing identifies its owning class and supplies constructor source,
public signatures, and bodies of short public methods that can show setup steps.
No candidate module is imported or executed. The context is confined to the
approved file and owning class; unrelated classes and unapproved files are excluded.

Constructor bodies, signature length and method count are bounded, with truncation
markers. Interface text uses at most one third of the existing per-file allowance
and never more than 1,200 characters; it does not raise the source/context budget.
Current source hashes remain on the containing frame. Fresh phase/repair prompts
rebuild this data rather than inheriting model reasoning or previous transcripts.

A regression test first demonstrated the missing constructor/setup context, then
verified its presence, owning-class scope, source limits and import avoidance even
when source would raise if imported. Ruff lint/format pass;
`uv run pytest -q`: **97 passed in 26.26 seconds**. Raw log:
`~/.local/share/autocoder/stage0/interface-context-verification.log`.
Frozen v5 protocol/engine checksum verification remains unchanged and passes.

## Third exploratory task: empty source ranges

On the merged base, `ToolGateway.read('empty.py', 100, 100)` unexpectedly returns
an empty source frame starting/ending at line 100, although there are no such lines.
The requested behavior preserves empty-file reading at start 1 and existing
nonempty/bound/hash/path behavior, but rejects empty-file starts above 1.

Trial folder: `~/.local/share/autocoder/trials/gateway-empty-read-qwen128k-v1/`.
Task: `78afbad310104c33995114ea1ca40a5b`; base `36d35d8`.
Only `src/autocoder/v0/gateway.py` and `tests/test_v0_context.py` are readable/
editable; the latter is explicitly approved. Trusted checks fingerprint all
original tests/helpers and all source functions except `ToolGateway.read`.
Independent checks cover empty/nonempty ranges and hashes, with public pytest,
Ruff lint and Ruff formatting gates. Base reproduction must fail exactly
`Empty source accepted start beyond line one`.

Model remains installed `qwen35-128k:latest`, digest
`a14034a9a68498756f82d5697930cebacde180e0521b48b415238bb10d6ee4ed`,
on the sole available Ollama endpoint. Context 32,768; limits 600 seconds,
98,304 input tokens, 8,192 output tokens, 60 tools, 20 tools per phase and
three repairs. The same read-only uv check runtime is pinned at
`48e04dae3af7d15e6c845b9700ed47870c2d90bc1901a1d6694de791159d0f50`.
No model download or budget increase was requested. This is an exploratory task
outside the TUI module, not broad cross-project acceptance or a frozen benchmark.

### Outcome and limits

**BUDGET_EXHAUSTED**, detail `request_tokens`, during ORIENT in the bounded
replan. Usage: 98.56 seconds, 87,761 input tokens, 5,578 output tokens, 21 tools
and two repairs. The next conservative reservation did not fit the remaining
input allowance. No increased limits or subsequent retuned trial was run.

The first IMPLEMENT request actually contains `ToolGateway`'s constructor
`__init__(self, workspace, budget, checks, navigator=None)` and short setup method
`enter(self, phase, paths=())`. Primary method source is 1,024 characters and
interface source 784 characters, within the existing per-file allowance.

The model fixed range validation and added a regression test. A truncated response
was discarded and the candidate entered independent verification. After one
repair, behavior, original-function/test preservation, lint and formatting passed.
Public pytest still failed: the new test creates a `Fixture` but passes `tmp_path`
as the repository and `tmp_path / 'tmp'` as state storage to `coordinator_for`.
Policy correctly rejects task state inside the source checkout. The model removed
an unused fixture variable during repair without correcting that root setup error.
The new test therefore did not complete its assertions. Final selected pytest
result: one failed, one passed, 17 deselected. No candidate commit was created.

Diff artifact:
`e2ec86e678341d72896d3a3cd622956d05b38f385915b4bd009abf8272d63953`.
All evidence and candidate edits remain in the private trial worktree. The main
checkout retains this gateway bug for a future controlled task; the reviewed
Unicode patch is the only target bug merged in this checkpoint. Held-out, remote
CI and human acceptance of the gateway candidate remain `not_run`.

Constructor/setup retrieval is implemented and deterministically tested, and its
presence is demonstrated in a real request. This run does not establish autonomous
completion or correct fixture usage. Broad reliability remains unresolved; no
new agents, models or larger budgets were introduced to disguise the failure.
