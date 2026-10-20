"""Owned, disposable Git fixtures; never reset or clean a user checkout."""

import os
import subprocess
import tempfile
from pathlib import Path, PurePosixPath


def git(root: Path, *args: str) -> str:
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(root),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_AUTHOR_NAME": "Autocoder Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@localhost",
        "GIT_COMMITTER_NAME": "Autocoder Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@localhost",
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
        "LC_ALL": "C",
    }
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *args],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    ).stdout.strip()


def safe_relative(name: str) -> Path:
    path = PurePosixPath(name)
    if not path.parts or path.is_absolute() or ".." in path.parts or ".git" in path.parts:
        raise ValueError(f"Unsafe fixture path: {name}")
    return Path(*path.parts)


class Fixture:
    def __init__(self, files: dict[str, str]):
        self._temporary = tempfile.TemporaryDirectory(prefix="autocoder-fixture-")
        self.root = Path(self._temporary.name)
        self.repository = self.root / "repository"
        self.worktree = self.root / "candidate"
        try:
            self.repository.mkdir()
            for name, content in files.items():
                target = self.repository / safe_relative(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            git(self.repository, "init", "--object-format=sha1", "--initial-branch=fixture")
            git(self.repository, "add", "--all")
            git(self.repository, "commit", "--no-gpg-sign", "-m", "Pinned fixture base")
            self.base_sha = git(self.repository, "rev-parse", "HEAD")
            git(self.repository, "worktree", "add", "--detach", str(self.worktree), self.base_sha)
        except BaseException:
            self.close()
            raise

    def diff(self) -> str:
        return git(self.worktree, "diff", "--no-ext-diff", "--no-textconv", self.base_sha)

    def protected_changes(self, protected: list[str]) -> list[str]:
        changed = []
        for name in protected:
            relative = safe_relative(name)
            original = self.repository / relative
            candidate = self.worktree / relative
            if (
                candidate.is_symlink()
                or not candidate.is_file()
                or original.read_bytes() != candidate.read_bytes()
            ):
                changed.append(name)
        # Flag new tests/configuration as well as modifications to registered paths.
        names = git(self.worktree, "ls-files", "--others", "--exclude-standard").splitlines()
        changed.extend(
            name
            for name in names
            if any(part in {"tests", ".github"} for part in Path(name).parts)
            or Path(name).name in {"conftest.py", "pyproject.toml", "Cargo.toml"}
        )
        return sorted(set(changed))

    def close(self) -> None:
        self._temporary.cleanup()

    def __enter__(self) -> "Fixture":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
