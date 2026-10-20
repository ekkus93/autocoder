"""Native terminal client for the persistent task CLI and its JSONL event stream."""

import argparse
import curses
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from pathlib import Path

from autocoder.v0.cli import load_project

COMMANDS = {
    "start",
    "resume",
    "events",
    "status",
    "evidence",
    "diff",
    "cancel",
    "approve",
    "refuse",
}


def display_text(value):
    """Never send source/model escape sequences or bidi controls to the terminal."""
    return "".join(c if c.isprintable() else " " for c in str(value))


class CommandClient:
    """Bounded display buffer; the CLI's durable journal remains the source of truth."""

    def __init__(self, config):
        self.config = Path(config).resolve()
        self.lines = deque(maxlen=2000)
        self.lock = threading.Lock()
        self.thread = None
        self.process = None
        self.task_id = None
        self.phase = "PREFLIGHT"
        self.status = "IDLE"
        self.result = None
        self.returncode = None
        self.command = None

    @property
    def active(self):
        return self.thread is not None and self.thread.is_alive()

    def append(self, line):
        with self.lock:
            self.lines.append(display_text(line)[:4096])

    def snapshot(self):
        with self.lock:
            return list(self.lines)

    def consume(self, line):
        try:
            row = json.loads(line)
        except ValueError:
            self.append(line)
            return
        if not isinstance(row, dict):
            self.append(line)
            return
        if "event_id" in row:
            self.task_id = row.get("task_id", self.task_id)
            self.phase = row.get("phase", self.phase)
            self.status = row.get("status") or self.status
            data = row.get("data") or {}
            self.append(
                f"{row['event_id']} {self.phase} {row.get('kind')} "
                f"{data.get('tool', '')} {row.get('status') or ''} "
                f"evidence={row.get('evidence_ref') or '-'}"
            )
        else:
            self.result = row
            self.task_id = row.get("task_id", self.task_id)
            self.phase = row.get("phase", self.phase)
            self.status = row.get("status") or self.status
            for part in json.dumps(row, indent=2, ensure_ascii=True).splitlines():
                self.append(part)

    def launch(self, command, task_id=None, *, request=None, evidence_ref=None):
        if self.active:
            raise ValueError("This client already has an active command")
        if command not in COMMANDS:
            raise ValueError("Unsupported terminal action")
        if command != "start":
            if (
                not task_id
                or len(task_id) != 32
                or any(c not in "0123456789abcdef" for c in task_id)
            ):
                raise ValueError("Expected a generated 32-character task ID")
        elif not request or not request.strip() or len(request.encode()) > 8192:
            raise ValueError("Task request must contain one to 8192 bytes")
        if evidence_ref and (
            len(evidence_ref) != 64 or any(c not in "0123456789abcdef" for c in evidence_ref)
        ):
            raise ValueError("Expected an evidence SHA-256")
        self.command = command
        self.result = None
        self.returncode = None
        self.process = None
        self.task_id = task_id
        self.thread = threading.Thread(
            target=self._run, args=(command, task_id, request, evidence_ref), daemon=True
        )
        self.thread.start()

    def _run(self, command, task_id, request, evidence_ref):
        request_path = None
        try:
            argv = [sys.executable, "-m", "autocoder.v0.cli", "--config", str(self.config), command]
            if command == "start":
                fd, name = tempfile.mkstemp(prefix="autocoder-request-", suffix=".txt")
                request_path = Path(name)
                with os.fdopen(fd, "w") as handle:
                    handle.write(request)
                argv += ["--request-file", name]
            else:
                argv.append(task_id)
                if evidence_ref:
                    argv += ["--ref", evidence_ref]
                if command == "events":
                    argv.append("--follow")
            with subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            ) as process:
                self.process = process
                # Bounded readline also protects against a huge single diff/source line.
                while raw := process.stdout.readline(65537):
                    if len(raw) > 65536:
                        self.append("[oversized display line omitted; inspect task evidence]")
                        while raw and not raw.endswith(b"\n"):
                            raw = process.stdout.readline(65537)
                        continue
                    self.consume(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
                self.returncode = process.wait()
                self.append(f"[{command} exited {self.returncode}]")
        except (OSError, ValueError) as error:
            self.returncode = 2
            self.append(f"Command failed: {error}")
        finally:
            if request_path:
                request_path.unlink(missing_ok=True)

    def close(self):
        # Only stop an event reader here. Task controllers must finish/cancel first.
        if self.active and self.command != "events":
            raise ValueError("Stop the running task and wait for its outcome before quitting")
        if self.active:
            # The worker may still be between thread start and Popen.
            deadline = time.monotonic() + 2
            while self.process is None and self.active and time.monotonic() < deadline:
                time.sleep(0.01)
            if self.process and self.process.poll() is None:
                self.process.terminate()
            self.thread.join(timeout=3)
            if self.active and self.process:
                self.process.kill()
                self.thread.join(timeout=2)


class Terminal:
    def __init__(self, config, task_id=None):
        self.stream = CommandClient(config)
        self.action = CommandClient(config)
        self.task_id = task_id
        self.view = "events"
        self.offset = 0
        self.notice = "n: new task | o: open task | q: quit"
        self.prompt = None
        self.input = ""
        self.confirm = None
        if task_id:
            self.stream.launch("events", task_id)

    def ask(self, kind, label):
        self.prompt = kind
        self.input = ""
        self.notice = label + " (Enter submits, Esc cancels)"

    def submit(self):
        kind, text = self.prompt, self.input.strip()
        self.prompt = None
        if kind == "new":
            self.stream.launch("start", request=text)
            self.task_id = None
            self.view = "events"
        elif kind == "open":
            self.stream.close()
            self.stream = CommandClient(self.stream.config)
            self.stream.launch("events", text)
            self.task_id = text
            self.view = "events"
        elif kind == "evidence":
            self.action.launch("evidence", self.task_id, evidence_ref=text or None)
            self.view = "details"
        elif kind in {"approve", "refuse"}:
            if text != kind:
                self.notice = "Decision cancelled: confirmation did not match"
                return
            self.action.launch(kind, self.task_id)
            self.view = "details"
        self.notice = "Command submitted"
        self.offset = 0

    def key(self, key):
        if key == "\x03":
            self.notice = "Use x to request stop, then q after the task exits"
            return False
        if self.prompt:
            if key == "\x1b":
                self.prompt = None
                self.notice = "Input cancelled"
            elif key in {"\n", "\r", curses.KEY_ENTER}:
                self.submit()
            elif key in {"\b", "\x7f", curses.KEY_BACKSPACE}:
                self.input = self.input[:-1]
            elif isinstance(key, str) and key.isprintable() and len(self.input.encode()) < 8192:
                self.input += key
            return False
        if key == "q":
            if self.action.active:
                raise ValueError("Wait for the pending command before quitting")
            self.stream.close()
            return True
        if key in {"n", "o"} and self.action.active:
            raise ValueError("Wait for the pending command before switching tasks")
        if key == "n":
            if self.stream.active:
                raise ValueError("Finish or stop the current task before starting another")
            self.ask("new", "Task request")
        elif key == "o":
            if self.stream.active and self.stream.command != "events":
                raise ValueError("Finish or stop the current task before opening another")
            self.ask("open", "Task ID")
        elif key == "r":
            if self.stream.active:
                if self.stream.command != "events":
                    raise ValueError("Task is already running")
                self.stream.close()
            if self.action.active:
                raise ValueError("Wait for the pending command")
            self.stream.launch("resume", self.task_id)
            self.view = "events"
        elif key == "e":
            if self.action.active:
                raise ValueError("Wait for the pending command")
            self.ask("evidence", "Evidence SHA-256 (blank lists recent references)")
        elif key in {"s", "d", "x"}:
            command = {"s": "status", "d": "diff", "e": "status", "x": "cancel"}[key]
            if key == "d" and self.stream.active and self.stream.command != "events":
                raise ValueError("Diff is available after the task releases its worktree lock")
            if self.action.active:
                raise ValueError("Wait for the pending command")
            with self.action.lock:
                self.action.lines.clear()
            self.action.launch(command, self.task_id)
            self.view = "details"
            self.offset = 0
        elif key in {"a", "j"}:
            if self.stream.active and self.stream.command != "events":
                raise ValueError("Wait for the task's verification result before deciding")
            if self.action.active:
                raise ValueError("Wait for the pending command")
            kind = "approve" if key == "a" else "refuse"
            self.ask(kind, f"Record human decision for {self.task_id}; type {kind}")
        elif key == "v":
            self.view = "events"
            self.offset = 0
        elif key in {curses.KEY_UP, curses.KEY_PPAGE}:
            self.offset += 1 if key == curses.KEY_UP else 10
        elif key in {curses.KEY_DOWN, curses.KEY_NPAGE}:
            self.offset = max(0, self.offset - (1 if key == curses.KEY_DOWN else 10))
        return False

    def run(self, screen):
        curses.curs_set(0)
        screen.timeout(100)
        while True:
            self.task_id = self.stream.task_id or self.task_id
            height, width = screen.getmaxyx()
            screen.erase()
            title = (
                f"autocoder | {self.task_id or 'no task'} | "
                f"{self.stream.phase} | {self.stream.status}"
            )
            lines = (self.stream if self.view == "events" else self.action).snapshot()
            body_height = max(0, height - 5)
            self.offset = min(self.offset, max(0, len(lines) - body_height))
            end = max(0, len(lines) - self.offset)
            rows = [title, "events" if self.view == "events" else "diff / evidence / outcome"]
            rows += lines[max(0, end - body_height) : end]
            for index, row in enumerate(rows[: max(0, height - 3)]):
                self.write(screen, index, width, row)
            self.write(screen, height - 3, width, "n new  o open  s status  d diff  e evidence")
            self.write(
                screen, height - 2, width, "v events  x stop  r resume  a approve  j reject  q quit"
            )
            self.write(
                screen,
                height - 1,
                width,
                (self.notice + ": " + self.input) if self.prompt else self.notice,
            )
            screen.refresh()
            try:
                key = screen.get_wch()
            except curses.error:
                continue
            try:
                if self.key(key):
                    return
            except (OSError, ValueError) as error:
                self.notice = str(error)

    @staticmethod
    def write(screen, row, width, text):
        if row < 0 or width < 2:
            return
        try:
            screen.addnstr(row, 0, display_text(text), width - 1)
        except curses.error:
            pass  # Resize and wide Unicode glyphs can invalidate the last screen cell.


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--task-id", help="Attach to an existing task's event stream")
    args = parser.parse_args(argv)
    try:
        load_project(args.config)
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise ValueError(
                "The TUI requires an interactive terminal; use autocoder-task for JSONL"
            )

        # Ctrl-C is handled as a key, preserving the controller until explicit stop.
        def run(screen):
            curses.raw()
            terminal.run(screen)

        terminal = Terminal(args.config, args.task_id)
        curses.wrapper(run)
        return 0
    except (OSError, ValueError, curses.error) as error:
        print(f"autocoder-tui: {display_text(error)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
