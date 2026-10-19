"""Measure real confined MCP startup, reuse, root validation and stale-index restart."""

import argparse
import json
import time
from pathlib import Path

from autocoder.budget import Budget
from autocoder.fixtures import Fixture
from autocoder.protocol import digest, write_json
from autocoder.tool_schema import Edit
from autocoder.v0.cli import journal_for
from autocoder.v0.navigation import Navigation
from autocoder.v0.schema import Check, Project
from autocoder.v0.verification import directory_digest
from autocoder.v0.workspace import Workspace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    runtime_hash = directory_digest(args.runtime)
    results = []
    fixtures = {
        "python": (
            "module.py",
            "def total(items):\n    return sum(items)\n\ndef report(items):\n"
            "    return total(items)\n",
        ),
        "rust": (
            "src/lib.rs",
            "pub fn total(a: i64, b: i64) -> i64 { a + b }\n"
            "pub fn report() -> i64 { total(1, 2) }\n",
        ),
    }
    for language, (name, source) in fixtures.items():
        record = {"language": language, "runtime_sha256": runtime_hash}
        files = {name: source}
        if language == "rust":
            files["Cargo.toml"] = '[package]\nname="nav-probe"\nversion="0.1.0"\nedition="2021"\n'
        with Fixture(files) as fixture:
            project = Project(
                repository=fixture.repository,
                state_dir=(args.output / language).resolve(),
                readable_paths=list(files),
                editable_paths=[name],
                checks=[Check(name="unused", command=["/usr/bin/true"])],
                serena=True,
                serena_runtime=args.runtime.resolve(),
                serena_runtime_sha256=runtime_hash,
            )
            journal = journal_for(project, "a" * 32, create=True)
            with journal.lock():
                journal.emit("CREATED")
                workspace = Workspace(project, journal)
                workspace.create()
                nav = Navigation(workspace, Budget(project.limits))
                try:
                    started = time.monotonic()
                    symbol = nav.lookup("read_symbol", name, "total")
                    record["cold_seconds"] = time.monotonic() - started
                    record["symbol"] = symbol
                    started = time.monotonic()
                    record["references"] = nav.lookup("find_references", name, "total")
                    record["warm_query_seconds"] = time.monotonic() - started
                    first_pid = nav.client.process.pid
                    with_error = False
                    try:
                        nav.client.call("execute_shell_command", {"command": "id"})
                    except ValueError:
                        with_error = True
                    record["unapproved_tool_blocked"] = with_error
                    workspace.edit(
                        Edit(
                            path=name,
                            old=source,
                            new=source.replace("total", "subtotal"),
                            expected_sha256=digest(source.encode()),
                        )
                    )
                    record["updated_symbol"] = nav.lookup("read_symbol", name, "subtotal")
                    record["restart_pid_changed"] = nav.client.process.pid != first_pid
                    record["status"] = (
                        "VERIFIED_LOCAL"
                        if (
                            symbol["matches"]
                            and record["updated_symbol"]["matches"]
                            and with_error
                            and record["restart_pid_changed"]
                        )
                        else "FAILED_VERIFICATION"
                    )
                except Exception as error:
                    record.update(status="BLOCKED_ENVIRONMENT", error=str(error)[-4096:])
                finally:
                    nav.close()
            results.append(record)
            print(json.dumps(record), flush=True)
    write_json(args.output / "summary.json", {"results": results})


if __name__ == "__main__":
    main()
