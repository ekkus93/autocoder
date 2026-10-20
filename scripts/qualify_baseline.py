"""Unscored adapter qualification on a separate, fixed engineering fixture."""

import argparse
import json
from pathlib import Path

from autocoder.baseline_probe import run_baseline
from autocoder.budget import Budget
from autocoder.execution import Sandbox
from autocoder.protocol import Limits, write_json
from autocoder.provenance import inventory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=["aider", "opencode"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output.is_relative_to(root):
        raise ValueError("Evidence must be outside the checkout")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "manifest.json", inventory(root, "http://127.0.0.1:11434", "qwen3.5:9b"))
    task = {
        "files": {"lib.py": "def value():\n    return 7\n"},
        "protected": [],
        "prompt": "Fix value in lib.py to return the integer 8 instead of 7.",
    }
    result = run_baseline(args.arm, task, "http://127.0.0.1:11434", Budget(Limits()), output)
    check = Sandbox().execute(
        output / "candidate",
        [
            "/usr/bin/python3",
            "-I",
            "-c",
            'import sys,json;sys.path.insert(0,"/work");import lib;print(json.dumps(lib.value()))',
        ],
    )
    result["verification"] = check.model_dump()
    result["changed_correctly"] = check.exit_code == 0 and check.stdout.strip() == "8"
    result["scope"] = "Unscored baseline adapter qualification; not one of the eight pilot tasks"
    write_json(output / "result.json", result)
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("status", "exit_code", "proxy_error", "changed_correctly")
            }
        )
    )


if __name__ == "__main__":
    main()
