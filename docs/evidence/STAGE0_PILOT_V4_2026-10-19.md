# Stage 0 pilot: pilot-v4-01

Registration SHA-256: `8ffc72948d8684ddea2a38c80d5029f6b9a074087cba9d893d73f57672dd576e`.

Local synthetic screening results; no CI or owner acceptance is claimed.

## Initial eight tasks

| Task | Loop | Aider | OpenCode |
| --- | --- | --- | --- |
| py-clamp | FAILED_VERIFICATION | VERIFIED_LOCAL | VERIFIED_LOCAL |
| py-chunks | VERIFIED_LOCAL | VERIFIED_LOCAL | VERIFIED_LOCAL |
| py-dedupe | FAILED_VERIFICATION | VERIFIED_LOCAL | VERIFIED_LOCAL |
| py-config | VERIFIED_LOCAL | FAILED_VERIFICATION | VERIFIED_LOCAL |
| rs-clamp | FAILED_VERIFICATION | VERIFIED_LOCAL | VERIFIED_LOCAL |
| rs-divceil | FAILED_VERIFICATION | VERIFIED_LOCAL | VERIFIED_LOCAL |
| rs-ranges | VERIFIED_LOCAL | VERIFIED_LOCAL | VERIFIED_LOCAL |
| rs-config | FAILED_VERIFICATION | VERIFIED_LOCAL | BUDGET_EXHAUSTED |

## Aggregate metrics

All scheduled runs, including repeated tasks; means include failures.

| Arm | Initial pass | Repeat pass | Mean seconds | Mean input/output tokens |
| --- | ---: | ---: | ---: | ---: |
| minimal_loop | 3/8 | 3/6 | 10.65 | 1150/699 |
| aider | 7/8 | 1/6 | 28.22 | 3829/400 |
| optimized_opencode | 7/8 | 6/6 | 11.30 | 8788/499 |

## Shared successful initial tasks

Post-hoc descriptive subset: py-chunks, rs-ranges.
Excluded failures remain in all primary completion rates above.

| Arm | Mean seconds | Mean input/output tokens |
| --- | ---: | ---: |
| minimal_loop | 8.68 | 1304/620 |
| aider | 10.56 | 2111/200 |
| optimized_opencode | 7.83 | 7058/298 |

## Repeat stability

Preselected tasks, three additional rounds each.

| Task | Arm | Initial, repeat 1, repeat 2, repeat 3 |
| --- | --- | --- |
| py-config | minimal_loop | VERIFIED_LOCAL, VERIFIED_LOCAL, VERIFIED_LOCAL, VERIFIED_LOCAL |
| py-config | aider | FAILED_VERIFICATION, VERIFIED_LOCAL, FAILED_VERIFICATION, FAILED_VERIFICATION |
| py-config | optimized_opencode | VERIFIED_LOCAL, VERIFIED_LOCAL, VERIFIED_LOCAL, VERIFIED_LOCAL |
| rs-divceil | minimal_loop | FAILED_VERIFICATION, FAILED_VERIFICATION, FAILED_VERIFICATION, FAILED_VERIFICATION |
| rs-divceil | aider | VERIFIED_LOCAL, BUDGET_EXHAUSTED, BUDGET_EXHAUSTED, BUDGET_EXHAUSTED |
| rs-divceil | optimized_opencode | VERIFIED_LOCAL, VERIFIED_LOCAL, VERIFIED_LOCAL, VERIFIED_LOCAL |

## Task-level unrecovered outcomes

- `minimal_loop`: 8/14 unrecovered; {'FAILED_VERIFICATION': 8}.
- `aider`: 6/14 unrecovered; {'FAILED_VERIFICATION': 3, 'BUDGET_EXHAUSTED': 3}.
- `optimized_opencode`: 1/14 unrecovered; {'BUDGET_EXHAUSTED': 1}.

## Failure classification

Classification uses stored status/check artifacts; no model adjudication.

| Arm | Failure category | Runs |
| --- | --- | ---: |
| aider | resource budget | 3 |
| aider | terminal held-out functional failure | 3 |
| minimal_loop | public check or bounded repair failure | 2 |
| minimal_loop | terminal held-out functional failure | 6 |
| optimized_opencode | resource budget | 1 |

The loop's two Python failures contain invalid source after nested JSON edits and a failed public repair. Its Rust clamp uses reversed min/max logic; division overflow and boolean parsing errors survive compilation. Aider's Python configuration failures omit required missing-value behavior; its repeated Rust division runs exhaust the inference budget following edit-format recovery attempts. OpenCode's configuration failure is a budget refusal. These observations motivate the separately frozen v5 public reproducer and flat-edit condition; private cases are never fed back to an agent.

## Limits and interpretation

Private expected values stay outside candidate worktrees and model feedback. Public checks and terminal held-out checks have separate artifacts. Passing compilation or public checks alone cannot produce final acceptance.

Tasks are tiny seeded Python/Rust fixtures. Repeated deterministic prompts are correlated, not independent evidence of general coding reliability. Per-task hidden cases check target behavior, not broad real-project regression coverage. No controlled pilot ablation isolates context or cache effects; see the separate component report for those measurements.

All arms use the registered digest, 32K context, thinking disabled and the same task limits. Client prompts, edit protocols, tool accounting and startup overhead differ. The inference proxy translates compatible requests to native Ollama. The repairs counter bounds outer public-check retries. Client-internal edit-format retries consume time/tokens but do not increment that counter; Aider's text edit proposals also do not count as native tool calls. A conservative UTF-8 request-size reservation can refuse an invocation before actual reported input tokens reach the cap, especially for chatty clients. Budget failures remain failures. These limitations prevent a fair claim of general superiority from token or timing differences alone.

V4 checks public import/compilation; v5 adds shared public functional feedback and replaces the loop's nested edit payload with flat tool calls. They are different registered conditions, not interchangeable replicates.

## Evidence

- Completed runs: 42.
- Raw summary: `/home/phil/.local/share/autocoder/stage0/pilot-v4-01/summary.json`.
- Summary SHA-256: `5be3a333f2165b659cd26eb7ecc75eb61c88cca055822ceb07b7c38e1e6823b1`.
- Per-run manifests bind model/template/runtime and source hashes. Per-task folders contain traces, public checks, terminal candidate scores and diffs.
