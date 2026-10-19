"""Summarize a completed frozen pilot without invoking models or changing scores."""

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

from autocoder.protocol import digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary_path = args.run / "summary.json"
    summary = json.loads(summary_path.read_text())
    rows = summary["results"]
    text = "# Stage 0 pilot: " + args.run.name + "\n\n"
    text += "Registration SHA-256: `" + summary["registration"] + "`.\n\n"
    text += "Local synthetic screening results; no CI or owner acceptance is claimed.\n\n"
    text += "## Initial eight tasks\n\n"
    arms = ["minimal_loop", "aider", "optimized_opencode"]
    text += "| Task | Loop | Aider | OpenCode |\n| --- | --- | --- | --- |\n"
    initial = [row for row in rows if row["repeat_round"] == 0]
    for task in dict.fromkeys(row["task_id"] for row in initial):
        outcomes = [
            next(row["status"] for row in initial if row["task_id"] == task and row["arm"] == arm)
            for arm in arms
        ]
        text += "| " + task + " | " + " | ".join(outcomes) + " |\n"
    text += "\n## Aggregate metrics\n\n"
    text += "All scheduled runs, including repeated tasks; means include failures.\n\n"
    text += "| Arm | Initial pass | Repeat pass | Mean seconds | Mean input/output tokens |\n"
    text += "| --- | ---: | ---: | ---: | ---: |\n"
    for arm in arms:
        selected = [row for row in rows if row["arm"] == arm]
        first = [row for row in selected if row["repeat_round"] == 0]
        repeats = [row for row in selected if row["repeat_round"] != 0]
        passed_first = sum(row["status"] == "VERIFIED_LOCAL" for row in first)
        passed_repeats = sum(row["status"] == "VERIFIED_LOCAL" for row in repeats)
        mean = statistics.mean
        seconds = mean(row["usage"]["elapsed_seconds"] for row in selected)
        inputs = mean(row["usage"]["request_tokens"] for row in selected)
        outputs = mean(row["usage"]["output_tokens"] for row in selected)
        text += (
            f"| {arm} | {passed_first}/{len(first)} | {passed_repeats}/{len(repeats)} | "
            f"{seconds:.2f} | {inputs:.0f}/{outputs:.0f} |\n"
        )
    text += "\n## Repeat stability\n\n"
    text += "Preselected tasks, three additional rounds each.\n\n"
    text += "| Task | Arm | Initial, repeat 1, repeat 2, repeat 3 |\n| --- | --- | --- |\n"
    for task in dict.fromkeys(row["task_id"] for row in rows if row["repeat_round"] != 0):
        for arm in arms:
            selected = sorted(
                (row for row in rows if row["task_id"] == task and row["arm"] == arm),
                key=lambda row: row["repeat_round"],
            )
            statuses = ", ".join(row["status"] for row in selected)
            text += f"| {task} | {arm} | {statuses} |\n"
    text += "\n## Task-level unrecovered outcomes\n\n"
    for arm in arms:
        selected = [row for row in rows if row["arm"] == arm]
        failures = Counter(row["status"] for row in selected if row["status"] != "VERIFIED_LOCAL")
        text += (
            f"- `{arm}`: {sum(failures.values())}/{len(selected)} unrecovered; {dict(failures)}.\n"
        )
    text += "\n## Failure classification\n\n"
    text += "Classification uses stored status/check artifacts; no model adjudication.\n\n"
    categories = Counter()
    for row in rows:
        if row["status"] == "VERIFIED_LOCAL":
            continue
        folder = args.run / row["id"]
        if row["status"] == "BUDGET_EXHAUSTED":
            category = "resource budget"
        elif (folder / "candidate-score.json").exists():
            category = "terminal held-out functional failure"
        elif "Public" in row.get("error", ""):
            category = "public check or bounded repair failure"
        else:
            category = "handoff, edit, or environment failure; inspect raw error"
        categories[(row["arm"], category)] += 1
    text += "| Arm | Failure category | Runs |\n| --- | --- | ---: |\n"
    for (arm, category), count in sorted(categories.items()):
        text += f"| {arm} | {category} | {count} |\n"
    if args.run.name.startswith("pilot-v4"):
        text += (
            "\nThe loop's two Python failures contain invalid source after nested JSON "
            "edits and a failed public repair. Its Rust clamp uses reversed min/max "
            "logic; division overflow and boolean parsing errors survive compilation. "
            "Aider's Python configuration failures omit required missing-value behavior; "
            "its repeated Rust division runs exhaust the inference budget following "
            "edit-format recovery attempts. OpenCode's configuration failure is a "
            "budget refusal. These observations motivate the separately frozen v5 "
            "public reproducer and flat-edit condition; private cases are never "
            "fed back to an agent.\n"
        )
    text += "\n## Limits and interpretation\n\n"
    text += (
        "Private expected values stay outside candidate worktrees and model feedback. "
        "Public checks and terminal held-out checks have separate artifacts. "
        "Passing compilation or public checks alone cannot produce final acceptance.\n\n"
        "Tasks are tiny seeded Python/Rust fixtures. Repeated deterministic prompts are "
        "correlated, not independent evidence of general coding reliability. "
        "Per-task hidden cases check target behavior, not broad real-project regression coverage. "
        "No controlled pilot ablation isolates context or cache effects; see the separate "
        "component report for those measurements.\n\n"
        "All arms use the registered digest, 32K context, thinking disabled and the same "
        "task limits. Client prompts, edit protocols, tool accounting and startup overhead "
        "differ. The inference proxy translates compatible requests to native Ollama. "
        "A conservative UTF-8 request-size reservation can refuse an invocation before "
        "actual reported input tokens reach the cap, especially for chatty clients. "
        "Budget failures remain failures. These limitations prevent a fair claim of "
        "general superiority from token or timing differences alone.\n\n"
        "V4 checks public import/compilation; v5 adds shared public functional feedback "
        "and replaces the loop's nested edit payload with flat tool calls. "
        "They are different registered conditions, not interchangeable replicates.\n"
    )
    if args.run.name.startswith("pilot-v5"):
        text += (
            "\nMetadata caveat: v5 inherits several v4 descriptions saying only public "
            "compilation feedback and no expected values. V5's explicit rationale, "
            "public_repair setting, public-checks.json and bound executable instead "
            "declare public functional cases. The no-exposure claim applies to private "
            "oracle values. This inherited descriptive inconsistency is retained in "
            "the immutable registration and disclosed here.\n"
        )
    text += "\n## Evidence\n\n"
    text += f"- Completed runs: {len(rows)}.\n"
    text += f"- Raw summary: `{summary_path}`.\n"
    text += f"- Summary SHA-256: `{digest(summary_path.read_bytes())}`.\n"
    text += (
        "- Per-run manifests bind model/template/runtime and source hashes. Per-task folders "
        "contain traces, public checks, terminal candidate scores and diffs.\n"
    )
    args.output.write_text(text)


if __name__ == "__main__":
    main()
