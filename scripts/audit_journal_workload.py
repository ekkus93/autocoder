"""Read-only replay measurements for explicitly selected existing task journals."""

import argparse
import json
import statistics
import time
from pathlib import Path

from autocoder.protocol import digest, utc_now
from autocoder.v0.journal import Journal


def measure(path):
    if path.is_symlink() or path.stat().st_size > 32_000_000:
        raise ValueError("Unsafe or oversized journal")
    raw = path.read_bytes()
    identity = json.loads(raw.splitlines()[0])
    journal = Journal(path.parent, identity["project_id"], identity["task_id"])
    timings = []
    for _ in range(7):
        started = time.perf_counter()
        rows = journal.read()
        timings.append((time.perf_counter() - started) * 1000)
    if path.read_bytes() != raw:
        raise ValueError("Journal changed during measurement")
    return {
        "journal": str(path),
        "sha256": digest(raw),
        "bytes": len(raw),
        "events": len(rows),
        "task_id": identity["task_id"],
        "median_replay_ms": statistics.median(timings),
        "max_replay_ms": max(timings),
        "last_event_hash": rows[-1]["event_hash"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {
        "recorded": utc_now(),
        "replays_per_journal": 7,
        "journals": [measure(path) for path in args.journal],
        "limitations": "Existing small local workload only; OS caches not cleared; no scale claim",
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
