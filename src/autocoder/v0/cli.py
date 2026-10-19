"""Headless persistent tasks; integration remains an explicit user operation."""

import argparse
import asyncio
import json
import os
import re
import shlex
import sys
import time
import uuid
from pathlib import Path

from autocoder.protocol import digest
from autocoder.v0.coordinator import Coordinator
from autocoder.v0.journal import Journal, NeedsUser, private_directory, sync_directory
from autocoder.v0.schema import Outcome, Project
from autocoder.v0.workspace import Workspace, git


def load_project(path):
    if path.stat().st_size > 65536:
        raise ValueError("Project policy exceeds 64KB")
    return Project.model_validate_json(path.read_bytes())


def policy_binding(project):
    policy = project.model_dump(mode="json")
    assets = {}
    for oracle in project.oracles:
        for path in [oracle.cases_file, oracle.driver]:
            if path:
                assets[str(path)] = digest(path.read_bytes())
    return {"policy": policy, "private_asset_sha256": assets}


def directory(project, task_id):
    if not re.fullmatch(r"[a-f0-9]{32}", task_id):
        raise ValueError("Expected a generated task ID")
    state = private_directory(project.state_dir.resolve())
    projects = private_directory(state / "projects")
    owner = private_directory(projects / project.project_id)
    return owner / task_id


def journal_for(project, task_id, sink=None, *, create=False):
    path = directory(project, task_id)
    if not create and (not path.is_dir() or not (path / "events.jsonl").is_file()):
        raise NeedsUser("Unknown task for this project")
    return Journal(path, project.project_id, task_id, sink=sink)


def task_result(journal):
    events = journal.read()
    finals = [row for row in events if row["kind"] == "FINAL"]
    if finals and finals[-1] == events[-1]:
        return journal.load(finals[-1]["evidence_ref"])
    return {
        "task_id": journal.task_id,
        "status": "RUNNING",
        "phase": events[-1]["phase"] if events else "PREFLIGHT",
    }


def start(project, request, *, sink=None, transport=None, metadata=True):
    if not request.strip() or len(request.encode()) > 8192:
        raise ValueError("Task request must contain one to 8192 bytes")
    task_id = uuid.uuid4().hex
    journal = journal_for(project, task_id, sink, create=True)
    with journal.lock():
        ref = journal.artifact({"binding": policy_binding(project), "request": request})
        journal.emit("CREATED", status="PENDING", evidence_ref=ref)
        return asyncio.run(
            Coordinator(project, journal, transport=transport).run(request, metadata=metadata)
        )


def resume(project, task_id, *, sink=None, transport=None, metadata=True):
    journal = journal_for(project, task_id, sink)
    with journal.lock():
        rows = journal.read()
        original = journal.load(rows[0]["evidence_ref"])
        if original["binding"] != policy_binding(project):
            raise NeedsUser("Policy or private acceptance assets changed since task creation")
        status = task_result(journal)
        if status["status"] in {"VERIFIED_LOCAL", "INTEGRATED_BY_USER"}:
            return status
        marker = journal.directory / "cancel"
        if marker.exists():
            marker.unlink()
            sync_directory(journal.directory)
        return asyncio.run(
            Coordinator(project, journal, transport=transport).run(
                original["request"], resume=True, metadata=metadata
            )
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, required=True, help="Explicit reviewed JSON project policy"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    begin = commands.add_parser("start")
    begin.add_argument("--request-file", type=Path, required=True)
    for name in (
        "resume",
        "status",
        "diff",
        "events",
        "cancel",
        "approve",
        "refuse",
        "mark-integrated",
    ):
        command = commands.add_parser(name)
        command.add_argument("task_id")
        if name == "events":
            command.add_argument("--follow", action="store_true")
    args = parser.parse_args(argv)

    def sink(event):
        print(json.dumps(event), flush=True)

    try:
        project = load_project(args.config)
        if args.command == "start":
            result = start(project, args.request_file.read_text(), sink=sink)
        elif args.command == "resume":
            result = resume(project, args.task_id, sink=sink)
        else:
            journal = journal_for(project, args.task_id)
            if args.command == "events":
                cursor = 0
                while True:
                    rows = journal.read()
                    for row in rows[cursor:]:
                        sink(row)
                    cursor = len(rows)
                    if not args.follow or (rows and rows[-1]["kind"] == "FINAL"):
                        return 0
                    time.sleep(0.2)
            if args.command == "cancel":
                fd = os.open(
                    journal.directory / "cancel", os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600
                )
                os.fsync(fd)
                os.close(fd)
                sync_directory(journal.directory)
                result = {"task_id": args.task_id, "status": "CANCEL_REQUESTED"}
            elif args.command == "status":
                result = task_result(journal)
            else:
                with journal.lock():
                    workspace = Workspace(project, journal)
                    workspace.restore()
                    if args.command == "diff":
                        print(workspace.diff())
                        return 0
                    result = task_result(journal)
                    if args.command in {"approve", "refuse"}:
                        if result["status"] != "VERIFIED_LOCAL":
                            raise NeedsUser(
                                "Only independently verified local changes can be approved/refused"
                            )
                        result["acceptance"]["human_acceptance"] = (
                            "pass" if args.command == "approve" else "fail"
                        )
                        journal.emit("HUMAN_DECISION", status=args.command)
                        result["integration_command"] = (
                            f"git -C {shlex.quote(str(project.repository))} "
                            f"merge --ff-only {shlex.quote(workspace.branch)}"
                        )
                        result["integration_note"] = (
                            "Review and run manually; original checkout was not modified"
                        )
                    elif args.command == "mark-integrated":
                        if result.get("acceptance", {}).get("human_acceptance") != "pass":
                            raise NeedsUser(
                                "Approve the concrete verified change before recording integration"
                            )
                        git(
                            project.repository,
                            "merge-base",
                            "--is-ancestor",
                            result["task_commit"],
                            "HEAD",
                        )
                        result["status"] = str(Outcome.INTEGRATED_BY_USER)
                    journal.emit(
                        "FINAL", status=result["status"], evidence_ref=journal.artifact(result)
                    )
        print(json.dumps(result, sort_keys=True), flush=True)
        return (
            0
            if result["status"] in {"VERIFIED_LOCAL", "INTEGRATED_BY_USER", "CANCEL_REQUESTED"}
            else 2
        )
    except (ValueError, NeedsUser, OSError) as error:
        print(json.dumps({"status": "NEEDS_USER", "detail": str(error)[:1024]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
