# Stage 0 pilot: pilot-v5-01

Registration SHA-256: `c04da250ab2f317ff8f4dabef3f18d91530e75811d6ed5a68f730e89ade87307`.

Local synthetic screening results; no CI or owner acceptance is claimed.

## Initial eight tasks

| Task | Loop | Aider | OpenCode |
| --- | --- | --- | --- |
| py-clamp | VERIFIED_LOCAL | VERIFIED_LOCAL | VERIFIED_LOCAL |
| py-chunks | VERIFIED_LOCAL | VERIFIED_LOCAL | VERIFIED_LOCAL |
| py-dedupe | VERIFIED_LOCAL | FAILED_VERIFICATION | VERIFIED_LOCAL |
| py-config | VERIFIED_LOCAL | VERIFIED_LOCAL | BUDGET_EXHAUSTED |
| rs-clamp | VERIFIED_LOCAL | VERIFIED_LOCAL | VERIFIED_LOCAL |
| rs-divceil | VERIFIED_LOCAL | VERIFIED_LOCAL | VERIFIED_LOCAL |
| rs-ranges | FAILED_VERIFICATION | VERIFIED_LOCAL | VERIFIED_LOCAL |
| rs-config | FAILED_VERIFICATION | FAILED_VERIFICATION | BUDGET_EXHAUSTED |

## Aggregate metrics

All scheduled runs, including repeated tasks; means include failures.

| Arm | Initial pass | Repeat pass | Mean seconds | Mean input/output tokens |
| --- | ---: | ---: | ---: | ---: |
| minimal_loop | 6/8 | 6/6 | 9.83 | 1782/645 |
| aider | 6/8 | 6/6 | 17.41 | 2557/594 |
| optimized_opencode | 6/8 | 3/6 | 12.35 | 9470/558 |

## Shared successful initial tasks

Post-hoc descriptive subset: py-clamp, py-chunks, rs-clamp, rs-divceil.
Excluded failures remain in all primary completion rates above.

| Arm | Mean seconds | Mean input/output tokens |
| --- | ---: | ---: |
| minimal_loop | 9.72 | 1423/599 |
| aider | 14.35 | 2170/472 |
| optimized_opencode | 9.86 | 7352/398 |

## Repeat stability

Preselected tasks, three additional rounds each.

| Task | Arm | Initial, repeat 1, repeat 2, repeat 3 |
| --- | --- | --- |
| py-config | minimal_loop | VERIFIED_LOCAL, VERIFIED_LOCAL, VERIFIED_LOCAL, VERIFIED_LOCAL |
| py-config | aider | VERIFIED_LOCAL, VERIFIED_LOCAL, VERIFIED_LOCAL, VERIFIED_LOCAL |
| py-config | optimized_opencode | BUDGET_EXHAUSTED, BUDGET_EXHAUSTED, BUDGET_EXHAUSTED, BUDGET_EXHAUSTED |
| rs-divceil | minimal_loop | VERIFIED_LOCAL, VERIFIED_LOCAL, VERIFIED_LOCAL, VERIFIED_LOCAL |
| rs-divceil | aider | VERIFIED_LOCAL, VERIFIED_LOCAL, VERIFIED_LOCAL, VERIFIED_LOCAL |
| rs-divceil | optimized_opencode | VERIFIED_LOCAL, VERIFIED_LOCAL, VERIFIED_LOCAL, VERIFIED_LOCAL |

## Task-level unrecovered outcomes

- `minimal_loop`: 2/14 unrecovered; {'FAILED_VERIFICATION': 2}.
- `aider`: 2/14 unrecovered; {'FAILED_VERIFICATION': 2}.
- `optimized_opencode`: 5/14 unrecovered; {'BUDGET_EXHAUSTED': 5}.

## Failure classification

Classification uses stored status/check artifacts; no model adjudication.

| Arm | Failure category | Runs |
| --- | --- | ---: |
| aider | public check or bounded repair failure | 1 |
| aider | public compilation failure after bounded repair | 1 |
| minimal_loop | public check or bounded repair failure | 1 |
| minimal_loop | public compilation failure after bounded repair | 1 |
| optimized_opencode | resource budget | 5 |

## Limits and interpretation

Private expected values stay outside candidate worktrees and model feedback. Public checks and terminal held-out checks have separate artifacts. Passing compilation or public checks alone cannot produce final acceptance.

Tasks are tiny seeded Python/Rust fixtures. Repeated deterministic prompts are correlated, not independent evidence of general coding reliability. Per-task hidden cases check target behavior, not broad real-project regression coverage. No controlled pilot ablation isolates context or cache effects; see the separate component report for those measurements.

All arms use the registered digest, 32K context, thinking disabled and the same task limits. Client prompts, edit protocols, tool accounting and startup overhead differ. The inference proxy translates compatible requests to native Ollama. The repairs counter bounds outer public-check retries. Client-internal edit-format retries consume time/tokens but do not increment that counter; Aider's text edit proposals also do not count as native tool calls. A conservative UTF-8 request-size reservation can refuse an invocation before actual reported input tokens reach the cap, especially for chatty clients. Budget failures remain failures. These limitations prevent a fair claim of general superiority from token or timing differences alone.

V4 checks public import/compilation; v5 adds shared public functional feedback and replaces the loop's nested edit payload with flat tool calls. They are different registered conditions, not interchangeable replicates.

Metadata caveat: v5 inherits several v4 descriptions saying only public compilation feedback and no expected values. V5's explicit rationale, public_repair setting, public-checks.json and bound executable instead declare public functional cases. The no-exposure claim applies to private oracle values. This inherited descriptive inconsistency is retained in the immutable registration and disclosed here.

## Evidence

- Completed runs: 42.
- Raw summary: `/home/phil/.local/share/autocoder/stage0/pilot-v5-01/summary.json`.
- Summary SHA-256: `84e35a3a5973dde943ca7cbb8b8a4236900ba26db675e2a244b34edd07403112`.
- Per-run manifests bind model/template/runtime and source hashes. Per-task folders contain traces, public checks, terminal candidate scores and diffs.
