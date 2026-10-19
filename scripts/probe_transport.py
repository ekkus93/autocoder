"""Audited endpoint failures and a fresh inference after failure; no source writes."""

import argparse
import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from autocoder.budget import Budget, BudgetExhausted
from autocoder.experiments import append
from autocoder.inference import InferenceError, infer
from autocoder.protocol import Limits, digest, write_json
from autocoder.provenance import inventory

ROOT = Path(__file__).resolve().parents[1]


class Stalled(BaseHTTPRequestHandler):
    def do_POST(self):
        time.sleep(1)

    def log_message(self, *_):
        pass


def hashes():
    return {
        str(path.relative_to(ROOT)): digest(path.read_bytes())
        for path in (ROOT / "src").rglob("*.py")
    }


async def main(output):
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "manifest.json", inventory(ROOT, "http://127.0.0.1:11434", "qwen3.5:9b"))
    before = hashes()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Stalled)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    records = []
    try:
        for name, endpoint, wall in (
            ("connection_refused", "http://127.0.0.1:1", 1),
            ("stalled_endpoint", f"http://127.0.0.1:{server.server_port}", 0.15),
            ("fresh_recovery", "http://127.0.0.1:11434", 30),
        ):
            budget = Budget(Limits(wall_seconds=wall))
            record = {"probe": name, "automatic_replays": 0}
            try:
                response = await infer(
                    endpoint,
                    "qwen3.5:9b",
                    [{"role": "user", "content": "Return JSON with answer 42."}],
                    budget,
                    context=32768,
                    schema={"type": "object"},
                    max_output=128,
                )
                record["status"] = (
                    "VERIFIED_LOCAL"
                    if json.loads(response["message"]["content"]) == {"answer": 42}
                    else "FAILED_VERIFICATION"
                )
                record["response"] = response
            except (BudgetExhausted, InferenceError) as error:
                record["status"] = (
                    "BUDGET_EXHAUSTED"
                    if isinstance(error, BudgetExhausted)
                    else "BLOCKED_ENVIRONMENT"
                )
                record["error"] = str(error)
            record["usage"] = budget.snapshot().model_dump()
            append(output / "events.jsonl", record)
            records.append(record)
    finally:
        server.shutdown()
        server.server_close()
    write_json(
        output / "summary.json",
        {
            "probes": records,
            "source_unchanged": before == hashes(),
            "scope": "controlled transport fault injection over TCP; no remote-machine claim",
        },
    )
    print(
        json.dumps(
            {"source_unchanged": before == hashes(), "outcomes": [r["status"] for r in records]}
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(main(parser.parse_args().output))
