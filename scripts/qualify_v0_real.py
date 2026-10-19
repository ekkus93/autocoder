"""Run an actual repository policy bug through the live CLI without integrating its patch."""

import argparse
import json
import subprocess
from pathlib import Path

from autocoder.protocol import digest, write_json
from autocoder.v0.schema import Check, Oracle, Project
from autocoder.v0.verification import directory_digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-cases", type=Path, required=True)
    parser.add_argument("--task", choices=["rust-tests", "path-del"], default="rust-tests")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    runtime = root / ".venv/lib/python3.12/site-packages"
    runtime_hash = directory_digest(runtime)
    public = (
        'import sys; sys.path[:0]=["/work/src","/toolchain"]; '
        "from autocoder.v0.schema import protected; "
        'assert protected("src/codec_test.rs"), "rust test protection regression"; '
        'assert protected("src/tests.rs"), "rust test protection regression"; '
        'assert not protected("src/lib.rs"), "production source incorrectly protected"'
    )
    signature = "rust test protection regression"
    entry = "autocoder.v0.schema.protected"
    request_text = (
        "Fix autocoder.v0.schema.protected: Rust files named tests.rs or ending "
        "in _test.rs must require explicit test approval, even outside a tests directory. "
        "Preserve existing Python/config protection and keep ordinary Rust source editable. "
        "Only update src/autocoder/v0/schema.py. Run all configured checks."
    )
    if args.task == "path-del":
        signature = "DEL path regression"
        entry = "autocoder.v0.schema.relative"
        public = """
import sys
sys.path[:0]=['/work/src','/toolchain']
from autocoder.v0.schema import relative
try:
    relative('src/a'+chr(127)+'b.py')
except ValueError:
    pass
else:
    raise AssertionError('DEL path regression')
assert relative('src/module.py') == 'src/module.py'
"""
        request_text = (
            "Fix autocoder.v0.schema.relative so all ASCII control characters, including "
            "DEL (U+007F), are rejected in project paths. Preserve other path safety checks "
            "and valid Unicode file names. Only edit src/autocoder/v0/schema.py; "
            "run every named check."
        )
    private = output / "private-cases.json"
    cases_bytes = args.private_cases.read_bytes()
    write_json(private, json.loads(cases_bytes))
    write_json(
        output / "registration.json",
        {
            "fixture_version": 2 if args.task == "rust-tests" else 1,
            "task": args.task,
            "rationale": "Correct an acceptance expectation contradicting preserved base behavior; "
            "keep private case data outside the target repository and generator source.",
            "private_cases_sha256": digest(cases_bytes),
            "source_script_sha256": digest(Path(__file__).read_bytes()),
        },
    )
    policy = Project(
        repository=root,
        state_dir=output / "state",
        readable_paths=["src/autocoder/v0/schema.py"],
        editable_paths=["src/autocoder/v0/schema.py"],
        model_digest="6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7",
        checks=[
            Check(
                name="regression",
                command=["/usr/bin/python3", "-I", "-c", public],
                runtime=runtime,
                runtime_sha256=runtime_hash,
                regression_pattern=signature,
            ),
            Check(
                name="compile",
                kind="compile",
                command=[
                    "/usr/bin/python3",
                    "-I",
                    "-c",
                    "import ast,pathlib; "
                    'ast.parse(pathlib.Path("src/autocoder/v0/schema.py").read_text())',
                ],
            ),
        ],
        oracles=[
            Oracle(
                language="python",
                entry=entry,
                cases_file=private,
                runtime=runtime,
                runtime_sha256=runtime_hash,
            )
        ],
    )
    config = output / "project.json"
    write_json(config, policy.model_dump(mode="json"))
    request = output / "request.txt"
    request.write_text(request_text)
    before = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True)
    with (output / "events.jsonl").open("w") as events:
        result = subprocess.run(
            [
                "uv",
                "run",
                "autocoder-task",
                "--config",
                str(config),
                "start",
                "--request-file",
                str(request),
            ],
            cwd=root,
            stdout=events,
            stderr=subprocess.PIPE,
            text=True,
            timeout=650,
        )
    lines = (output / "events.jsonl").read_text().splitlines()
    final = json.loads(lines[-1]) if lines else {"status": "BLOCKED_ENVIRONMENT"}
    after = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True)
    write_json(
        output / "result.json",
        {
            "client_exit_code": result.returncode,
            "stderr": result.stderr[-4096:],
            "task": final,
            "original_status_unchanged": before == after,
            "event_log_sha256": digest((output / "events.jsonl").read_bytes()),
        },
    )
    print(
        json.dumps(
            {
                "status": final["status"],
                "task_id": final.get("task_id"),
                "original_status_unchanged": before == after,
            }
        )
    )


if __name__ == "__main__":
    main()
