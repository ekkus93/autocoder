"""Fsynced append-only events and content-addressed evidence, with task locking."""

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path

from autocoder.protocol import canonical, digest, utc_now


class NeedsUser(RuntimeError):
    pass


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_directory(path):
    path = Path(path)
    # Reject links before resolve so a replaced task directory cannot redirect writes.
    if any(part.is_symlink() for part in [path, *path.parents]):
        raise NeedsUser("Symlink in application state path")
    existed = path.exists()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not existed:
        sync_directory(path.parent)
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise NeedsUser("Application state directory must be private (mode 0700)")
    return path


class Journal:
    def __init__(self, directory: Path, project_id: str, task_id: str, sink=None):
        self.directory = private_directory(directory)
        self.project_id, self.task_id = project_id, task_id
        self.path = directory / "events.jsonl"
        self.sink = sink
        self.phase = "PREFLIGHT"
        self.base_sha = None
        self.worktree_id = None

    @contextmanager
    def lock(self):
        fd = os.open(self.directory / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise NeedsUser("Task is locked by another process") from error
            yield self
        finally:
            os.close(fd)

    def read(self):
        if not self.path.exists():
            return []
        if self.path.is_symlink() or self.path.stat().st_size > 32_000_000:
            raise NeedsUser("Unsafe or oversized journal")
        raw = self.path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            raise NeedsUser("Torn journal tail; preserve evidence for manual reconciliation")
        previous = "0" * 64
        rows = []
        try:
            for line in raw.splitlines():
                row = json.loads(line)
                checksum = row.pop("event_hash")
                if (
                    row["event_id"] != len(rows) + 1
                    or row["previous_hash"] != previous
                    or row["project_id"] != self.project_id
                    or row["task_id"] != self.task_id
                    or digest(canonical(row)) != checksum
                ):
                    raise ValueError("Journal identity/hash mismatch")
                row["event_hash"] = checksum
                rows.append(row)
                previous = checksum
        except (ValueError, KeyError, TypeError) as error:
            raise NeedsUser("Invalid journal chain; refusing automatic repair") from error
        return rows

    def emit(
        self,
        kind,
        *,
        operation_id=None,
        expected=None,
        observed=None,
        status=None,
        evidence_ref=None,
        data=None,
    ):
        rows = self.read()
        event = {
            "event_version": 1,
            "event_id": len(rows) + 1,
            "utc_time": utc_now(),
            "project_id": self.project_id,
            "task_id": self.task_id,
            "phase": self.phase,
            "kind": kind,
            "operation_id": operation_id,
            "base_sha": self.base_sha,
            "worktree_id": self.worktree_id,
            "expected_hashes": expected or {},
            "observed_hashes": observed or {},
            "status": status,
            "evidence_ref": evidence_ref,
            "data": data or {},
            "previous_hash": rows[-1]["event_hash"] if rows else "0" * 64,
        }
        event["event_hash"] = digest(canonical(event))
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            data_bytes = json.dumps(event, sort_keys=True).encode() + b"\n"
            if os.write(fd, data_bytes) != len(data_bytes):
                raise NeedsUser("Short journal append")
            os.fsync(fd)
        finally:
            os.close(fd)
        sync_directory(self.directory)
        if self.sink:
            self.sink(event)
        return event

    def artifact(self, value):
        data = canonical(value)
        key = digest(data)
        folder = private_directory(self.directory / "evidence")
        path = folder / (key + ".json")
        if path.exists():
            if path.is_symlink() or digest(path.read_bytes()) != key:
                raise NeedsUser("Evidence content hash mismatch")
            return key
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            sync_directory(folder)
        return key

    def load(self, key):
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise NeedsUser("Invalid evidence reference")
        path = self.directory / "evidence" / (key + ".json")
        if path.is_symlink() or digest(path.read_bytes()) != key:
            raise NeedsUser("Evidence was changed")
        return json.loads(path.read_bytes())
