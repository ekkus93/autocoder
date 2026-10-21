# Qwen 32k-context tag with thinking off and on (2026-10-21)

**Status:** Informal local experiment. One run per task and mode, known regression scripts,
no held-out oracle, no confidence intervals. It is not a Stage 0 benchmark and closes no
`docs/TODO.md` item. A pass means only that the configured regression script passed; lint,
remote CI and human acceptance were not run.

This completes the comparison suggested in the
[handoff](../HANDOFF_QWEN_TESTS_2026-10-21.md): the installed `qwen35-32k:latest` tag, run with
the same driver, tasks and limits as the 128k and 256k tags in the
[context comparison](QWEN_CONTEXT_THINKING_COMPARISON_2026-10-21.md). The earlier
[thinking comparison](QWEN_THINKING_COMPARISON_2026-10-21.md) used the generic `qwen3.5:9b`
tag.

## Setup

| Item | Value |
| --- | --- |
| Harness revision | `a458804e55bd7a2e2c475f9f1b36ca6fa6786136`, with no uncommitted tracked changes (the recorded diff hash is the SHA-256 of empty input) |
| Model | `qwen35-32k:latest`, digest `cb98bf1e233e1d1fe7abf04d09efc1f6a076740fd7e16131af6ff6138e7ac219`, 9.7B, Q4_K_M, parent `qwen3.5:9b` |
| Context | Explicit `num_ctx` 32,768 on every request |
| Limits | 4,096 output tokens per call and 16,384 per task; other limits unchanged (600 s, 49,152 input tokens, 60 tool calls, three repairs) |
| Sampling | Temperature 0, seed 42, one request at a time |
| Runtime | Ollama 0.40.6, local endpoint |
| Tasks | `paginate`, `calc`, `intervals`, `report` (from `scripts/make_scratch_tasks.py`) and the three-file `shop` package |
| Order | Thinking-off/on order alternated between tasks; no warm-up, cold load recorded separately |
| Driver | A copy of the 128k/256k driver with only the model list changed, in the ignored directory `tmp/qwen-32k-comparison-2026-10-21/` |

The driver's `manifest.json` still carries the settings text "Explicit 131072 or 262144",
copied unchanged from the earlier driver. The requested and observed context for every call
was 32,768, as the checks below show.

## Results

| Thinking | Passed | Total seconds | Output tokens |
| --- | ---: | ---: | ---: |
| Off | 3/5 | 64.0 | 3,810 |
| On | **5/5** | 348.6 | 25,489 |

| Task | Thinking off | Thinking on |
| --- | --- | --- |
| `paginate` | `FAILED_VERIFICATION` in ORIENT; 10.6 s, 1 repair, no edits | `VERIFIED_LOCAL`; 58.0 s, 5 tool calls, 4,135 output tokens |
| `calc` | `VERIFIED_LOCAL`; 21.7 s, 6 tool calls, 1,382 output tokens | `VERIFIED_LOCAL`; 176.0 s, 13 tool calls, 2 repairs, 13,018 output tokens |
| `intervals` | `VERIFIED_LOCAL`; 10.9 s, 1 tool call, 699 output tokens | `VERIFIED_LOCAL`; 34.2 s, 2 tool calls, 2,501 output tokens |
| `report` | `VERIFIED_LOCAL`; 16.6 s, 5 tool calls, 1,112 output tokens | `VERIFIED_LOCAL`; 34.9 s, 5 tool calls, 2,525 output tokens |
| `shop` | `FAILED_VERIFICATION` in ORIENT; 4.3 s, 1 repair, no edits | `VERIFIED_LOCAL`; 45.5 s, 7 tool calls, 3,310 output tokens |

I did not review the passing candidate diffs for this run, so correctness beyond the
regression scripts is not established here.

### Runtime and mode verification

- All 66 responses were recorded with a runtime context of 32,768 from `/api/ps` checked
  after each call. No fallback to a smaller context was observed.
- All 41 thinking-mode responses contained thinking text. None of the 25 non-thinking
  responses did.
- The largest prompt was 5,640 tokens, so these tasks exercise a 32k allocation but not a
  nearly full window. The longest model load took 2.8 s.

### The two ORIENT failures

Both non-thinking failures ended with `Invalid phase artifact after one decoding repair`
before any edit. The model's diagnoses were right; the cited line numbers were not.

| Task | File length | Cited ranges (first response / repair response) |
| --- | --- | --- |
| `paginate` | `src/pager.py` has 12 lines | 5-8, 13-16, 13-16 / 4-7, 13-16, 13-16 |
| `shop` | `src/shop/money.py` has 7 lines | `money.py` 10-12, `pricing.py` 8-9, `cart.py` 17-18 / `money.py` 5-8 only |

In `paginate`, the repair kept citing 13-16, past the end of the 12-line file. In `shop`,
the first response put `money.py` at lines 10-12 and the repair moved it to 5-8, which is
still one line past the end, and dropped the other two findings. The repair message names
the cited range and the lines that were actually read, but the repair responses still
failed. I did not test whether more explicit wording would help.

The anchoring check is working as intended: it rejects ranges that were never read. This is
the same failure the earlier session recorded for the 128k and 256k non-thinking runs.

## Comparison with the other tags

These come from different reports, so treat them as approximate. The 128k and 256k rows
come from the [context comparison](QWEN_CONTEXT_THINKING_COMPARISON_2026-10-21.md), with the
same driver and limits. The generic-tag rows used the earlier output limits.

| Tag and context | Thinking off | Thinking on |
| --- | --- | --- |
| `qwen35-32k` (this run), 32,768 | 3/5; 64 s; 3,810 tokens | 5/5; 349 s; 25,489 tokens |
| `qwen35-128k`, 131,072 | 3/5; 79 s; 4,118 tokens | 5/5; 340 s; 25,163 tokens |
| `qwen35-256k`, 262,144 | 2/5; 195 s; 5,380 tokens | 3/5; 439 s; 14,701 tokens |
| `qwen3.5:9b`, 32,768 (original limits, not matched) | 3/5; 90 s; 5,830 tokens | 4/5; 191 s; 14,559 tokens |

The 32k and 128k tags produced the same pass counts, and the same two tasks failed with
thinking off (`paginate` and `shop`, both in ORIENT). Total time and output tokens were also
close. On these small tasks the context size did not visibly matter; this says nothing
about long-context recall. The 256k tag differed in runtime placement as well as size (the
earlier report records 12.47 of 15.05 GiB in GPU memory), so its lower scores do not
isolate context length either.

The three custom tags share the same underlying weights, so the matched 32k/128k/256k
comparison is the cleanest available. Thinking is what moved the pass count (3/5 to 5/5 at
32k), at roughly 5 times the wall time and 6.7 times the output tokens.

## Devstral runtime-context check

The comparison of `devstral-small-2:24b` earlier in the session assumed it also ran at the
harness's configured 32,768 context. A separate single run confirmed it. `intervals` with
thinking off, using the same driver and per-call `/api/ps` check, passed
(`VERIFIED_LOCAL`, 57 s). All four snapshots reported `context_length` 32,768 for
`devstral-small-2:24b`, with about 13.1 GB of its 15.5 GB resident in GPU memory. That is
one task and small prompts (471-1,539 tokens), so it confirms the allocation, not the
behavior of a full window. Artifacts are in the ignored directory
`tmp/devstral-context-check-2026-10-21/`.

## Limits

- One run per cell, deterministic sampling (temperature 0, seed 42), five small tasks, tasks
  authored in the same session as the harness. Counts such as 3/5 versus 5/5 are suggestive,
  not statistically meaningful.
- The 32k, 128k and 256k runs used the same driver but ran at different times, with no
  repeat to measure run-to-run variation on the server.
- The repository's production default context is the project setting (32,768 unless
  configured otherwise); this run did not change any default.

## Possible follow-ups

1. Make the orientation repair more effective at line citations, without weakening
   anchoring, for example by supplying the file's line count in the first ORIENT request.
   Both non-thinking failures involved ranges past the end of a short file.
2. Repeat on more and harder tasks, and add a task that really fills a large window.
3. If thinking or a larger context is adopted, expose it as an explicit project setting
   with budget checks and tests, as the handoff suggests.

## Follow-up: line counts in the orientation repair (harness change)

The orientation repair message now lists every unanchored finding with the file's real line
count and the ranges that were shown, for example `src/pager.py lines 13-16: the file has 12
lines; lines shown to you: 1-12`. An unknown file is reported with the observed file names.
The anchoring rule is unchanged, and a unit test (108 tests now pass) checks the message for a
range that was never read and for an unobserved file.

The two non-thinking ORIENT failures were re-run with `qwen35-32k:latest` (same settings,
one run each, in the ignored directory `tmp/qwen-32k-repair-check-2026-10-21/`):

| Task | Before | After |
| --- | --- | --- |
| `paginate` | `FAILED_VERIFICATION` in ORIENT | `FAILED_VERIFICATION` in ORIENT (11.6 s) |
| `shop` | `FAILED_VERIFICATION` in ORIENT | Passed ORIENT, then `BUDGET_EXHAUSTED` in IMPLEMENT with "duplicate tool operation without source progress" (25.8 s, 6 tool calls) |

- `paginate`: the repair request carried the message above, but the model's second response
  again cited lines 13-16 of the 12-line file and also changed its first finding to 4-5.
- `shop`: the message flagged only `money.py` lines 10-12 (the file has 7 lines). The model
  corrected that finding to lines 6-7 but dropped the other two findings, which had been valid.
  Planning then covered only `money.py`, and the task stalled without fixing `pricing.py`
  or `cart.py`.

So the message gets the model to use a correct range in one of two cases, and neither task
passed. One run each is a small sample, but the `shop` result suggests the repair should also
tell the model to keep the findings that were already valid. That is a prompt change I have not
made or tested.
