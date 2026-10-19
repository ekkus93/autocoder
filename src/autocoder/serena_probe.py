"""A bounded, worktree-pinned MCP client for the Serena feasibility experiments."""

import json
import os
import selectors
import signal
import subprocess
import tempfile
import time
from pathlib import Path

SOURCE = "git+https://github.com/oraios/serena.git@d9e4c796fae0207ba6848d1df4b331122a5567b5"


class Serena:
    def __init__(self, worktree: Path):
        self.root = worktree.resolve()
        self._temporary = tempfile.TemporaryDirectory(prefix="autocoder-serena-")
        self.home = Path(self._temporary.name)
        environment = dict(os.environ, SERENA_HOME=str(self.home))
        self._stderr = (self.home / "stderr.log").open("wb")
        self.process = subprocess.Popen(
            [
                "uv",
                "tool",
                "run",
                "--from",
                SOURCE,
                "serena",
                "start-mcp-server",
                "--project",
                str(self.root),
                "--context",
                "desktop-app",
                "--mode",
                "editing",
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
                "30",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
            env=environment,
            cwd=self.root,
            start_new_session=True,
            close_fds=True,
        )
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.buffer = bytearray()
        self.sequence = 0
        self.started = time.monotonic()
        try:
            self.initialized = self.request(
                "initialize",
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "autocoder-stage0", "version": "0.1.0"},
                },
                timeout=120,
            )
            self.notify("notifications/initialized", {})
            self.tools = self.request("tools/list", {})["tools"]
            self.startup_seconds = time.monotonic() - self.started
        except BaseException:
            self.close()
            raise

    def notify(self, method: str, params: dict):
        self.process.stdin.write(
            (json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n").encode()
        )
        self.process.stdin.flush()

    def request(self, method: str, params: dict, timeout: float = 40) -> dict:
        self.sequence += 1
        identifier = self.sequence
        self.process.stdin.write(
            (
                json.dumps({"jsonrpc": "2.0", "id": identifier, "method": method, "params": params})
                + "\n"
            ).encode()
        )
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if b"\n" not in self.buffer:
                if not self.selector.select(max(0, deadline - time.monotonic())):
                    break
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError("Serena MCP exited before response")
                self.buffer.extend(chunk)
                if len(self.buffer) > 1_000_000:
                    raise ValueError("Serena MCP response exceeds byte cap")
                continue
            line, _, remainder = self.buffer.partition(b"\n")
            self.buffer = bytearray(remainder)
            message = json.loads(line)
            if message.get("id") == identifier:
                if "error" in message:
                    raise RuntimeError(f"Serena MCP error: {message['error']}")
                return message["result"]
        raise TimeoutError("Serena MCP response deadline")

    def call(self, name: str, arguments: dict) -> dict:
        if name not in {
            "initial_instructions",
            "get_current_config",
            "find_symbol",
            "get_symbols_overview",
            "replace_symbol_body",
            "find_referencing_symbols",
        }:
            raise ValueError("Tool is outside the micro-experiment allowlist")
        # The model cannot access shell, project activation, or arbitrary MCP tools.
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait()
        self.selector.close()
        self._stderr.close()
        self._temporary.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
