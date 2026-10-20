# Test setup retrieval and focused repair — 2026-10-20

## Controller changes

Revision `7d58fee` implements the owner-approved follow-up to repeated fixture
setup errors:

- Approved Python test files can carry a bounded setup excerpt from a test in the
  task's frozen Git base. It shows an observed context manager and local helper
  call with its revision and source lines. Candidate test edits cannot replace
  the example. These are usage excerpts, not standalone or independently qualified
  tests; no candidate module is imported or executed to obtain them.
- Examples share the existing per-file source allowance, capped at one third of
  that allowance and 1,000 characters. Fresh repair and compacted prompts retain
  the example while refreshing current source/hashes, only for planned paths.
- After an approved Python test-file edit and its complete tool batch, the
  controller returns to configured verification before another inference request.
  Operator-provided unit checks must cover new tests; no arbitrary model-generated
  test command is run. Passing early checks do not bypass final/private acceptance.
- Changed public diagnostics receive another focused repair. An unchanged public
  diagnostic after at least two failures can trigger the one bounded replan.
  Repair, tool, inference and elapsed-time limits are unchanged. This is text-based
  progress detection, not semantic classification of the error's root cause.

Three regression cases first failed on the prior controller, then passed: immutable
baseline setup examples surviving edits/refreshed excerpts; immediate verification
handoff after a test edit; changed public failures completing through focused
repair without a new orientation. Existing stalled-failure replan coverage passes.

`uv run ruff check .`, `uv run ruff format --check .`, `git diff --check` pass.
`uv run pytest -q`: **101 passed in 29.03 seconds**. Full log:
`~/.local/share/autocoder/stage0/fixture-repair-verification.log`.
Frozen v5 protocol/engine checksums pass unchanged.

## Fresh live rerun

Task `9b574133f13e441db672fa5615cf877a`, trial directory
`~/.local/share/autocoder/trials/gateway-empty-read-qwen128k-v2/`.
The new controller runs from `7d58fee` in the main uv environment. The original
buggy task source is a detached worktree at
`36d35d8c2f61cf67b507d324618d190d65cac6be`, matching v1's original base. This
allows reproducing the old task without reverting the reviewed main-branch fix.
Task worktrees/state are separate from this baseline; original v1 state is untouched.

The original request bytes and effective project policy were compared before
starting. Only repository/state directory locations changed. Editable files,
AST preservation checks, regression/unit/lint/format commands, runtime digest and
all limits remain unchanged. The runtime is the same read-only uv environment.
Installed `qwen35-128k:latest` digest:
`a14034a9a68498756f82d5697930cebacde180e0521b48b415238bb10d6ee4ed`;
context 32,768; limits 600 seconds, 98,304 input tokens, 8,192 output tokens,
60 tools, 20 tools per phase, three repairs. No model download, larger budget,
manual candidate edit, push or remote workflow dispatch was requested.

This is an exploratory rerun of a known task. It is not a blind held-out task,
registered benchmark, or evidence of general autonomous reliability.

### Observed live outcome

Task ended **BUDGET_EXHAUSTED**, detail `repairs`, during VERIFY. Usage:
111.05 seconds, 86,887 input tokens, 5,870 output tokens, 20 tools, three repairs.
There was one incomplete-response discard, two `EARLY_TEST_VERIFICATION` events,
and zero replans. All limits were enforced; no extra repair, manual candidate
correction or retuned follow-up run was performed.

The first IMPLEMENT prompt includes the actual baseline setup excerpt:

```python
with Fixture({"source.py": source, "helper.py": "VALUE = 1\n"}) as fixture:
    controller = coordinator_for(fixture.repository, tmp_path, None)
```

It is labeled with base `36d35d8` and lines 680–681 of
`test_focused_method_context_includes_bounded_constructor_and_setup_without_imports`.
That complete existing test also passes the configured baseline unit check; the
excerpt alone references its surrounding setup and is not a standalone program.

The model nevertheless constructed fixture files inconsistent with the helper's
fixed readable paths (`source.py`/`helper.py`). Workspace policy rejected this
setup rather than silently weakening the requirement. Its source edit also
rejected a valid empty-file read at start 1/end 120. Early verification exposed
both issues. Changed diagnostics received focused repair, but the model mainly
resolved style problems. Final lint/format passed; independent behavior and public
unit checks failed. No private oracle, hosted CI or human acceptance was recorded.

Diff artifact:
`08bcae4c59675c995426a6a50c108465daba244ff5632c03eaa3e5b59ed09e09`.
Final unit result: one failed, one passed, 17 deselected. No candidate commit was
created and the trial patch was not merged. The isolated buggy baseline and all
candidate evidence remain available. Main retains its reviewed, correct gateway
patch. The new controller code is committed locally; no remote push occurred.

This demonstrates baseline-example retrieval, early verification and bounded
focused repair in a live run. It does **not** establish that these changes solve
autonomous fixture usage or behavior interpretation. Further reliability work
needs measured task outcomes; another manual completion must not be counted as
autonomous success.
