"""Run the frozen Stage 0 suite sequentially, saving a result after every task."""

import argparse
import json
from pathlib import Path

from autocoder.experiments import append, verify_engines
from autocoder.pilot_v5 import run_task
from autocoder.protocol import Limits, digest, write_json
from autocoder.provenance import inventory, request_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registration", type=Path, default=Path("benchmarks/v5"))
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    registration = args.registration.resolve()
    protocol = verify_engines(root, registration, args.expected_sha256)
    bindings = json.loads((registration / "baseline-bindings.json").read_text())
    if digest(Path(bindings["opencode_path"]).read_bytes()) != bindings["opencode_sha256"]:
        raise ValueError("OpenCode binary differs from frozen baseline binding")
    models = request_json(args.endpoint, "/api/tags")["models"]
    if not any(
        model["name"] == protocol["reference_model"]
        and model["digest"] == protocol["reference_digest"]
        for model in models
    ):
        raise ValueError("Reference model digest changed")
    output = args.output.resolve()
    if output.is_relative_to(root):
        raise ValueError("Evidence must stay outside the checkout")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "registration.json", {"sha256": args.expected_sha256})
    tasks = {task["id"]: task for task in json.loads((registration / "tasks.json").read_text())}
    oracles = json.loads((registration / "oracles.json").read_text())
    results = []
    for entry in protocol["pilot_schedule"]:
        task = tasks[entry["task_id"]]
        destination = output / entry["id"]
        destination.mkdir()
        write_json(
            destination / "manifest.json",
            inventory(root, args.endpoint, protocol["reference_model"]),
        )
        write_json(destination / "registration.json", {"sha256": args.expected_sha256})
        result = run_task(
            entry["arm"],
            task,
            oracles[task["id"]],
            registration,
            args.endpoint,
            Limits(**protocol["limits"]),
            destination,
        )
        record = {"id": entry["id"], "repeat_round": entry["repeat_round"], **result}
        append(output / "results.jsonl", record)
        results.append(record)
        print(
            json.dumps({"id": entry["id"], "status": result["status"], "usage": result["usage"]}),
            flush=True,
        )
    write_json(
        output / "summary.json",
        {"schema_version": 1, "registration": args.expected_sha256, "results": results},
    )


if __name__ == "__main__":
    main()
