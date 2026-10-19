"""Two native project processes sharing one real endpoint; no independent-server claim."""

import argparse
import json
import subprocess
from pathlib import Path

from autocoder.budget import Budget
from autocoder.fixtures import git
from autocoder.protocol import digest, write_json
from autocoder.v0.cli import journal_for
from autocoder.v0.gateway import ToolGateway
from autocoder.v0.schema import Check, Oracle, Project
from autocoder.v0.verification import directory_digest
from autocoder.v0.workspace import Workspace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    runtime_hash = directory_digest(args.runtime)
    public_python = (
        'import sys; sys.path.insert(0,"/work"); from greeting import greet; '
        'assert greet("Ada")=="Hello, Ada!", "greeting regression"'
    )
    rust_driver = """#[path="/work/src/lib.rs"] mod parity;
fn main() { assert!(parity::is_even(4), "parity regression");
assert!(!parity::is_even(-3), "parity regression"); }
"""
    public_rust = (
        "import pathlib,subprocess; "
        f'pathlib.Path("public.rs").write_text({rust_driver!r}); '
        'subprocess.run(["/toolchain/bin/rustc","--edition=2021","-C","linker=/usr/bin/cc",'
        '"public.rs","-o","/tmp/public"],check=True); '
        'subprocess.run(["/tmp/public"],check=True)'
    )
    projects = []
    for label in ("python", "rust"):
        repo = output / ("project-" + label)
        repo.mkdir()
        files = (
            {"greeting.py": 'def greet(name):\n    return "Hello!"\n'}
            if label == "python"
            else {
                "src/lib.rs": "pub fn is_even(value: i64) -> bool { value % 2 == 1 }\n",
                "Cargo.toml": '[package]\nname="project-parity"\nversion="0.1.0"\nedition="2021"\n',
            }
        )
        for name, source in files.items():
            path = repo / name
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_text(source)
        git(repo, "init", "--initial-branch=main")
        git(repo, "add", "--all")
        git(repo, "commit", "--no-gpg-sign", "-m", "Controlled v0 project base")
        private = output / (label + "-private.json")
        if label == "python":
            write_json(
                private,
                [
                    {"args": ["Mira"], "expected": "Hello, Mira!"},
                    {"args": [""], "expected": "Hello, !"},
                ],
            )
            checks = [
                Check(
                    name="regression",
                    command=["/usr/bin/python3", "-I", "-c", public_python],
                    regression_pattern="greeting regression",
                )
            ]
            oracle = Oracle(language="python", entry="greeting.greet", cases_file=private)
            request = 'Fix greet(name) to return "Hello, " + name + "!" for every string.'
        else:
            write_json(
                private,
                [
                    {"args": [-8], "expected": True},
                    {"args": [0], "expected": True},
                    {"args": [17], "expected": False},
                ],
            )
            driver = output / "private-driver.rs"
            driver.write_text(
                '#[path="/work/src/lib.rs"] mod parity;\nfn main(){ '
                "let value=std::env::args().nth(1).unwrap().parse::<i64>().unwrap(); "
                'println!("{{\\"value\\":{}}}",parity::is_even(value)); }\n'
            )
            checks = [
                Check(
                    name="regression",
                    language="rust",
                    command=["/usr/bin/python3", "-I", "-c", public_rust],
                    regression_pattern="parity regression",
                )
            ]
            oracle = Oracle(
                language="rust", entry="parity.is_even", cases_file=private, driver=driver
            )
            request = (
                "Fix is_even(value) to return true exactly when the integer is even, "
                "including negative numbers."
            )
        policy = Project(
            repository=repo,
            state_dir=output / ("state-" + label),
            readable_paths=list(files),
            editable_paths=[next(iter(files))],
            checks=checks,
            oracles=[oracle],
            serena=True,
            serena_runtime=args.runtime.resolve(),
            serena_runtime_sha256=runtime_hash,
            model_digest="6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7",
        )
        config = output / (label + "-project.json")
        write_json(config, policy.model_dump(mode="json"))
        task = output / (label + "-request.txt")
        task.write_text(request)
        log = (output / (label + "-events.jsonl")).open("w")
        process = subprocess.Popen(
            [
                "uv",
                "run",
                "autocoder-task",
                "--config",
                str(config),
                "start",
                "--request-file",
                str(task),
            ],
            cwd=root,
            stdout=log,
            stderr=subprocess.PIPE,
            text=True,
        )
        projects.append((label, policy, process, log))
    records = []
    intervals = []
    for label, policy, process, log in projects:
        _, stderr = process.communicate(timeout=650)
        log.close()
        lines = (output / (label + "-events.jsonl")).read_text().splitlines()
        result = json.loads(lines[-1]) if lines else {"status": "BLOCKED_ENVIRONMENT"}
        record = {
            "project": label,
            "pid": process.pid,
            "client_exit_code": process.returncode,
            "stderr": stderr[-4096:],
            "task": result,
            "original_checkout_clean": not git(policy.repository, "status", "--porcelain"),
        }
        if result.get("task_id"):
            journal = journal_for(policy, result["task_id"])
            rows = journal.read()
            record["navigation_pids"] = [
                r["data"]["pid"] for r in rows if r["kind"] == "NAVIGATION_READY"
            ]
            acquired = None
            for row in rows:
                if row["kind"] == "INFERENCE_ACQUIRED":
                    acquired = row["data"]["monotonic"]
                elif row["kind"] == "INFERENCE_RELEASED" and acquired is not None:
                    intervals.append((acquired, row["data"]["monotonic"], label))
                    acquired = None
        records.append(record)
    cross_blocked = False
    if all(r["task"].get("task_id") for r in records):
        pa, pb = projects[0][1], projects[1][1]
        ja = journal_for(pa, records[0]["task"]["task_id"])
        jb = journal_for(pb, records[1]["task"]["task_id"])
        wa, wb = Workspace(pa, ja), Workspace(pb, jb)
        with ja.lock():
            wa.restore()
            wb.restore()
            gateway = ToolGateway(wa, Budget(pa.limits), None)
            try:
                gateway.read(str(wb.root / "src/lib.rs"))
            except ValueError:
                cross_blocked = True
    intervals.sort()
    serialized = all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:], strict=False))
    write_json(
        output / "summary.json",
        {
            "scope": "two native processes, one shared real Ollama endpoint",
            "records": records,
            "inference_intervals": intervals,
            "inference_serialized": serialized,
            "cross_project_read_blocked": cross_blocked,
            "source_script_sha256": digest(Path(__file__).read_bytes()),
        },
    )
    print(
        json.dumps(
            {
                "outcomes": [r["task"]["status"] for r in records],
                "inference_serialized": serialized,
                "cross_project_read_blocked": cross_blocked,
            }
        )
    )


if __name__ == "__main__":
    main()
