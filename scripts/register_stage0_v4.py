"""Freeze the qualified end-to-end pilot before any of its scores are collected."""

import json
import shutil
import subprocess
from pathlib import Path

from autocoder.protocol import canonical, digest

ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT / "benchmarks/v4"
    shutil.copytree(ROOT / "benchmarks/v3", target)
    (target / "freeze.json").unlink()
    protocol = json.loads((target / "protocol.json").read_text())
    protocol.update(
        {
            "benchmark_version": "stage0-v4",
            "rationale": (
                "Freeze qualified baseline adapters and finite pilot. Preserve task prompts, "
                "oracles, thresholds and budgets. Strengthen confinement with cgroup limits. "
                "Use native Ollama for exact thinking/context control. The proxy translates "
                "compatible requests to native. OpenCode uses a short build prompt qualified "
                "on a separate unscored fixture."
            ),
        }
    )
    protocol["pilot_configuration"] = {
        "minimal": {
            "plan_output_cap": 512,
            "edit_output_cap": 1536,
            "max_repairs": 1,
            "edit_format": "unique exact search/replace",
            "handoffs": "fresh messages, typed Plan",
        },
        "baseline_output_cap_per_request": 2048,
        "oracle_feedback": "terminal only; no cases or expected answers guide repair",
        "public_repair": "at most one import/compile repair per task, shared task budget",
        "resource_policy": {
            "memory_bytes": 2147483648,
            "processes": 64,
            "check_network": "none",
            "baseline_network": "inference-only Unix proxy",
        },
        "scope": "Stage 0 fixture runner only, not the v0 application",
    }
    protocol["fairness_limitations"] = [
        (
            "All arms share model digest, 32K context, thinking off, "
            "temperature 0, seed 42 and task caps."
        ),
        (
            "Conservative byte-based input reservations may refuse a "
            "request before actual tokens exhaust the cap; report "
            "separately."
        ),
        (
            "Baseline proxy adapts streaming compatible requests to "
            "buffered native requests to enforce settings and usage."
        ),
        (
            "OpenCode has a shorter configured build prompt; shell, "
            "subagent, network and external-project tools are "
            "disabled."
        ),
        "Aider uses its diff search/replace format; its 1024-token repo map remains enabled.",
        (
            "Only public import/compilation diagnostics can guide "
            "one repair; held-out scoring is terminal for every arm."
        ),
        (
            "No candidate model gets oracle files or expected "
            "values. Tiny seeded fixtures do not establish "
            "superiority on real projects."
        ),
        (
            "The input upper-bound reservation scheme and different "
            "application prompts limit strict token-equivalence "
            "claims."
        ),
    ]
    tasks = json.loads((target / "tasks.json").read_text())
    schedule = []
    for round_index in range(4):
        selected = (
            tasks
            if round_index == 0
            else [task for task in tasks if task["id"] in protocol["repeat_task_ids"]]
        )
        for task_index, task in enumerate(selected):
            arms = list(protocol["arms"])
            offset = (task_index + round_index) % len(arms)
            for arm in arms[offset:] + arms[:offset]:
                schedule.append(
                    {
                        "id": f"r{round_index}-{task['id']}-{arm}",
                        "repeat_round": round_index,
                        "task_id": task["id"],
                        "arm": arm,
                    }
                )
    protocol["pilot_schedule"] = schedule
    (target / "protocol.json").write_bytes(canonical(protocol))
    engines = json.loads((target / "engine.json").read_text())
    for name in [
        *engines,
        "src/autocoder/pilot.py",
        "src/autocoder/model_proxy.py",
        "src/autocoder/baseline_probe.py",
        "scripts/run_pilot.py",
        "scripts/baseline_bridge.py",
        "experiments/aider/pyproject.toml",
        "experiments/aider/uv.lock",
    ]:
        engines[name] = digest((ROOT / name).read_bytes())
    opencode = Path(shutil.which("opencode")).resolve()
    bindings = {
        "opencode_path": str(opencode),
        "opencode_sha256": digest(opencode.read_bytes()),
        "opencode_version": subprocess.check_output(
            [str(opencode), "--version"], text=True
        ).strip(),
        "aider_version": "0.86.2",
        "aider_python": "/usr/bin/python3 (3.12.3)",
        "maf_decision": "Direct asyncio + Ollama + independent Serena MCP; MAF SDK spike failed",
    }
    (target / "baseline-bindings.json").write_bytes(canonical(bindings))
    integrations = json.loads((target / "integrations.json").read_text())
    integrations.pop("not_yet_installed", None)
    integrations["independent_baselines"] = bindings
    integrations["maf_spike"] = {
        "agent_framework_core": "1.22.0",
        "agent_framework_ollama": "1.0.0b261015",
        "mcp": "2.2.0",
        "decision": "reject for v0; SDK compatibility failures",
    }
    integrations["runtime_metric_domains"] = {
        "host": "controller host",
        "ollama_ps": "endpoint server self-report",
        "physical_backend_gpu_telemetry": "not independently available",
    }
    (target / "integrations.json").write_bytes(canonical(integrations))
    (target / "engine.json").write_bytes(canonical(engines))
    files = {
        str(path.relative_to(target)): digest(path.read_bytes())
        for path in sorted(target.rglob("*"))
        if path.is_file()
    }
    (target / "freeze.json").write_bytes(canonical({"version": 1, "files": files}))
    print(digest((target / "freeze.json").read_bytes()))


if __name__ == "__main__":
    main()
