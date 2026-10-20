"""Build a report from saved Stage 0 component artifacts without rerunning inference."""

# Wide Markdown tables are intentional in this report generator.
# ruff: noqa: E501

import json
import statistics
from pathlib import Path

from autocoder.protocol import digest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = Path.home() / ".local/share/autocoder/stage0"


def load(name):
    return json.loads((EVIDENCE / name / "summary.json").read_text())


def main():
    text = """# Stage 0 component evidence

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
"""
    for row in load("runtime-v2-01")["trials"]:
        trial = row["trial"]
        responses = row.get("responses", [])
        observed = row["residency"]["models"][0]
        retrieval = responses[-1]
        text += f"| {trial['num_ctx']} | {trial['think']} | {observed.get('context_length')} | {observed.get('size_vram')} | {responses[0]['correct']} | {retrieval['correct']} | {retrieval['prompt_tokens']}/{retrieval['output_tokens']} | {retrieval['elapsed_seconds']:.3f} |\n"
    text += """
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
"""
    for row in load("runtime-v2-01")["trials"]:
        raw = row["responses"][-1]["raw"]
        trial = row["trial"]
        cached = raw.get("prompt_eval_cached_count")
        duration = raw["prompt_eval_duration"] / 1e9
        prefill = f"{raw['prompt_eval_count'] / duration:.1f}" if cached == 0 else "unverified"
        generation = raw["eval_count"] / (raw["eval_duration"] / 1e9)
        text += f"| {trial['num_ctx']} | {trial['think']} | {raw['prompt_eval_count']}/{cached} | {duration:.4f} | {prefill} | {generation:.1f} |\n"
    text += """
These are endpoint counters, not independently instrumented hardware measurements.
Cached requests are excluded from the uncached-prefill rate column.

## Tool API and inventories (P1B-01–02)

| API | Tools | Trials | First schema+semantic pass | Pass by one recovery | Unrecovered |
| --- | ---: | ---: | ---: | ---: | ---: |
"""
    tools = load("tools-v2-01")["trials"]
    for api in ("native", "openai"):
        for count in (4, 6, 12):
            rows = [row for row in tools if row["api"] == api and row["inventory"] == count]
            first = sum(
                row["attempts"][0]["schema_valid"] and row["attempts"][0]["semantic_correct"]
                for row in rows
            )
            final = sum(row["status"] == "VERIFIED_LOCAL" for row in rows)
            text += f"| {api} | {count} | {len(rows)} | {first} | {final} | {len(rows) - final} |\n"
    text += """
The 40 registered prompts cover four operation classes and refusal of unauthorized
host-secret access. Indexed names vary, but scenario diversity is limited; repeated
cases are not independent broad real-project evidence. Twelve-tool inventories
include six explicitly synthetic distractors that are never executed.

## Phase-specific schemas and thinking/tool impact (P1B-03/P1A-02)

| Arm | Trials | Correct | Mean schema bytes | Mean response seconds | Mean output tokens | Mean cached prompt tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
"""
    cache = load("cache-v3-01")
    for arm in ("fixed", "per_phase", "thinking"):
        rows = [row for row in cache["trials"] if row["arm"] == arm]
        mean = statistics.mean
        cached = [
            row.get("response", {}).get("raw", {}).get("prompt_eval_cached_count", 0)
            for row in rows
        ]
        text += f"| {arm} | {len(rows)} | {sum(row['status'] == 'VERIFIED_LOCAL' for row in rows)} | {mean(row['schema_bytes'] for row in rows):.1f} | {mean(row['response']['elapsed_seconds'] for row in rows):.3f} | {mean(row['response']['output_tokens'] for row in rows):.1f} | {mean(cached):.1f} |\n"
    text += "\nMeasured schema-surface calibration on a constant prompt (includes template overhead):\n\n| Tools | Prompt tokens |\n| ---: | ---: |\n"
    for row in cache["schema_calibration"]:
        text += f"| {row['inventory']} | {row['response']['prompt_tokens']} |\n"
    text += """
Choose small phase-specific schemas for the initial loop: all eight selections
passed, with lower schema size and observed latency. The sample is small and
cache/order effects are visible; no statistically optimal policy is claimed.
Thinking also passed this eight-tool subset while spending more output tokens;
thinking-off is the initial bounded-task setting, not a universal recommendation.

## Typed handoffs (P1B-01/P1B-04)

"""
    for row in load("handoffs-v3-01")["trials"]:
        text += f"- `{row['api']}`: `{row['status']}`. "
        text += (
            "Valid typed, revision-anchored plan and successful seeded recovery.\n"
            if row["status"] == "VERIFIED_LOCAL"
            else "Empty final content failed strict JSON decoding; failure retained.\n"
        )
    text += """
Malformed handoff recovery is separately seeded and is not counted as first-try
model performance. Unit tests reject missing fields, stale revisions and unknown
paths, and stop after one failed recovery. Tool parsing is not a persistent blocker
in these tool-choice trials; the optional llama.cpp diagnostic is not triggered.
The pilot uses native Ollama structured output. The baseline proxy maps compatible
requests to native requests to enforce thinking/context settings consistently.

## Edit candidates (P1C-01–02)

| Format | Trials | First functional pass | Final clean, correct-target, functional pass | Final schema-valid envelopes |
| --- | ---: | ---: | ---: | ---: |
"""
    edits = load("edits-v3-01")["trials"]
    for method in ("exact", "diff", "symbol"):
        rows = [row for row in edits if row["method"] == method]
        first = sum(row["attempts"][0]["functional"] for row in rows)
        final = sum(
            row["attempts"][-1]["functional"]
            and row["attempts"][-1]["clean_apply"]
            and row["attempts"][-1]["correct_target"]
            for row in rows
        )
        valid = sum(row["attempts"][-1]["schema_valid"] for row in rows)
        text += f"| {method} | {len(rows)} | {first} | {final} | {valid} |\n"
    text += """
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
"""
    retrieval = load("retrieval-v3-01")["trials"]
    for method in ("rg", "serena"):
        records = [row[method] for row in retrieval]
        text += f"| {method} | {len(records)} | {sum(row['correct'] for row in records)} | {statistics.mean(row.get('startup_seconds', 0) for row in records):.3f} | {statistics.mean(row.get('query_seconds', row.get('seconds', 0)) for row in records):.3f} | {statistics.mean(row['bytes'] for row in records):.1f} |\n"
    text += """
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
"""
    names = (
        "runtime-v2-01",
        "tools-v2-01",
        "edits-v3-01",
        "retrieval-v3-01",
        "handoffs-v3-01",
        "cache-v3-01",
        "transport-01",
        "maf-spike-01",
        "maf-spike-02",
        "repomap-01",
        "aider-qualification-02",
        "opencode-qualification-02",
    )
    for name in names:
        folder = EVIDENCE / name
        final = folder / "summary.json"
        if not final.exists():
            final = folder / "result.json"
        text += f"| `{final}` | `{digest(final.read_bytes())}` |\n"
    (ROOT / "docs/evidence/STAGE0_COMPONENTS_2026-10-19.md").write_text(text)


if __name__ == "__main__":
    main()
