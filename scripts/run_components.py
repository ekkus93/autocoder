"""Run frozen component experiments without changing previously frozen v2 runners."""

import argparse
from pathlib import Path

from autocoder import additional_experiments, component_experiments
from autocoder.experiments import verify_engines
from autocoder.protocol import write_json
from autocoder.provenance import inventory, request_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--family", choices=["edits", "retrieval", "handoffs", "cache"], required=True
    )
    parser.add_argument("--registration", type=Path, default=Path("benchmarks/v3"))
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    registration = args.registration.resolve()
    protocol = verify_engines(root, registration, args.expected_sha256)
    model = protocol["reference_model"]
    tags = request_json(args.endpoint, "/api/tags")["models"]
    if not any(
        item["name"] == model and item["digest"] == protocol["reference_digest"] for item in tags
    ):
        raise ValueError("Model digest differs from frozen registration")
    output = args.output.resolve()
    if output.is_relative_to(root):
        raise ValueError("Keep raw evidence outside the checkout")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "manifest.json", inventory(root, args.endpoint, model))
    write_json(output / "registration.json", {"sha256": args.expected_sha256})
    runner = (
        additional_experiments if args.family in {"handoffs", "cache"} else component_experiments
    )
    runner.run(args.family, args.endpoint, model, registration, output)


if __name__ == "__main__":
    main()
