"""Freeze edit, retrieval and typed-handoff adapters before their scored trials."""

import json
import shutil
from pathlib import Path

from autocoder.fixtures import Fixture
from autocoder.protocol import canonical, digest

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / "benchmarks/v3"
    shutil.copytree(ROOT / "benchmarks/v2", destination)
    (destination / "freeze.json").unlink()
    protocol = json.loads((destination / "protocol.json").read_text())
    protocol["benchmark_version"] = "stage0-v3"
    protocol["rationale"] = (
        "Freeze edit/retrieval/handoff/cache implementations after deterministic adapter tests. "
        "Preserve v2 task prompts, oracles, gates and budgets. Runtime observations justify "
        "thinking-off as the initial coding setting; thinking comparison remains measured."
    )
    protocol["component_arms"] = {
        "edits": ["exact", "diff", "symbol"],
        "retrieval": ["rg", "serena"],
        "cache": ["fixed-six", "per-phase-subset", "thinking-six"],
        "handoffs": ["native", "openai"],
        "cache_task_subset": list(range(8)),
        "edit_output_cap": 1024,
        "cache_output_cap": 512,
        "repairs": 1,
        "context": 32768,
        "temperature": 0,
        "seed": 42,
        "unattended_code_execution": "qualified offline bubblewrap only",
    }
    (destination / "protocol.json").write_bytes(canonical(protocol))
    files = {"bounds.py": "def clamp(value, lower, upper):\n    return min(value, lower)\n"}
    with Fixture(files) as fixture:
        evidence = {
            "base_sha": fixture.base_sha,
            "files": files,
            "task": "Fix inclusive clamping and reject reversed bounds",
        }
    (destination / "handoff_trial.json").write_bytes(canonical(evidence))
    engines = json.loads((destination / "engine.json").read_text())
    for name in [
        "src/autocoder/serena_probe.py",
        "src/autocoder/editing_probe.py",
        "src/autocoder/component_experiments.py",
        "src/autocoder/handoff_probe.py",
        "src/autocoder/additional_experiments.py",
        "scripts/run_components.py",
    ]:
        engines[name] = digest((ROOT / name).read_bytes())
    (destination / "engine.json").write_bytes(canonical(engines))
    files = {
        str(path.relative_to(destination)): digest(path.read_bytes())
        for path in sorted(destination.rglob("*"))
        if path.is_file()
    }
    (destination / "freeze.json").write_bytes(canonical({"version": 1, "files": files}))
    print(digest((destination / "freeze.json").read_bytes()))


if __name__ == "__main__":
    main()
