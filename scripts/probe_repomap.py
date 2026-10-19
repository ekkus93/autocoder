"""Measure Aider's map on a separate fixture; does not call the model."""

import argparse
from pathlib import Path

from autocoder.baseline_probe import run_baseline
from autocoder.budget import Budget
from autocoder.protocol import Limits, write_json
from autocoder.provenance import inventory


def main(output):
    root = Path(__file__).resolve().parents[1]
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "manifest.json", inventory(root, "http://127.0.0.1:11434", "qwen3.5:9b"))
    files = {
        f"module_{index}.py": f"def target_{index}():\n    return {index}\n" for index in range(8)
    }
    result = run_baseline(
        "aider",
        {"files": files, "protected": [], "prompt": "unused", "map_probe": 1024},
        "http://127.0.0.1:11434",
        Budget(Limits()),
        output,
    )
    result["retrieved_symbols"] = sum(f"target_{index}" in result["stdout"] for index in range(8))
    result["model_requests"] = (
        len((output / "proxy.jsonl").read_text().splitlines())
        if (output / "proxy.jsonl").exists()
        else 0
    )
    write_json(output / "result.json", result)
    print(
        {
            key: result[key]
            for key in ("exit_code", "retrieved_symbols", "model_requests", "seconds")
        }
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    main(parser.parse_args().output)
