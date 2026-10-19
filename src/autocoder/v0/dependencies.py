"""Digest-pinned inert downloads and task-local offline installation/build hooks."""

import os
import shutil
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from autocoder.evaluator import rust_toolchain
from autocoder.execution import SandboxUnavailable
from autocoder.protocol import digest
from autocoder.v0.journal import NeedsUser, private_directory, sync_directory
from autocoder.v0.verification import directory_digest


class ArtifactCache:
    def __init__(self, root, budget, journal):
        self.root = private_directory(root)
        self.budget, self.journal = budget, journal

    def acquire(self, artifact):
        path = self.root / artifact.sha256
        if path.exists():
            if (
                path.is_symlink()
                or path.stat().st_size > artifact.max_bytes
                or digest(path.read_bytes()) != artifact.sha256
            ):
                raise NeedsUser("Dependency cache content changed")
            return path
        url = urlsplit(artifact.url)
        if (
            url.scheme not in {"https", "http"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or (url.scheme == "http" and url.hostname not in {"127.0.0.1", "localhost", "::1"})
        ):
            raise NeedsUser("Dependency acquisition requires HTTPS or a loopback test server")
        self.journal.emit(
            "DEPENDENCY_FETCH", data={"name": artifact.name, "sha256": artifact.sha256}
        )
        temporary = self.root / (".download-" + uuid.uuid4().hex)
        try:
            with httpx.Client(
                trust_env=False,
                follow_redirects=False,
                timeout=min(10, self.budget.remaining_seconds),
            ) as client:
                with client.stream("GET", artifact.url) as response:
                    response.raise_for_status()
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise ValueError("Encoded download responses are not accepted")
                    total = 0
                    fd = os.open(
                        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
                    )
                    with os.fdopen(fd, "wb") as handle:
                        for chunk in response.iter_raw(65536):
                            _ = self.budget.remaining_seconds
                            total += len(chunk)
                            if total > artifact.max_bytes:
                                raise ValueError("Dependency download exceeds registered byte cap")
                            handle.write(chunk)
                        handle.flush()
                        os.fsync(handle.fileno())
            if digest(temporary.read_bytes()) != artifact.sha256:
                raise ValueError("Dependency digest mismatch")
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.is_symlink() or digest(path.read_bytes()) != artifact.sha256:
                    raise NeedsUser("Concurrent dependency cache collision") from None
            sync_directory(self.root)
            return path
        finally:
            temporary.unlink(missing_ok=True)


def prepare(runner):
    project, journal = runner.workspace.project, runner.journal
    policy = project.preparation
    if policy is None:
        return None
    destination = journal.directory / "dependencies"
    ready = [r for r in journal.read() if r["kind"] == "DEPENDENCIES_READY"]
    pending = [r for r in journal.read() if r["kind"] == "DEPENDENCY_PUBLISH_INTENT"]
    if ready or (pending and destination.exists()):
        expected = (ready or pending)[-1]["data"]["sha256"]
        if destination.is_symlink() or directory_digest(destination) != expected:
            raise NeedsUser("Prepared dependency directory changed")
        if not ready:
            journal.emit("DEPENDENCIES_READY", status="reconciled", data={"sha256": expected})
        return destination
    if destination.exists():
        raise NeedsUser("Unrecorded prepared dependencies")
    cache = ArtifactCache(project.state_dir.resolve() / "artifacts", runner.budget, journal)
    with tempfile.TemporaryDirectory(prefix="autocoder-preparation-") as temporary:
        parent = Path(temporary)
        artifacts = parent / "artifacts"
        artifacts.mkdir()
        for artifact in policy.artifacts:
            shutil.copyfile(cache.acquire(artifact), artifacts / artifact.name)
        source = parent / "source"
        source.mkdir()
        runner.copy(source)
        output = source / ".autocoder-deps"
        if output.exists():
            raise NeedsUser("Preparation output collides with tracked source")
        journal.emit("PREPARATION_STARTED")
        execution = runner.sandbox.execute(
            source,
            policy.command,
            toolchain=rust_toolchain() if policy.language == "rust" else None,
            readonly={"/artifacts": artifacts},
            timeout=min(policy.timeout, runner.budget.remaining_seconds),
        )
        _ = runner.budget.remaining_seconds
        record = {
            "execution": execution.model_dump(),
            "integrity_changes": runner.integrity(source),
        }
        journal.emit(
            "PREPARATION_RESULT",
            evidence_ref=journal.artifact(record),
            status="pass"
            if execution.exit_code == 0 and not record["integrity_changes"]
            else "fail",
        )
        if (
            execution.exit_code != 0
            or execution.status != "finished"
            or execution.truncated
            or record["integrity_changes"]
        ):
            raise SandboxUnavailable("Offline dependency preparation failed; no host fallback")
        if not output.is_dir() or output.is_symlink():
            raise SandboxUnavailable("Preparation did not produce .autocoder-deps")
        # Reject special files, traversal links and oversized output before publishing it.
        total = 0
        count = 0
        for file in output.rglob("*"):
            _ = runner.budget.remaining_seconds
            count += 1
            if count > 10000:
                raise NeedsUser("Prepared dependency file-count cap exceeded")
            if file.is_symlink() or (not file.is_file() and not file.is_dir()):
                raise NeedsUser("Unsafe prepared dependency entry")
            if file.is_file():
                total += file.stat().st_size
                if file.stat().st_nlink != 1 or total > 256_000_000:
                    raise NeedsUser("Prepared dependencies exceed file/link limits")
        staging = journal.directory / (".dependencies-" + uuid.uuid4().hex)
        shutil.copytree(output, staging)
        for file in staging.rglob("*"):
            if file.is_file():
                with file.open("rb") as handle:
                    os.fsync(handle.fileno())
        for folder in sorted((p for p in staging.rglob("*") if p.is_dir()), reverse=True):
            sync_directory(folder)
        sync_directory(staging)
        fingerprint = directory_digest(staging)
        journal.emit("DEPENDENCY_PUBLISH_INTENT", data={"sha256": fingerprint})
        os.rename(staging, destination)
        sync_directory(journal.directory)
        journal.emit("DEPENDENCIES_READY", data={"sha256": fingerprint})
        return destination
