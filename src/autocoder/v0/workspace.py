"""Retained branches, guarded atomic edits and reconciliation of durable intents."""

import os
import stat
import subprocess
import uuid
from pathlib import Path

from autocoder.protocol import digest
from autocoder.v0.integrity import preserve_inline_tests
from autocoder.v0.journal import NeedsUser, sync_directory
from autocoder.v0.schema import relative

GIT_OPTIONS = [
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.untrackedCache=false",
    "-c",
    "diff.external=",
    "-c",
    "core.attributesFile=/dev/null",
    "-c",
    "core.quotePath=false",
]


def git(root, *arguments, check=True):
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/nonexistent",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_AUTHOR_NAME": "Autocoder",
        "GIT_AUTHOR_EMAIL": "autocoder@localhost",
        "GIT_COMMITTER_NAME": "Autocoder",
        "GIT_COMMITTER_EMAIL": "autocoder@localhost",
    }
    return subprocess.run(
        ["/usr/bin/git", "--no-optional-locks", *GIT_OPTIONS, "-C", str(root), *arguments],
        env=env,
        capture_output=True,
        text=True,
        check=check,
        timeout=20,
    ).stdout.rstrip("\n")


def safe_file(root, name, *, maximum=262144, text=True):
    relative(name)
    target = root / name
    current = root
    for part in Path(name).parts:
        current = current / part
        if current.is_symlink():
            raise NeedsUser("Symlink in project path: " + name)
    if not target.resolve().is_relative_to(root.resolve()):
        raise NeedsUser("Project path escapes worktree")
    info = target.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > maximum or info.st_nlink != 1:
        raise NeedsUser("Expected bounded regular file with no hard links: " + name)
    data = target.read_bytes()
    if text and b"\x00" in data:
        raise NeedsUser("Binary source is not editable")
    return target, data


class Workspace:
    def __init__(self, project, journal):
        self.project, self.journal = project, journal
        self.root = journal.directory / "worktree"
        self.branch = "autocoder/task-" + journal.task_id
        self.repository = project.repository.resolve()
        self.base_sha = None

    def identity(self):
        if self.root.is_symlink() or not self.root.is_dir():
            raise NeedsUser("Task worktree missing or replaced")
        if Path(git(self.root, "rev-parse", "--show-toplevel")).resolve() != self.root:
            raise NeedsUser("Task root identity mismatch")
        common = Path(git(self.root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        original = Path(
            git(self.repository, "rev-parse", "--path-format=absolute", "--git-common-dir")
        )
        if common.resolve() != original.resolve():
            raise NeedsUser("Worktree belongs to another repository")
        if git(self.root, "symbolic-ref", "--short", "HEAD") != self.branch:
            raise NeedsUser("Worktree branch was changed")
        if git(self.root, "rev-parse", "HEAD") != self.base_sha:
            commits = [r for r in self.journal.read() if r["kind"] == "COMMIT_OUTCOME"]
            if not commits or commits[-1]["data"]["sha"] != git(self.root, "rev-parse", "HEAD"):
                raise NeedsUser("Unexpected task HEAD revision")

    def create(self):
        if Path(git(self.repository, "rev-parse", "--show-toplevel")).resolve() != self.repository:
            raise NeedsUser("Project must name its canonical Git root")
        # Repository-local checkout filters require an explicitly reviewed preparation policy.
        filters = git(
            self.repository, "config", "--local", "--get-regexp", r"^filter\.", check=False
        )
        if filters:
            raise NeedsUser("Repository checkout filters require a reviewed preparation policy")
        if self.root.exists():
            raise NeedsUser("Worktree path already exists")
        refs = git(
            self.repository, "for-each-ref", "--format=%(refname)", "refs/heads/" + self.branch
        )
        if refs:
            raise NeedsUser("Task branch collision")
        self.base_sha = git(self.repository, "rev-parse", "HEAD")
        self.journal.base_sha = self.base_sha
        self.journal.worktree_id = digest(str(self.root).encode())[:24]
        operation = uuid.uuid4().hex
        original_status = git(self.repository, "status", "--porcelain=v1", "--untracked-files=all")
        self.journal.emit(
            "WORKTREE_INTENT",
            operation_id=operation,
            data={
                "base": self.base_sha,
                "branch": self.branch,
                "original_status_sha256": digest(original_status.encode()),
            },
        )
        git(self.repository, "worktree", "add", "-b", self.branch, str(self.root), self.base_sha)
        self.identity()
        baseline = self.fingerprint()
        if not set(self.project.readable_paths) <= set(baseline):
            raise NeedsUser("All readable paths must be tracked regular files in the base revision")
        self.journal.emit(
            "WORKTREE_OUTCOME",
            operation_id=operation,
            evidence_ref=self.journal.artifact(baseline),
            observed=baseline,
            data={"file_modes": {n: (self.root / n).stat().st_mode & 0o777 for n in baseline}},
        )
        if original_status != git(
            self.repository, "status", "--porcelain=v1", "--untracked-files=all"
        ):
            raise NeedsUser("Original checkout changed during worktree preparation")

    def restore(self):
        events = self.journal.read()
        intents = [r for r in events if r["kind"] == "WORKTREE_INTENT"]
        if not intents:
            raise NeedsUser("No recorded worktree intent")
        self.base_sha = intents[0]["data"]["base"]
        self.journal.base_sha = self.base_sha
        self.journal.worktree_id = digest(str(self.root).encode())[:24]
        self.reconcile_commit()
        self.identity()
        if not any(r["kind"] == "WORKTREE_OUTCOME" for r in events):
            if git(self.root, "status", "--porcelain=v1", "--untracked-files=all"):
                raise NeedsUser("Ambiguous worktree creation has unrecorded changes")
            values = self.fingerprint()
            self.journal.emit(
                "WORKTREE_OUTCOME",
                operation_id=intents[0]["operation_id"],
                observed=values,
                evidence_ref=self.journal.artifact(values),
                status="reconciled",
            )
        self.reconcile()
        self.assert_expected()

    def tracked(self):
        names = git(self.root, "ls-files", "-z").split("\x00")
        names = [name for name in names if name]
        if len(names) > 10000:
            raise NeedsUser("Repository exceeds v0 file inventory cap")
        for name in names:
            relative(name)
        return names

    def fingerprint(self):
        values = {}
        total = 0
        for name in self.tracked():
            _, data = safe_file(self.root, name, maximum=8_000_000, text=False)
            total += len(data)
            if total > 100_000_000:
                raise NeedsUser("Repository exceeds v0 snapshot cap")
            values[name] = digest(data)
        return values

    def expected(self):
        values = {}
        for row in self.journal.read():
            if row["kind"] in {"WORKTREE_OUTCOME", "EDIT_OUTCOME"}:
                values.update(row["observed_hashes"])
        return values

    def assert_expected(self):
        self.identity()
        if self.fingerprint() != self.expected():
            raise NeedsUser("Worktree changed outside recorded operations")
        initial = [r for r in self.journal.read() if r["kind"] == "WORKTREE_OUTCOME"]
        if initial and any(
            (self.root / n).stat().st_mode & 0o777 != mode
            for n, mode in initial[0]["data"].get("file_modes", {}).items()
        ):
            raise NeedsUser("Worktree file permissions changed outside recorded operations")
        other = git(self.root, "ls-files", "--others", "--exclude-standard", "-z")
        # Do not hide arbitrary new files behind a model's success claim.
        unexpected = [n for n in other.split("\x00") if n]
        if unexpected:
            raise NeedsUser("Unexpected untracked task files: " + ", ".join(unexpected[:5]))

    def edit(self, edit, *, after_replace=None):
        self.assert_expected()
        if not self.project.can_edit(edit.path):
            raise NeedsUser("Path is not approved for edits")
        target, data = safe_file(self.root, edit.path)
        if digest(data) != edit.expected_sha256:
            raise ValueError("Stale edit hash; retrieve current source")
        source = data.decode("utf-8")
        if not edit.old or source.count(edit.old) != 1:
            raise ValueError("Edit requires exactly one nonempty match")
        replacement = source.replace(edit.old, edit.new, 1).encode()
        if edit.path not in self.project.approved_test_paths:
            preserve_inline_tests(source, replacement.decode())
        if len(replacement) > 262144 or b"\x00" in replacement:
            raise ValueError("Edited source exceeds text limit")
        if replacement == data:
            return {"path": edit.path, "sha256": digest(data), "changed": False}
        operation = uuid.uuid4().hex
        before, after = digest(data), digest(replacement)
        artifact = self.journal.artifact({"path": edit.path, "before": before, "after": after})
        self.journal.emit(
            "EDIT_INTENT",
            operation_id=operation,
            expected={edit.path: before},
            evidence_ref=artifact,
            data={"proposed_hashes": {edit.path: after}},
        )
        # Directory-relative descriptors prevent a swapped parent link from redirecting the write.
        parent = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        temporary = ".autocoder-" + operation
        try:
            for part in Path(edit.path).parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                os.close(parent)
                parent = child
            current = os.open(target.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                st = os.fstat(current)
                if st.st_nlink != 1 or digest(os.read(current, 262145)) != before:
                    raise NeedsUser("File changed before atomic edit")
            finally:
                os.close(current)
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                stat.S_IMODE(st.st_mode),
                dir_fd=parent,
            )
            with os.fdopen(fd, "wb") as handle:
                handle.write(replacement)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target.name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
            if after_replace:
                after_replace()
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
            os.close(parent)
        _, actual = safe_file(self.root, edit.path)
        if digest(actual) != after:
            raise NeedsUser("Atomic edit outcome does not match proposed content")
        self.journal.emit(
            "EDIT_OUTCOME",
            operation_id=operation,
            expected={edit.path: before},
            observed={edit.path: after},
        )
        return {"path": edit.path, "sha256": after, "changed": True}

    def reconcile(self):
        rows = self.journal.read()
        completed = {r["operation_id"] for r in rows if r["kind"] == "EDIT_OUTCOME"}
        for row in rows:
            if row["kind"] != "EDIT_INTENT" or row["operation_id"] in completed:
                continue
            name, before = next(iter(row["expected_hashes"].items()))
            _, data = safe_file(self.root, name)
            proposed = row["data"].get("proposed_hashes", row["observed_hashes"])
            actual, after = digest(data), proposed[name]
            if actual not in {before, after}:
                raise NeedsUser("Ambiguous edit changed by another writer; no replay performed")
            temporary = self.root / Path(name).parent / (".autocoder-" + row["operation_id"])
            if temporary.exists() or temporary.is_symlink():
                _, pending_data = safe_file(self.root, str(temporary.relative_to(self.root)))
                if digest(pending_data) != after:
                    raise NeedsUser("Pending edit temporary file was changed")
                temporary.unlink()
                sync_directory(temporary.parent)
            self.journal.emit(
                "EDIT_OUTCOME",
                operation_id=row["operation_id"],
                expected={name: before},
                observed={name: actual},
                status="reconciled_applied" if actual == after else "reconciled_not_applied",
            )

    def diff(self):
        return git(self.root, "diff", "--no-ext-diff", "--no-textconv", self.base_sha)

    def checkpoint(self):
        self.assert_expected()
        if not self.diff():
            return git(self.root, "rev-parse", "HEAD")
        operation = uuid.uuid4().hex
        parent = git(self.root, "rev-parse", "HEAD")
        expected = self.fingerprint()
        self.journal.emit(
            "COMMIT_INTENT",
            operation_id=operation,
            data={"parent": parent, "tree_hash": digest(str(sorted(expected.items())).encode())},
        )
        git(self.root, "add", "--", *self.project.editable_paths)
        git(
            self.root,
            "-c",
            "commit.gpgSign=false",
            "commit",
            "--no-gpg-sign",
            "-m",
            "Autocoder verified task " + self.journal.task_id,
        )
        sha = git(self.root, "rev-parse", "HEAD")
        if self.fingerprint() != expected:
            raise NeedsUser("Source changed during Git checkpoint; inspect pending commit")
        self.journal.emit("COMMIT_OUTCOME", operation_id=operation, data={"sha": sha})
        return sha

    def reconcile_commit(self):
        rows = self.journal.read()
        completed = {r["operation_id"] for r in rows if r["kind"] == "COMMIT_OUTCOME"}
        for row in rows:
            if row["kind"] != "COMMIT_INTENT" or row["operation_id"] in completed:
                continue
            current = git(self.root, "rev-parse", "HEAD")
            parent = row["data"]["parent"]
            if current == parent:
                continue  # No commit took place; later guarded checkpoint may commit once.
            actual_parent = git(self.root, "rev-parse", "HEAD^")
            tree_hash = digest(str(sorted(self.fingerprint().items())).encode())
            subject = git(self.root, "log", "-1", "--format=%s")
            if (
                actual_parent != parent
                or tree_hash != row["data"]["tree_hash"]
                or subject != "Autocoder verified task " + self.journal.task_id
                or git(self.root, "status", "--porcelain=v1", "--untracked-files=all")
            ):
                raise NeedsUser("Ambiguous Git commit outcome; no commit replay performed")
            self.journal.emit(
                "COMMIT_OUTCOME",
                operation_id=row["operation_id"],
                data={"sha": current},
                status="reconciled",
            )
