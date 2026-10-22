# Exact-match edit errors: change and effect on the Qwen 32k matrix (2026-10-21)

**Status:** Informal local experiment. Five small tasks, known regression scripts, no held-out
oracle. It is not a Stage 0 benchmark and closes no `docs/TODO.md` item. A pass means only that
the configured regression script passed; I did not review the candidate diffs.

It follows the [repeats report](QWEN_32K_REPEATS_2026-10-21.md), which found `shop` with thinking
failing 0 of 5 because the model's first `apply_edit` did not match the file and it then resent the
identical edit.

## The change

Before, any `old` text that did not match exactly once produced the same error, `Edit requires
exactly one nonempty match`. `explain_edit_mismatch` in `src/autocoder/v0/workspace.py` now says
why, within the existing 512-character tool-error cap:

| Situation | Message |
| --- | --- |
| Empty `old` | `Edit old text must not be empty` |
| Several matches | The match count and up to five line numbers, and a request for more surrounding lines |
| Same non-blank lines, different blank lines or indentation | That fact, the line range, and the actual text (up to 300 characters) |
| Otherwise similar to a region (difflib ratio of 0.6 or more, files up to 3,000 lines) | The most similar region's line range and actual text |
| No match | A request to re-read the file and copy exact lines |

Edits still must match exactly once, so the rules for what is applied are unchanged; only the
error text is richer. Four new unit tests cover each message and the length bound, and the full
suite (112 tests) passes.

## Setup

Same as the repeats report: `qwen35-32k:latest` (digest `cb98bf1e233e1d1fe7abf04d09efc1f6a076740fd7e16131af6ff6138e7ac219`),
explicit 32,768 context, temperature 0, seed 42, 4,096 output tokens per call and 16,384 per task,
Ollama 0.40.6. Five complete sweeps of five tasks with thinking off and on (50 runs), run one after
another from copies of the same driver in the ignored directory
`tmp/qwen-32k-edit-error-repeats-2026-10-21/`. The sweeps started on the working tree that became commit `c22a2d8` (the
change above, committed while they ran).

## Results

| Task | Thinking off | Thinking on |
| --- | --- | --- |
| `paginate` | **0/5**, ORIENT failure | 5/5 |
| `calc` | 5/5 | 5/5 |
| `intervals` | 5/5 | 5/5 |
| `report` | 5/5 | 5/5 |
| `shop` | 5/5 | **0/5**, `BUDGET_EXHAUSTED` in IMPLEMENT |
| **Total** | **20/25** | **20/25** |

This is identical, cell by cell, to the earlier repeats without the new error text. Mean time per
run was 17.1 s with thinking off and 47.2 s with thinking on, against 17.5 s and 45.1 s before.
Token counts varied between sweeps within some cells, as before.

### What the model did with the new message

In all five `shop` thinking failures the first edit's `old` text for `money.py` had one blank line
after the module docstring where the file has two. The tool result was `Edit old text not found
exactly; it differs only in blank lines or indentation at lines 1-7`, followed by the actual text.
In all five the model's next response resent an edit identical to the first, and the
duplicate-operation guard ended the task. In the single case I read in detail, the model's
reasoning said the file had one blank line and that it would "match exactly", although the
message it had just received showed two. So for this cell the richer message was delivered and
did not change what the model did.

### Earlier smaller checks

- Two isolated runs of `shop` with thinking, started alone, both passed (12 tool calls each, 73-79
  s). Before the change this cell was 0/5, but the same cell failed in all five full sweeps, so the
  isolated passes may reflect what ran before it on the server and are not evidence that the
  change works. I did not test that explanation.
- One earlier full sweep, with the change in place, had further failures that did not recur in
  the five sweeps above: `calc` with thinking stopped on duplicate operations after an
  over-escaped regex edit, and one `intervals` run ended with `Runtime context mismatch ...
  observed None` because Ollama did not list the model as loaded when the driver checked.

## Interpretation and limits

- The change makes the failure reason visible to the model and to anyone reading the journal.
  It did not move any pass rate in this matrix.
- Five identical replicates of one setup, five small tasks, one model family. Cells that read 0/5
  or 5/5 do not give pass rates.
- Why the model ignored the text is not established. Candidates I have not tested: the blank
  lines are hard to see inside a JSON-escaped string, the thinking model prefers its own copy of
  the source over the tool message, or the guard fires before the model can try something else.

## Options not taken

1. Show the actual region with numbered lines and visible blank lines, a presentation change
   that keeps the matching rules.
2. Return the corrected `old` text as a separate field the model can copy verbatim.
3. Apply an edit when exactly one match exists after ignoring blank lines. This would change
   the edit primitive's fail-closed rule, so it needs an explicit decision and tests.
