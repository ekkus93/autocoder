"""Qualified offline execution with controller-selected read-only dependency mounts."""

import math
import os
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import PurePosixPath

from autocoder.execution import Execution, Sandbox
from autocoder.sandbox import argv


class TaskSandbox(Sandbox):
    def execute(
        self, worktree, command, *, timeout=30, input_text="", toolchain=None, readonly=None
    ):
        if timeout <= 0:
            raise ValueError("Positive check deadline required")
        arguments = argv(worktree, command)
        additions = []
        if toolchain:
            additions += ["--ro-bind", str(toolchain.resolve()), "/toolchain"]
        for target, source in (readonly or {}).items():
            if target not in {"/deps", "/artifacts"} or ".." in PurePosixPath(target).parts:
                raise ValueError("Unregistered dependency mount")
            additions += ["--ro-bind", str(source.resolve()), target]
        position = arguments.index("--")
        arguments[position:position] = additions
        position = arguments.index("--")
        arguments[position + 1 : position + 1] = [
            "/usr/bin/prlimit",
            "--as=2147483648",
            "--cpu=30",
            "--fsize=8388608",
            "--nofile=128",
            "--",
        ]
        unit = "autocoder-task-check-" + uuid.uuid4().hex + ".scope"
        arguments = [
            "systemd-run",
            "--user",
            "--scope",
            "--quiet",
            "--unit",
            unit,
            "--property=MemoryMax=2G",
            "--property=MemorySwapMax=0",
            "--property=TasksMax=64",
            f"--property=RuntimeMaxSec={math.ceil(timeout) + 2}s",
            *arguments,
        ]
        started = time.monotonic()
        status = "finished"
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
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            finally:
                subprocess.run(
                    ["systemctl", "--user", "stop", unit], capture_output=True, timeout=5
                )
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait(timeout=5)
            stdout.seek(0)
            stderr.seek(0)
            out, err = stdout.read(65537), stderr.read(65537)
        return Execution(
            status=status,
            exit_code=process.returncode,
            elapsed_seconds=time.monotonic() - started,
            stdout=out[:65536].decode(errors="replace"),
            stderr=err[:65536].decode(errors="replace"),
            truncated=len(out) > 65536 or len(err) > 65536,
        )
