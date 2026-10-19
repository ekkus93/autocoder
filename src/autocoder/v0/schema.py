"""Explicit project policy and revision-anchored phase handoffs."""

import re
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from autocoder.protocol import Limits, digest


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Outcome(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    VERIFIED_LOCAL = "VERIFIED_LOCAL"
    FAILED_VERIFICATION = "FAILED_VERIFICATION"
    BLOCKED_ENVIRONMENT = "BLOCKED_ENVIRONMENT"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    NEEDS_USER = "NEEDS_USER"
    CANCELLED = "CANCELLED"
    INTEGRATED_BY_USER = "INTEGRATED_BY_USER"


class Phase(StrEnum):
    PREFLIGHT = "PREFLIGHT"
    ORIENT = "ORIENT"
    REPRODUCE_AND_PLAN = "REPRODUCE_AND_PLAN"
    IMPLEMENT = "IMPLEMENT"
    VERIFY = "VERIFY"
    REPAIR = "REPAIR"
    REPORT = "REPORT"


TRANSITIONS = {
    Phase.PREFLIGHT: {Phase.ORIENT},
    Phase.ORIENT: {Phase.REPRODUCE_AND_PLAN},
    Phase.REPRODUCE_AND_PLAN: {Phase.IMPLEMENT},
    Phase.IMPLEMENT: {Phase.VERIFY},
    Phase.VERIFY: {Phase.REPAIR, Phase.REPORT},
    Phase.REPAIR: {Phase.VERIFY},
    Phase.REPORT: set(),
}


def relative(name: str) -> str:
    if (
        not name
        or len(name) > 240
        or name.startswith("/")
        or any(part in {"", ".", "..", ".git"} for part in name.split("/"))
        or any(ord(c) < 32 for c in name)
        or "\\" in name
    ):
        raise ValueError("Expected a normalized relative project path")
    return name


def protected(name: str) -> bool:
    parts = name.lower().split("/")
    base = parts[-1]
    return (
        any(p in {"tests", "test", ".github", ".gitlab", ".serena"} for p in parts)
        or base.startswith(("test_", ".env"))
        or base.endswith(("_test.py", ".lock", ".pem", ".key"))
        or base
        in {
            "agents.md",
            "conftest.py",
            "pyproject.toml",
            "cargo.toml",
            "package.json",
            "setup.py",
            "setup.cfg",
            "tox.ini",
            "pytest.ini",
            "makefile",
            "justfile",
        }
    )


class Check(Strict):
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    command: list[str] = Field(min_length=1, max_length=32)
    kind: str = Field(default="tests", pattern=r"^(format|lint|compile|tests)$")
    timeout: float = Field(default=30, gt=0, le=120)
    language: str = Field(default="python", pattern=r"^(python|rust)$")
    # A reviewed runtime directory, not a candidate-controlled dependency cache.
    runtime: Path | None = None
    runtime_sha256: str | None = None
    regression_pattern: str | None = Field(default=None, max_length=256)


class Oracle(Strict):
    language: str = Field(pattern=r"^(python|rust)$")
    entry: str = Field(pattern=r"^[a-zA-Z_][\w.]*(?:\.[a-zA-Z_]\w*)?$")
    cases_file: Path
    # Trusted Rust driver accepts arguments and emits JSON; contains no expected values.
    driver: Path | None = None
    runtime: Path | None = None
    runtime_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class Project(Strict):
    repository: Path
    state_dir: Path
    endpoint: str = "http://127.0.0.1:11434"
    model: str = "qwen3.5:9b"
    model_digest: str | None = None
    context: int = Field(default=32768, ge=4096, le=65536)
    readable_paths: list[str] = Field(min_length=1, max_length=64)
    editable_paths: list[str] = Field(min_length=1, max_length=32)
    approved_test_paths: list[str] = Field(default_factory=list, max_length=16)
    checks: list[Check] = Field(min_length=1, max_length=12)
    oracles: list[Oracle] = Field(default_factory=list, max_length=4)
    serena: bool = False
    serena_runtime: Path | None = None
    serena_runtime_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    limits: Limits = Field(
        default_factory=lambda: Limits(
            wall_seconds=600, request_tokens=49152, output_tokens=8192, tool_calls=60, repairs=3
        )
    )
    phase_tool_calls: int = Field(default=20, ge=1, le=40)
    observation_bytes: int = Field(default=8192, ge=512, le=8192)

    @model_validator(mode="after")
    def policy(self):
        repo, state = self.repository.resolve(), self.state_dir.resolve()
        if not self.repository.is_absolute() or not self.state_dir.is_absolute():
            raise ValueError("Repository and state_dir must be absolute paths")
        if state.is_relative_to(repo) or repo.is_relative_to(state):
            raise ValueError("Keep task state separate from the source checkout")
        url = urlsplit(self.endpoint)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError("Use an HTTP(S) origin without embedded credentials")
        if not re.fullmatch(r"[a-zA-Z0-9._:/-]+", self.model):
            raise ValueError("Invalid model identifier")
        for name in self.readable_paths + self.editable_paths + self.approved_test_paths:
            relative(name)
        if not set(self.editable_paths) <= set(self.readable_paths):
            raise ValueError("Editable paths must also be readable")
        for name in self.editable_paths:
            if protected(name) and name not in self.approved_test_paths:
                raise ValueError(f"Explicit test/config approval required: {name}")
        if len({check.name for check in self.checks}) != len(self.checks):
            raise ValueError("Duplicate check name")
        for oracle in self.oracles:
            for path in [oracle.cases_file, oracle.driver]:
                if path is not None and (
                    not path.is_absolute() or path.resolve().is_relative_to(repo)
                ):
                    raise ValueError("Private acceptance assets must be outside the repository")
        return self

    @property
    def project_id(self):
        return digest(str(self.repository.resolve()).encode())[:24]

    def can_read(self, name):
        return relative(name) in self.readable_paths

    def can_edit(self, name):
        return relative(name) in self.editable_paths


class Finding(Strict):
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    start: int = Field(ge=1)
    end: int = Field(ge=1)
    summary: str = Field(max_length=500)


class Orientation(Strict):
    base_sha: str = Field(pattern=r"^[a-f0-9]{40}$")
    findings: list[Finding] = Field(min_length=1, max_length=12)


class Plan(Strict):
    base_sha: str = Field(pattern=r"^[a-f0-9]{40}$")
    paths: list[str] = Field(min_length=1, max_length=8)
    steps: list[str] = Field(min_length=1, max_length=5)
    checks: list[str] = Field(min_length=1, max_length=12)
