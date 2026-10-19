"""Stage 0 edit candidates with common path/hash preconditions; no v0 coordinator."""

import os
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from autocoder.fixtures import Fixture, safe_relative
from autocoder.protocol import digest
from autocoder.serena_probe import Serena
from autocoder.tool_schema import Edit


class Patch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str
    expected_sha256: str
    patch: str


class SymbolEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str
    expected_sha256: str
    symbol: str
    body: str


FORMATS = {"exact": Edit, "diff": Patch, "symbol": SymbolEdit}


def target(fixture: Fixture, path: str, expected_sha256: str) -> tuple[Path, str]:
    relative = safe_relative(path)
    location = fixture.worktree / relative
    if location.is_symlink() or not location.resolve().is_relative_to(fixture.worktree.resolve()):
        raise ValueError("Outside-root path or symlink refused")
    if not location.is_file():
        raise ValueError("Target does not exist; inspect the provided file inventory")
    for parent in location.parents:
        if parent == fixture.worktree:
            break
        if parent.is_symlink():
            raise ValueError("Symlink ancestor refused")
    content = location.read_text()
    if "\x00" in content:
        raise ValueError("Binary edit refused")
    if digest(content.encode()) != expected_sha256:
        raise ValueError("Stale source hash; reread source and use the observed hash")
    return location, content


def apply(fixture: Fixture, method: str, payload: dict, serena: Serena | None = None) -> None:
    validated = FORMATS[method].model_validate(payload)
    location, content = target(fixture, validated.path, validated.expected_sha256)
    if validated.path != "module.py":
        raise ValueError("Only the registered target file is editable")
    if method == "exact":
        if not validated.old or content.count(validated.old) != 1:
            raise ValueError("Search text must match uniquely; include enclosing symbol context")
        replacement = content.replace(validated.old, validated.new, 1)
        descriptor, temporary = tempfile.mkstemp(prefix=".edit-", dir=location.parent)
        try:
            with os.fdopen(descriptor, "w") as handle:
                handle.write(replacement)
            if location.read_text() != content:
                raise ValueError("Source changed during edit")
            os.replace(temporary, location)
        finally:
            Path(temporary).unlink(missing_ok=True)
    elif method == "diff":
        patch = validated.patch
        if patch.count("--- ") != 1 or patch.count("+++ ") != 1:
            raise ValueError("Exactly one unified-diff file is allowed")
        if not patch.startswith("--- a/module.py\n+++ b/module.py\n"):
            raise ValueError("Patch headers must name only a/module.py and b/module.py")
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        }
        for check in (True, False):
            command = [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-C",
                str(fixture.worktree),
                "apply",
            ]
            if check:
                command += ["--check"]
            process = subprocess.run(
                command + ["--"],
                input=patch,
                text=True,
                capture_output=True,
                env=environment,
                timeout=5,
            )
            if process.returncode:
                raise ValueError("Unified diff rejected: " + process.stderr[:512])
    else:
        if serena is None or serena.root != fixture.worktree.resolve():
            raise ValueError("Serena must be pinned to this exact worktree")
        if validated.symbol != "value":
            raise ValueError("Only the registered symbol value is editable")
        result = serena.call(
            "replace_symbol_body",
            {
                "relative_path": validated.path,
                "name_path": validated.symbol,
                "body": validated.body,
            },
        )
        if result.get("isError"):
            raise ValueError("Serena rejected symbol edit")
    if location.read_text() == content:
        raise ValueError("Edit produced no source change")
