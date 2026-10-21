# Contract and checklist in the full loop

## Setup

The owner authorized taking the successful focused contract/checklist approach
into the autonomous loop. New task `3afe5b4688c343ffa81fd5c91bf9aa0c` uses
`~/.local/share/autocoder/trials/gateway-empty-read-qwen128k-v3/`.
Original buggy source is an isolated worktree at `36d35d8`; the controller is
unchanged at `e3b2c6d`. Main's reviewed gateway fix is preserved.

The request explicitly supplies the existing helper, a complete working setup
example, flat return-value structure, and C1–C5 case/field checklist. The successful
focused regression-test answer was **not** supplied. Earlier trial policies and
results remain unchanged. This is a revised exploratory prompt, not an identical
prompt comparison or a frozen benchmark.

Model remains installed `qwen35-128k:latest`, digest
`a14034a9a68498756f82d5697930cebacde180e0521b48b415238bb10d6ee4ed`.
Context 32,768; limits 600 seconds, 98,304 input tokens, 8,192 output tokens,
60 tools, 20 per phase and three repairs. No model download or larger budgets.
Existing behavior, unit, lint and format checks are unchanged. A fifth public
coverage gate independently alters each of 13 required result fields/ranges.
The gate was qualified before inference: it accepts the complete focused answer
and rejects the previous incomplete one. Its code, qualification logs and task
request/policy hashes were saved outside the candidate worktree before startup.

## Observed outcome

**BUDGET_EXHAUSTED**, detail `Model response incomplete or output allowance
exhausted`, during replan ORIENT. Usage: 104.96 seconds, 60,264 input tokens,
4,751 output tokens, 11 tools and two repairs. The final discovery response hit
its individual 768-token allowance. Aggregate input/output counters were below
their limits; this was not aggregate token or wall-time exhaustion.

The model used the fixture correctly and added a test covering C1–C4. Public unit
execution passed (two tests, 17 deselected), but the independent coverage gate
found all three C5/nonempty-helper field faults survived: **10/13 detected**.
The test omitted the helper read entirely. Lint also failed on a copied long
checklist comment; formatting passed.

The source edit fixed empty-file starts but deleted the existing nonempty EOF
start guard. It therefore introduced a regression: nonempty reads beginning past
the last line were accepted. Independent behavior verification correctly failed
`Preserve existing range validation`. A truncated implementation response was
discarded, candidate checks ran again, and unchanged diagnostics triggered the
bounded replan. Its truncated discovery response ended the task. No candidate
commit, acceptance, manual correction, merge or push occurred.

Diff artifact:
`5ad34655f4980655a3690f99ea5f97b1066ce08b41d96b16b6092bfba1423e8a`.
All candidate edits and check logs are preserved in external task state. Private
held-out, remote CI and human acceptance remain `not_run`. The main checkout's
production/test code is unchanged; documentation records this result.

## What this establishes

The explicit data contract and setup example were followed here. The complete
case checklist that worked in a focused test-writing call was only partially
followed while editing production code and tests through tools. The coverage gate
prevented passing unit execution from being mistaken for complete coverage, and
the independent behavior check caught a production regression.

This run does not establish autonomous completion or broad reliability. The
focused 13/13 result remains a separate result; it was not overwritten or counted
as a full-loop success. No extra attempt or controller retuning followed this run.
