"""One confined, offline MCP process per task; stale indexes restart on source changes."""

import json
import math
import os
import selectors
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from autocoder.evaluator import rust_toolchain
from autocoder.protocol import digest
from autocoder.sandbox import argv
from autocoder.serena_probe import Serena
from autocoder.v0.journal import NeedsUser
from autocoder.v0.verification import directory_digest
from autocoder.v0.workspace import safe_file


class ConfinedClient(Serena):
    def __init__(self, root, runtime, name, deadline):
        self.root = root
        self._temporary = tempfile.TemporaryDirectory(prefix="autocoder-mcp-")
        self.home = Path(self._temporary.name)
        self.unit = "autocoder-navigation-" + uuid.uuid4().hex + ".scope"
        settings = {
            "projects": [],
            "ls_specific_settings": {
                "python": {
                    "ls_base_cmd": [
                        str(runtime / "bin/node"),
                        str(
                            runtime
                            / "lib/python3.12/site-packages/pyright/dist/langserver.index.js"
                        ),
                    ]
                },
                "rust": {"ls_path": "/rust/bin/rust-analyzer"},
            },
        }
        (self.home / "serena_config.yml").write_text(json.dumps(settings))
        command = [
            str(runtime / "bin/serena"),
            "start-mcp-server",
            "--project",
            "/work",
            "--context",
            "desktop-app",
            "--agent-interface",
            "tools",
            "--enable-web-dashboard",
            "false",
            "--enable-gui-log-window",
            "false",
            "--open-web-dashboard",
            "false",
            "--log-level",
            "WARNING",
            "--tool-timeout",
            "20",
        ]
        arguments = argv(root, command)
        cut = arguments.index("--")
        additions = [
            "--ro-bind",
            str(runtime),
            str(runtime),
            "--ro-bind",
            str(self.home),
            "/bootstrap",
            "--setenv",
            "SERENA_HOME",
            "/tmp/serena",
            "--setenv",
            "PYTHONDONTWRITEBYTECODE",
            "1",
            "--setenv",
            "RAYON_NUM_THREADS",
            "2",
            "--setenv",
            "TOKIO_WORKER_THREADS",
            "2",
            "--setenv",
            "PATH",
            str(runtime / "bin") + ":/rust/bin:/usr/bin:/bin",
        ]
        if any(path.suffix == ".rs" for path in root.rglob("*.rs")):
            additions += ["--ro-bind", str(rust_toolchain()), "/rust"]
        arguments[cut:cut] = additions
        # Copy only controller-authored settings to writable ephemeral application home.
        cut = arguments.index("--")
        launch = [
            "/usr/bin/python3",
            "-I",
            "-c",
            "import os,shutil; os.makedirs('/tmp/serena'); "
            "shutil.copyfile('/bootstrap/serena_config.yml','/tmp/serena/serena_config.yml'); "
            "os.execv(__import__('sys').argv[1],__import__('sys').argv[1:])",
            *command,
        ]
        arguments[cut + 1 :] = [
            "/usr/bin/prlimit",
            "--as=8589934592",
            "--cpu=60",
            "--fsize=8388608",
            "--nofile=256",
            "--",
            "/usr/bin/taskset",
            "--cpu-list",
            ",".join(map(str, sorted(os.sched_getaffinity(0))[:2])),
            *launch,
        ]
        self._stderr = (self.home / "stderr.log").open("wb")
        self.process = subprocess.Popen(
            [
                "systemd-run",
                "--user",
                "--scope",
                "--quiet",
                "--unit",
                self.unit,
                "--property=MemoryMax=2G",
                "--property=MemorySwapMax=0",
                "--property=TasksMax=64",
                f"--property=RuntimeMaxSec={math.ceil(deadline)}s",
                *arguments,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
            start_new_session=True,
            close_fds=True,
        )
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.buffer, self.sequence = bytearray(), 0
        self.started = time.monotonic()
        try:
            self.initialized = self.request(
                "initialize",
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "autocoder-v0", "version": "0.1.0"},
                },
                timeout=min(40, deadline),
            )
            self.notify("notifications/initialized", {})
            self.call("initial_instructions", {})
            config = self.call("get_current_config", {})
            text = content(config)
            if "Active project: " + name not in text:
                raise NeedsUser("Serena active project does not match the task mirror")
            self.startup_seconds = time.monotonic() - self.started
        except BaseException as error:
            self._stderr.flush()
            detail = (self.home / "stderr.log").read_text(errors="replace")[-4096:]
            self.close()
            raise RuntimeError(f"Confined navigation startup failed: {detail}") from error

    def call(self, name, arguments):
        if name not in {
            "initial_instructions",
            "get_current_config",
            "find_symbol",
            "find_referencing_symbols",
        }:
            raise ValueError("Navigation process exposes only scoped read operations")
        return self.request("tools/call", {"name": name, "arguments": arguments}, timeout=25)

    def close(self):
        try:
            if self.process.poll() is None:
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            subprocess.run(
                ["systemctl", "--user", "stop", self.unit], capture_output=True, timeout=5
            )
        finally:
            if self.process.poll() is None:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.process.wait(timeout=5)
            self.selector.close()
            self._stderr.close()
            self._temporary.cleanup()


def content(response):
    return "\n".join(
        item.get("text", "") for item in response.get("content", []) if item.get("type") == "text"
    )


class Navigation:
    def __init__(self, workspace, budget):
        self.workspace, self.project = workspace, workspace.project
        self.journal, self.budget = workspace.journal, budget
        self.client = None
        self.fingerprint = None
        self.temporary = None
        runtime = self.project.serena_runtime
        if runtime is None or not self.project.serena_runtime_sha256:
            raise NeedsUser("Serena requires a separately prepared, digest-pinned runtime")
        if directory_digest(runtime) != self.project.serena_runtime_sha256:
            raise NeedsUser("Serena runtime content digest changed")
        self.runtime = runtime.resolve()

    def ensure(self):
        self.workspace.assert_expected()
        state = {name: self.workspace.expected()[name] for name in self.project.readable_paths}
        fingerprint = digest(json.dumps(state, sort_keys=True).encode())
        if self.client and self.client.process.poll() is None and fingerprint == self.fingerprint:
            return
        self.close()
        self.temporary = tempfile.TemporaryDirectory(prefix="autocoder-navigation-source-")
        root = Path(self.temporary.name)
        for name in self.project.readable_paths:
            _, data = safe_file(self.workspace.root, name)
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        config = root / ".serena/project.yml"
        config.parent.mkdir()
        languages = []
        if any(n.endswith(".py") for n in state):
            languages.append("python")
        if any(n.endswith(".rs") for n in state):
            languages.append("rust")
        config.write_text(
            json.dumps({"project_name": self.journal.task_id, "languages": languages})
        )
        self.client = ConfinedClient(
            root, self.runtime, self.journal.task_id, self.budget.remaining_seconds
        )
        self.fingerprint = fingerprint
        self.journal.emit(
            "NAVIGATION_READY",
            data={
                "startup_seconds": self.client.startup_seconds,
                "source_fingerprint": fingerprint,
                "project_root": "/work",
                "pid": self.client.process.pid,
                "runtime_sha256": self.project.serena_runtime_sha256,
            },
        )

    def lookup(self, tool, path, symbol):
        self.ensure()
        if path not in self.project.readable_paths or len(symbol) > 200:
            raise ValueError("Unapproved navigation target")
        started = time.monotonic()
        if tool == "read_symbol":
            response = self.client.call(
                "find_symbol",
                {
                    "name_path_pattern": symbol,
                    "relative_path": path,
                    "include_body": False,
                    "max_answer_chars": 4096,
                },
            )
        else:
            response = self.client.call(
                "find_referencing_symbols",
                {"name_path": symbol, "relative_path": path, "max_answer_chars": 4096},
            )
        if response.get("isError"):
            self.journal.emit("NAVIGATION_ERROR", evidence_ref=self.journal.artifact(response))
            raise ValueError("Semantic navigation failed: " + content(response)[:512])
        raw = content(response)
        rows = json.loads(raw)
        # Response text is untrusted; expose only approved paths, locations and current hashes.
        locations = []

        def flatten(value, inherited=None):
            if isinstance(value, list):
                for item in value:
                    yield from flatten(item, inherited)
            elif isinstance(value, dict):
                name = value.get("relative_path", inherited)
                if "body_location" in value or "location" in value:
                    yield name, value
                else:
                    for key, item in value.items():
                        yield from flatten(
                            item, key if key in self.project.readable_paths else name
                        )

        for name, row in list(flatten(rows))[:20]:
            if name in self.project.readable_paths:
                _, data = safe_file(self.workspace.root, name)
                location = row.get("body_location", row.get("location", {}))
                count = len(data.decode().splitlines())
                valid = (
                    isinstance(location, dict)
                    and type(location.get("start_line")) is int
                    and type(location.get("end_line")) is int
                    and 0 <= location["start_line"] <= location["end_line"] < count
                )
                locations.append(
                    {
                        "path": name,
                        "sha256": digest(data),
                        "location": location if valid else {},
                        "location_validated": valid,
                    }
                )
        self.journal.emit(
            "NAVIGATION_QUERY",
            evidence_ref=self.journal.artifact(response),
            data={
                "seconds": time.monotonic() - started,
                "response_bytes": len(raw.encode()),
                "matches": len(locations),
            },
        )
        return {"method": "serena", "matches": locations, "source_fingerprint": self.fingerprint}

    def close(self):
        if self.client:
            self.client.close()
            self.client = None
        if self.temporary:
            self.temporary.cleanup()
            self.temporary = None
