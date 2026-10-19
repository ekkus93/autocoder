"""Versioned, validated experiment records and benchmark change control."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    schema_version: Literal[1] = 1


class Limits(Record):
    wall_seconds: float = Field(default=300, gt=0)
    request_tokens: int = Field(default=24576, gt=0)
    output_tokens: int = Field(default=4096, gt=0)
    tool_calls: int = Field(default=20, gt=0)
    repairs: int = Field(default=1, ge=0)


class Usage(Record):
    elapsed_seconds: float = Field(default=0, ge=0)
    request_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    repairs: int = Field(default=0, ge=0)


class Result(Record):
    run_id: str
    utc_time: str
    experiment: str
    status: Literal[
        "VERIFIED_LOCAL", "FAILED_VERIFICATION", "BLOCKED_ENVIRONMENT", "BUDGET_EXHAUSTED"
    ]
    base_sha: str | None = None
    protocol_sha256: str
    manifest_sha256: str
    limits: Limits
    usage: Usage
    checks: dict[str, str]
    detail: str


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def write_json(path: Path, value: object) -> str:
    data = canonical(value)
    # Evidence must never silently replace an earlier record.
    with path.open("xb") as handle:
        handle.write(data)
    return digest(data)


def verify_protocol(root: Path, expected_lock: str | None = None) -> str:
    lock_bytes = (root / "freeze.json").read_bytes()
    lock_digest = digest(lock_bytes)
    if expected_lock is not None and lock_digest != expected_lock:
        raise ValueError("Frozen registration digest differs; register a new benchmark version")
    lock = json.loads(lock_bytes)
    if lock.get("version") != 1 or not lock.get("files"):
        raise ValueError("Unsupported or empty benchmark registration")
    actual_files = {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()} - {
        "freeze.json"
    }
    if actual_files != set(lock["files"]):
        raise ValueError("Benchmark inventory changed; register a new version")
    for name, expected in lock["files"].items():
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Unsafe registration path: {name}")
        if digest(path.read_bytes()) != expected:
            raise ValueError(f"Changed benchmark asset: {name}; register a new version")
    return lock_digest
