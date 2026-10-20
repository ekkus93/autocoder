"""Register a correction after v4 fails: flat tools and public regression feedback."""

import json
import shutil
from pathlib import Path

from autocoder.protocol import canonical, digest

ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT / "benchmarks/v5"
    shutil.copytree(ROOT / "benchmarks/v4", target)
    (target / "freeze.json").unlink()
    # Public examples are derived from the task contract, with distinct inputs from hold-outs.
    public = {
        "py-clamp": [
            {"args": [8, -2, 6], "expected": 6},
            {"args": [0, -2, 6], "expected": 0},
            {"args": [1, 9, 2], "exception": "ValueError"},
        ],
        "py-chunks": [
            {"args": [[4, 5, 6], 2], "expected": [[4, 5], [6]]},
            {"args": [[2], -2], "exception": "ValueError"},
        ],
        "py-dedupe": [
            {"args": [[7, 3, 7, 5]], "expected": [7, 3, 5]},
            {"args": [[[4], [4], [5]]], "expected": [[4], [5]]},
        ],
        "py-config": [
            {"args": [{"enabled": " No "}], "expected": False},
            {"args": [{"enabled": "YEs"}], "expected": True},
            {"args": [{"enabled": "maybe"}], "exception": "ValueError"},
        ],
        "rs-clamp": [
            {"args": [8, -2, 6], "expected": 6},
            {"args": [0, -2, 6], "expected": 0},
            {"args": [1, 9, 2], "exception": "panic"},
        ],
        "rs-divceil": [
            {"args": [10, 4], "expected": 3},
            {"args": [18446744073709551614, 3], "expected": 6148914691236517205},
            {"args": [2, 0], "exception": "panic"},
        ],
        "rs-ranges": [
            {"args": [2, 6, 6], "expected": False},
            {"args": [2, 6, 2], "expected": True},
            {"args": [3, 3, 3], "expected": False},
        ],
        "rs-config": [
            {"args": [" YeS "], "expected": True},
            {"args": [" false ", "parser"], "expected": False},
            {"args": ["off"], "expected": None},
        ],
    }
    private = json.loads((target / "oracles.json").read_text())
    tasks = {task["id"]: task for task in json.loads((target / "tasks.json").read_text())}
    for name, cases in public.items():
        hidden = {
            (case.get("entry", tasks[name]["entry"]), json.dumps(case["args"], sort_keys=True))
            for case in private[name]["cases"]
        }
        if any(
            (case.get("entry", tasks[name]["entry"]), json.dumps(case["args"], sort_keys=True))
            in hidden
            for case in cases
        ):
            raise ValueError("Public regression duplicates a held-out input")
    (target / "public-checks.json").write_bytes(
        canonical({name: {"cases": cases} for name, cases in public.items()})
    )
    protocol = json.loads((target / "protocol.json").read_text())
    protocol["benchmark_version"] = "stage0-v5"
    protocol["rationale"] = (
        "V4's controller scored 3/8 on the initial pilot, below the 4/8 gate. "
        "Public diagnostics showed malformed source in nested JSON edit payloads and "
        "logical errors surviving import/compile-only checks. Keep original tasks, "
        "private oracles, budgets and thresholds. Replace the nested edit array with "
        "a flat apply_edit tool call per file. Give every arm the same public reproducer "
        "and at most one public functional repair. No private oracle feedback is allowed. "
        "This is a versioned corrective experiment, not a retrospective change to v4."
    )
    protocol["pilot_configuration"]["minimal"]["edit_response"] = (
        "native flat apply_edit per planned file"
    )
    protocol["pilot_configuration"]["public_repair"] = (
        "public functional regression, at most one shared-budget repair"
    )
    protocol["fairness_limitations"].append(
        "V5 gives public functional feedback to all arms; compare v4/v5 as different conditions."
    )
    (target / "protocol.json").write_bytes(canonical(protocol))
    engines = json.loads((target / "engine.json").read_text())
    for name in ["src/autocoder/pilot_v5.py", "scripts/run_pilot_v5.py"]:
        engines[name] = digest((ROOT / name).read_bytes())
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
