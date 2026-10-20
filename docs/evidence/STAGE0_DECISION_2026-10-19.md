# Stage 0 decision packet

## Status

**GO: owner approved continuing the custom v0.** The owner explicitly replied
“Ok. Let’s do that.” after the recommendation to continue for compact contexts,
reliable recovery and verification. This authorizes v0 implementation, not human
acceptance of unbuilt capabilities or a claim of coding superiority. The reason for this checkpoint is `docs/TODO.md` P2-06's signed-off
Stage 0 decision and `docs/SPEC.md` §11.4(5)'s requirement for an actionable
baseline advantage or a clear unmet requirement.

## Evidence and frozen policy

| Gate | Observation | Assessment |
| --- | --- | --- |
| Isolation | Five host boundary probes pass; hostile hooks, oracle hiding and process caps tested; no unauthorized diff paths observed | Pass on tested local boundaries |
| Tool use | 240 registered trials; each API/inventory has 40/40 final successes by one recovery | Pass, limited scenario diversity |
| Edit primitive | Exact search/replace 30/30 final correct clean edits, versus diff 12/30 | Pass; select exact with hashes/unique matches |
| Pilot feasibility | Original loop 3/8; separately frozen correction 6/8 | V4 fails; v5 passes minimum 4/8 |
| Baseline value | V5 loop, Aider and OpenCode each complete 6/8 initially | No completion advantage; resource-efficiency signal requires judgment |
| Framework | MAF MCP spike fails; direct native Ollama plus independent MCP works | Do not select MAF |

See [component evidence](STAGE0_COMPONENTS_2026-10-19.md),
[v4 results](STAGE0_PILOT_V4_2026-10-19.md), and
[v5 results](STAGE0_PILOT_V5_2026-10-19.md).

The preselected repeats complete 6/6 for the loop, 6/6 for Aider, and 3/6 for
OpenCode. OpenCode repeatedly exhausts the Python configuration request budget.
All 42 v5 diffs stay within registered editable paths; audit artifact:
`/home/phil/.local/share/autocoder/stage0/pilot-v5-01/scope-audit.json`.

## What improved and what remains uncertain

V5 uses a flat edit tool and public functional reproduction/repair for every arm.
It keeps the original eight tasks, protected private oracles, budgets, thresholds
and repeat schedule. This is a new condition, not a revised score for v4.
The loop's initial completion count improves from three to six; the range task
regresses, and Rust multi-file configuration still fails compilation.

On the initial suite, mean reported input tokens are approximately 1,802 for the
loop, 2,823 for Aider and 9,738 for OpenCode. Mean execution time is 9.92, 16.79
and 11.87 seconds respectively. Planning increases the loop's output tokens.
These figures include failed tasks; the reports separately show tasks all arms
completed. Inventory preparation outside the task timer is excluded.

The observed compact contexts are a useful efficiency signal. Tiny synthetic
fixtures, different prompts, conservative byte reservations, client-internal retry
accounting and differing failure sets prevent treating that signal as general
coding superiority. No real-project advantage or unique unmet product requirement
has been demonstrated by this pilot. Further arbitrary tuning would expand this
finite feasibility exercise without resolving the product question.

## Decision requested

Is reduced reported token usage and this constrained workflow enough to justify
building the custom v0, or should the project adopt a corrected baseline? If a
specific capability is the reason to continue, identify it so v0 acceptance can
measure it. The current specification's numeric safety/feasibility thresholds
remain unchanged; an owner decision must not relabel failed runs or claim broader
acceptance.

If proceeding, the evidence supports a single deterministic loop, native Ollama
at 32K with thinking disabled, fresh typed phase handoffs, small per-phase tool
schemas, guarded exact edits, independent MCP/rg navigation, and fail-closed offline
checks. General dependency acquisition, durable production recovery, real-project
acceptance, multiple independent endpoints, and the TUI remain unimplemented.

## Verification

Controller correction: `832f9fae6c39f99bac7c709b13ab2828f0edcbb7`.
Frozen v5 digest:
`c04da250ab2f317ff8f4dabef3f18d91530e75811d6ed5a68f730e89ade87307`.
All 42 local tests pass; Ruff lint/format and whitespace checks pass. The sandbox
probe passes. CI, backend physical hardware acceptance and owner acceptance remain
unclaimed. `AGENTS.md` was left unchanged.

Review completed: 2026-10-19T21:39:48.581960+00:00.

## Owner decision recorded

2026-10-19T22:26:54.990289+00:00: Proceed with the custom v0 for smaller contexts and reliable recovery.
Keep the original benchmark outcomes and gates. Validate on real repositories
before claiming an advantage or v0 acceptance. Post-v0 integrations remain conditional.
