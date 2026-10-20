# Stage 0 component evidence

All scores below are local screening observations on synthetic fixtures. They do
not establish statistical superiority or production safety. Original fixtures,
model settings, source fingerprints and thresholds remain in registrations v2/v3;
the strengthened execution policy and pilot are registered separately in v4.

## Runtime/context and thinking (P1A-01–02)

Model `qwen3.5:9b`, digest
`6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`,
Q4_K_M. Ollama server reports 0.40.5; the controller CLI reports client 0.17.4.
Host metrics describe the controller; `/api/ps` memory and allocations are endpoint
server self-reports, without independent backend GPU telemetry. See full manifests
for exact model template, license, package builds, CPU/GPU/OS and source hashes.

| Requested context | Thinking | Observed allocation | Server-reported VRAM bytes | Short result | Retrieval result | Retrieval input/output tokens | Retrieval seconds |
| ---: | --- | ---: | ---: | --- | --- | --- | ---: |
| 16384 | False | 16384 | 6047945194 | True | True | 1062/19 | 0.799 |
| 16384 | True | 16384 | 6047945194 | True | True | 1060/488 | 5.864 |
| 32768 | False | 32768 | 6618370538 | True | True | 2086/19 | 2.002 |
| 32768 | True | 32768 | 6618370538 | True | False | 2084/512 | 6.172 |
| 65536 | False | 65536 | 8111584705 | True | True | 4134/19 | 1.401 |
| 65536 | True | 65536 | 8111584705 | True | False | 4132/512 | 6.515 |

Actual retrieval prompts contain roughly 1K/2K/4K tokens, so these are allocation
and shallow retrieval probes, not full-window context-quality demonstrations.
Thinking used most or all of the fixed 512-token response allowance and exhausted
that per-request allowance for two retrieval probes. All thinking-off probes passed.
128K was optional and was not tested; no claim of its practicality is made.
Raw timing counters include cache effects; do not divide total cached+uncached
prompt tokens by uncached-only prefill duration and label that uncached throughput.

Measured endpoint timings for each retrieval request:

| Context | Thinking | Prompt/cache tokens | Prefill seconds | Uncached prefill tokens/s (zero-cache only) | Generation tokens/s |
| ---: | --- | --- | ---: | ---: | ---: |
| 16384 | False | 1062/0 | 0.2391 | 4441.3 | 92.9 |
| 16384 | True | 1060/1058 | 0.0456 | unverified | 89.4 |
| 32768 | False | 2086/0 | 0.4073 | 5121.6 | 93.1 |
| 32768 | True | 2084/2082 | 0.0423 | unverified | 89.2 |
| 65536 | False | 4134/0 | 0.7734 | 5345.4 | 91.0 |
| 65536 | True | 4132/4130 | 0.0427 | unverified | 88.3 |

These are endpoint counters, not independently instrumented hardware measurements.
Cached requests are excluded from the uncached-prefill rate column.

## Tool API and inventories (P1B-01–02)

| API | Tools | Trials | First schema+semantic pass | Pass by one recovery | Unrecovered |
| --- | ---: | ---: | ---: | ---: | ---: |
| native | 4 | 40 | 34 | 40 | 0 |
| native | 6 | 40 | 39 | 40 | 0 |
| native | 12 | 40 | 39 | 40 | 0 |
| openai | 4 | 40 | 40 | 40 | 0 |
| openai | 6 | 40 | 40 | 40 | 0 |
| openai | 12 | 40 | 40 | 40 | 0 |

The 40 registered prompts cover four operation classes and refusal of unauthorized
host-secret access. Indexed names vary, but scenario diversity is limited; repeated
cases are not independent broad real-project evidence. Twelve-tool inventories
include six explicitly synthetic distractors that are never executed.

## Phase-specific schemas and thinking/tool impact (P1B-03/P1A-02)

| Arm | Trials | Correct | Mean schema bytes | Mean response seconds | Mean output tokens | Mean cached prompt tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed | 8 | 8 | 2366.0 | 1.378 | 50.6 | 0.0 |
| per_phase | 8 | 8 | 673.4 | 0.745 | 51.9 | 0.0 |
| thinking | 8 | 8 | 2366.0 | 1.720 | 136.1 | 0.0 |

Measured schema-surface calibration on a constant prompt (includes template overhead):

| Tools | Prompt tokens |
| ---: | ---: |
| 0 | 17 |
| 4 | 547 |
| 6 | 692 |
| 12 | 974 |

Choose small phase-specific schemas for the initial loop: all eight selections
passed, with lower schema size and observed latency. The sample is small and
cache/order effects are visible; no statistically optimal policy is claimed.
Thinking also passed this eight-tool subset while spending more output tokens;
thinking-off is the initial bounded-task setting, not a universal recommendation.

## Typed handoffs (P1B-01/P1B-04)

- `native`: `VERIFIED_LOCAL`. Valid typed, revision-anchored plan and successful seeded recovery.
- `openai`: `FAILED_VERIFICATION`. Empty final content failed strict JSON decoding; failure retained.

Malformed handoff recovery is separately seeded and is not counted as first-try
model performance. Unit tests reject missing fields, stale revisions and unknown
paths, and stop after one failed recovery. Tool parsing is not a persistent blocker
in these tool-choice trials; the optional llama.cpp diagnostic is not triggered.
The pilot uses native Ollama structured output. The baseline proxy maps compatible
requests to native requests to enforce thinking/context settings consistently.

## Edit candidates (P1C-01–02)

| Format | Trials | First functional pass | Final clean, correct-target, functional pass | Final schema-valid envelopes |
| --- | ---: | ---: | ---: | ---: |
| exact | 30 | 18 | 30 | 30 |
| diff | 30 | 6 | 12 | 30 |
| symbol | 30 | 18 | 30 | 30 |

Thirty trials per format repeat five versioned scenarios six times: unique edits,
stale hashes, ambiguous text, multiline edits and wrong paths. Some first attempts
are deliberately supplied stale/path-invalid preconditions; first-pass counts must
be interpreted with that setup. Envelope schema validity does not establish valid
unified-diff syntax; Git validation errors are retained in each raw observation.

Choose **unique exact search/replace** initially. It matches symbol editing's final
success here without a separate language-server dependency. Enforce canonical paths,
raw source hashes and unique matches; reject stale/ambiguous requests and allow only
one grounded recovery. Stop rather than blindly retry or switch to unqualified
formats. These are small Python edit fixtures; Rust functional feasibility is tested
in the separately registered pilot, not inferred from Python symbol edits.

## Retrieval and optional repo map (P1C-03–04)

| Method | Trials | Correct relevant file/symbol | Mean startup seconds | Mean query seconds | Mean response bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| rg | 8 | 8 | 0.000 | 0.005 | 765.2 |
| serena | 8 | 8 | 1.116 | 0.204 | 171.0 |

Each retrieval fixture has one relevant symbol/file; correctness corresponds to
perfect observed recall/precision on that narrow setup. It is not a multi-file
retrieval-recall benchmark. Evidence includes exact source revisions and Serena
responses; cold startup and query costs are separate.

Aider's separate eight-file map probe retrieved 8/8 symbol names without any model
requests (see `repomap-01/result.json`). Its baseline retains the 1024-token map.
Defer implementing an additional map in our loop: these bounded fixtures fit in
explicit source evidence, and the map probe does not demonstrate a task-success
gain for a custom map implementation.

## Isolation, dependency preparation and framework choice (P1D/P1E)

All boundary probes passed after the administrator installed the executable-scoped
AppArmor policy. Test evidence covers actual host-sentinel reads, outside writes,
network isolation, hidden-oracle inaccessibility, protected-test tampering, hostile
install hooks, timeouts and output limits. Version 4 additionally enforces cgroup
memory/process limits; the process-count test proves the 64-task cap rejects excess
children. No host-execution fallback is provided. See `DEPENDENCY_PREPARATION.md`.

Serena is pinned to `d9e4c796fae0207ba6848d1df4b331122a5567b5`, version
2.0.1.dev0, in an independent `uv` environment. Its application license is
GPL-3.0-or-later; SolidLSP is MIT. Full tool inventory and licensing provenance are
recorded in the integration manifest; a small gateway allowlist is used by probes.

The optional MAF spike pins core 1.22.0, Ollama adapter 1.0.0b261015 and MCP 2.2.0
in a separate locked environment. Structured outputs and fresh standalone contexts
worked, but MCP initialization failed: explicit timeout handling mixed float and
timedelta types; removing that timeout exposed an incompatible `protocolVersion`
attribute expectation. Tool integration through MAF was not qualified. Retain both
failed artifacts, and **choose direct asyncio + Ollama + independent MCP** for v0.
The spike provides no demonstrated simplification of authorization, budgets,
worktrees or verification. No second application backend is being built.

Controlled TCP transport faults recorded connection refusal and deadline exhaustion,
then successful fresh inference without source modification or automatic replay.
This was fault injection on TCP endpoints, not proof of another remote machine.

## Reproducible artifact inventory

Raw evidence is outside the tracked repository. These hashes bind the report to
the exact final records; full manifests preserve exact source/package/model details.

| Artifact | SHA-256 |
| --- | --- |
| `/home/phil/.local/share/autocoder/stage0/runtime-v2-01/summary.json` | `05d010c67cc748ea47667ce9dc4f4899cf186ef2f78c333200b9cf644e92f444` |
| `/home/phil/.local/share/autocoder/stage0/tools-v2-01/summary.json` | `154c44c6e5cb550fcf0b3bc8eeb9f82e96546084ec9d4d397e6ea6381456e22f` |
| `/home/phil/.local/share/autocoder/stage0/edits-v3-01/summary.json` | `353ef843d22676dd4851ebce2a6b10a2d5e90a160340ec354c7998157bfa92d0` |
| `/home/phil/.local/share/autocoder/stage0/retrieval-v3-01/summary.json` | `df70134fddfb1397f66793b1cabf10728dc2cba5fbda331faad45f7f301de35f` |
| `/home/phil/.local/share/autocoder/stage0/handoffs-v3-01/summary.json` | `e4d27837ab5eebb575315663b3c2501aec9cb66970fc645d5264d2597254086d` |
| `/home/phil/.local/share/autocoder/stage0/cache-v3-01/summary.json` | `1bc43d726cf870ef10a8af7e11dc80e219ec272bafc1112d657c0ff1a2fe8e1c` |
| `/home/phil/.local/share/autocoder/stage0/transport-01/summary.json` | `f4b7a4ac3c80445e2058792b57c7816ca431800194514d0ab2a3fe965f46b83b` |
| `/home/phil/.local/share/autocoder/stage0/maf-spike-01/result.json` | `d45631289b07cb52d08647d101b25d99a8877106b02db750a6f8bdcc2a380b7a` |
| `/home/phil/.local/share/autocoder/stage0/maf-spike-02/result.json` | `efc2c168b68e4379ae1c857dcb92db721cb796135a5da0255814b9521b42305d` |
| `/home/phil/.local/share/autocoder/stage0/repomap-01/result.json` | `b413a9b232e4d7c4bc7c4e393d98f934033177aad98761e562c4b1442ddbf48d` |
| `/home/phil/.local/share/autocoder/stage0/aider-qualification-02/result.json` | `7a6df17a3cdf42ac76d845fdc41ee7f28336da5b371d5ad245e54ba65298ee92` |
| `/home/phil/.local/share/autocoder/stage0/opencode-qualification-02/result.json` | `9848c8e09f056c8ed18ac2220258f5d4a40600779cde47b691c83a4f6a7d8c04` |

## Reproduction and controller verification

Component source revisions: runtime/tools `49cb356db41b7a71bd5f275bcb8f6294d4a9dabe`;
remaining component adapters `d5f14acd2432c914aa78a25a45c0b457a7548b4b`;
qualified baseline/proxy `225510a894a5c7d1a86d2523d7545e6ded120071`.
Do not rerun old registrations against modified engines; their source checksums
intentionally reject that. Use an isolated checkout at the recorded revision.

For example, at the v3 source revision:

```sh
uv sync --locked
uv run python scripts/run_components.py --family edits \
  --registration benchmarks/v3 \
  --expected-sha256 94d3587be493e3571927286829fd5233397e066f8dc82e8e817def2f99053af4 \
  --output /tmp/autocoder-edits-reproduction
```

At correction revision `832f9fae6c39f99bac7c709b13ab2828f0edcbb7`,
`uv run ruff check .`, `uv run ruff format --check .` and the full
`uv run pytest` suite pass (42 tests). Frozen benchmark drivers are excluded from
formatting to preserve their registered bytes. Saved local suite log:
`/home/phil/.local/share/autocoder/stage0/verification-832f9fa.log`.
No CI job, hardware acceptance or owner acceptance is claimed.

The fresh sandbox probe is saved at
`/home/phil/.local/share/autocoder/stage0/sandbox-resume-01/result.json`;
all five checks pass. The independent v4 diff-path audit found zero paths outside
registered editable files, saved at `pilot-v4-01/scope-audit.json` under that root.
This audit supplements negative isolation tests; it does not prove absence of
all possible vulnerabilities.
