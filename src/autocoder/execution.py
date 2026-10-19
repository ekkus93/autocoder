"""Bounded, offline Stage 0 execution in an independently probed bubblewrap policy."""

import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from autocoder.protocol import Record
from autocoder.sandbox import argv, probe


class SandboxUnavailable(RuntimeError):
    pass


class Execution(Record):
    status: str
    exit_code: int | None
    elapsed_seconds: float
    stdout: str
    stderr: str
    truncated: bool


class Sandbox:
    def __init__(self):
        self.qualification = probe()
        if self.qualification["status"] != "VERIFIED_LOCAL":
            raise SandboxUnavailable("Isolation probe failed; host execution is forbidden")

    def execute(
        self,
        worktree: Path,
        command: list[str],
        *,
        timeout: float = 30,
        input_text: str = "",
        toolchain: Path | None = None,
    ) -> Execution:
        if timeout <= 0:
            raise ValueError("Execution timeout must be positive")
        arguments = argv(worktree, command)
        # Bound address space, CPU and file growth inside the offline namespace.
        delimiter = arguments.index("--")
        additions = []
        if toolchain is not None:
            additions = ["--ro-bind", str(toolchain.resolve()), "/toolchain"]
        arguments[delimiter:delimiter] = additions
        delimiter = arguments.index("--")
        arguments[delimiter + 1 : delimiter + 1] = [
            "/usr/bin/prlimit",
            "--as=2147483648",
            "--cpu=30",
            "--fsize=8388608",
            "--nofile=128",
            "--",
        ]
        started = time.monotonic()
        status = "finished"
        # File-size limits bound output without unbounded communicate() buffering.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen(
                arguments,
                stdin=subprocess.PIPE,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
                close_fds=True,
            )
            try:
                process.communicate(input=input_text.encode(), timeout=timeout)
            except subprocess.TimeoutExpired:
                status = "timeout"
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            stdout.seek(0)
            stderr.seek(0)
            out = stdout.read(65537)
            err = stderr.read(65537)
        return Execution(
            status=status,
            exit_code=process.returncode,
            elapsed_seconds=time.monotonic() - started,
            stdout=out[:65536].decode(errors="replace"),
            stderr=err[:65536].decode(errors="replace"),
            truncated=len(out) > 65536 or len(err) > 65536,
        )
