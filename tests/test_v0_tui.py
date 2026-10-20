import fcntl
import json
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time

import pytest

from autocoder.fixtures import Fixture
from autocoder.v0.cli import journal_for
from autocoder.v0.schema import Check, Project
from autocoder.v0.tui import CommandClient, Terminal, display_text
from autocoder.v0.workspace import Workspace


def test_prompt_utf8(tmp_path):
    """Test UTF-8 byte limit handling in Terminal.key.

    The TUI permits at most 8192 UTF-8 bytes in a prompt. Appending a
    multibyte character can exceed that limit. Accept printable characters
    only when the complete resulting input fits; reject an overflowing
    character without changing existing input. Preserve exactly-fitting
    ASCII and Unicode, backspace and Escape behavior.

    Test cases:
    - Rejected two-byte UTF-8 character at the limit
    - Rejected four-byte UTF-8 character at the limit
    - Exact fit with ASCII characters
    - Exact fit with multibyte characters
    - Backspace at the limit without launching subprocess
    """
    # Create a Terminal instance for testing
    terminal = Terminal(tmp_path / "unused-config.json")
    terminal.ask("new", "Task request")

    # Test 1: Rejected two-byte UTF-8 character (e.g., 'é' is 2 bytes)
    # Leave one byte free, then try to add a two-byte character.
    input_at_limit = "a" * 8191  # A two-byte character must not overshoot by one byte.
    terminal.input = input_at_limit

    # Try to add a 2-byte UTF-8 character (é) - should be rejected
    two_byte_char = "é"  # UTF-8: 0xC3 0xA9 = 2 bytes
    result = terminal.key(two_byte_char)
    assert result is False  # Should reject
    assert terminal.input == input_at_limit  # Input unchanged

    # Test 2: Rejected four-byte UTF-8 character (e.g., emoji '😀' is 4 bytes)
    terminal.input = "a" * 8190  # 8190 ASCII chars = 8190 bytes
    four_byte_char = "😀"  # UTF-8: 4 bytes
    result = terminal.key(four_byte_char)
    assert result is False  # Should reject
    assert terminal.input == "a" * 8190  # Input unchanged

    # Test 3: Exact fit with ASCII characters (should accept)
    terminal.input = "a" * 8191
    result = terminal.key("a")  # One key exactly fills the remaining byte.
    assert result is False
    assert terminal.input == "a" * 8192

    # Test 4: Exact fit with multibyte characters (should accept if total <= 8192)
    terminal.input = ""
    # Add 4096 two-byte chars (é) = 8192 bytes exactly
    for _ in range(4096):
        result = terminal.key("é")
        assert result is False
    assert len(terminal.input.encode()) == 8192

    # Test 5: Backspace at the limit (should work)
    terminal.input = "a" * 8192
    result = terminal.key("\b")
    assert result is False
    assert terminal.input == "a" * 8191

    # Test 6: Escape at the limit (should clear prompt)
    terminal.prompt = "test"
    result = terminal.key("\x1b")
    assert result is False
    assert terminal.prompt is None
    assert terminal.notice == "Input cancelled"


def test_report_phase(tmp_path):
    """Test that report phase is preserved correctly in non-event reports."""
    with Fixture({"module.py": "VALUE = 1\n"}) as fixture:
        config, journal, evidence = setup_task(tmp_path, fixture.repository)
        client = CommandClient(config)

        # Initial report with phase
        initial_report = json.dumps(
            {
                "task_id": "b" * 32,
                "phase": "INIT",
                "status": "running",
                "data": {"tool": "init"},
                "evidence_ref": None,
            }
        )
        client.consume(initial_report)
        assert client.phase == "INIT"
        assert client.status == "running"

        # Missing-phase report should preserve previous phase
        missing_phase = json.dumps(
            {
                "task_id": "b" * 32,
                "status": "running",
                "data": {"tool": "update"},
                "evidence_ref": None,
            }
        )
        client.consume(missing_phase)
        assert client.phase == "INIT", f"Phase should be preserved: {client.phase}"

        # Event report updates phase
        event_report = json.dumps(
            {
                "event_id": "evt1",
                "task_id": "b" * 32,
                "phase": "CHECK",
                "kind": "CHECK",
                "status": "pass",
                "data": {"tool": "check"},
                "evidence_ref": None,
            }
        )
        client.consume(event_report)
        assert client.phase == "CHECK"

        # Another non-event report should preserve phase
        another_non_event = json.dumps(
            {
                "task_id": "b" * 32,
                "status": "running",
                "data": {"tool": "more"},
                "evidence_ref": None,
            }
        )
        client.consume(another_non_event)
        assert client.phase == "CHECK", f"Phase should be preserved: {client.phase}"


def setup_task(tmp_path, repository):
    project = Project(
        repository=repository,
        state_dir=tmp_path / "state",
        readable_paths=["module.py"],
        editable_paths=["module.py"],
        checks=[Check(name="unit", command=["/usr/bin/true"])],
    )
    config = tmp_path / "project.json"
    config.write_text(project.model_dump_json())
    journal = journal_for(project, "a" * 32, create=True)
    journal.emit("CREATED")
    workspace = Workspace(project, journal)
    workspace.create()
    evidence = journal.artifact({"execution": {"exit_code": 1, "stderr": "regression"}})
    journal.emit("CHECK", evidence_ref=evidence, status="fail")
    journal.emit(
        "FINAL",
        status="NEEDS_USER",
        evidence_ref=journal.artifact({"task_id": "a" * 32, "status": "NEEDS_USER"}),
    )
    return config, journal, evidence


def finish(client):
    client.thread.join(timeout=10)
    assert not client.active, client.snapshot()


def test_terminal_client_replays_real_cli_and_checks_evidence_hash(tmp_path):
    with Fixture({"module.py": "VALUE = 1\n"}) as fixture:
        config, journal, evidence = setup_task(tmp_path, fixture.repository)
        client = CommandClient(config)
        client.launch("events", journal.task_id)
        finish(client)
        assert client.task_id == journal.task_id
        assert client.status == "NEEDS_USER"
        assert any("CHECK" in line and evidence in line for line in client.snapshot())
        client.launch("evidence", journal.task_id, evidence_ref=evidence)
        finish(client)
        assert client.returncode == 0
        assert client.result["evidence"]["execution"]["stderr"] == "regression"
        (journal.directory / "evidence" / (evidence + ".json")).write_text("{}")
        client.launch("evidence", journal.task_id, evidence_ref=evidence)
        finish(client)
        assert client.returncode == 2
        assert client.result["status"] == "NEEDS_USER"
        client.launch("diff", journal.task_id)
        finish(client)
        assert client.returncode == 0
        assert (fixture.repository / "module.py").read_text() == "VALUE = 1\n"


def test_terminal_decision_requires_typed_confirmation_and_stop_uses_cli(tmp_path, monkeypatch):
    terminal = Terminal(tmp_path / "policy.json")
    terminal.task_id = "a" * 32
    calls = []
    monkeypatch.setattr(terminal.action, "launch", lambda *a, **kw: calls.append((a, kw)))
    terminal.key("a")
    assert not calls
    terminal.input = "yes"
    terminal.submit()
    assert not calls
    terminal.key("a")
    terminal.input = "approve"
    terminal.submit()
    assert calls == [(("approve", "a" * 32), {})]
    terminal.key("x")
    assert calls[-1] == (("cancel", "a" * 32), {})
    terminal.key("j")
    terminal.key("\x1b")
    assert len(calls) == 2
    with pytest.raises(ValueError):
        terminal.stream.launch("start", request=" ")
    with pytest.raises(ValueError):
        terminal.stream.launch("status", "../other")
    with pytest.raises(ValueError):
        terminal.stream.launch("shell", "a" * 32)


def test_terminal_display_bounds_and_strips_terminal_controls(tmp_path):
    client = CommandClient(tmp_path / "policy.json")
    for _ in range(2100):
        client.consume("\x1b]52;c;clipboard\x07\u202eevil" + "x" * 5000)
    assert len(client.snapshot()) == 2000
    assert all(len(line) <= 4096 and "\x1b" not in line for line in client.snapshot())
    assert "\u202e" not in display_text("\u202e")
    client.consume(json.dumps({"status": "NEEDS_USER", "detail": "\x1b[2J"}))
    assert client.status == "NEEDS_USER"


def test_real_terminal_attach_resize_and_quit_restores_terminal(tmp_path):
    with Fixture({"module.py": "VALUE = 1\n"}) as fixture:
        config, journal, _ = setup_task(tmp_path, fixture.repository)
        master, slave = pty.openpty()
        original = termios.tcgetattr(slave)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "autocoder.v0.tui",
                "--config",
                str(config),
                "--task-id",
                journal.task_id,
            ],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env={**os.environ, "TERM": "xterm-256color"},
        )
        output = bytearray()
        try:
            deadline = time.monotonic() + 10
            while b"NEEDS_USER" not in output and time.monotonic() < deadline:
                if select.select([master], [], [], 0.2)[0]:
                    output.extend(os.read(master, 65536))
            assert b"NEEDS_USER" in output, output
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 8, 20, 0, 0))
            os.write(master, b"q")
            assert process.wait(timeout=5) == 0
            restored = termios.tcgetattr(slave)
            assert restored[3] & (termios.ECHO | termios.ICANON) == original[3] & (
                termios.ECHO | termios.ICANON
            )
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)


def test_terminal_start_uses_private_request_and_existing_cli(tmp_path, monkeypatch):
    import http.server
    import tempfile
    import threading

    from autocoder.v0.cli import load_project

    ready = threading.Event()
    release = threading.Event()

    class Inventory(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            ready.set()
            release.wait(timeout=5)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"models": []}')

        def log_message(self, *_):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Inventory)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    created = []
    mkstemp = tempfile.mkstemp

    def private_request(**kwargs):
        fd, name = mkstemp(dir=tmp_path, **kwargs)
        assert os.stat(name).st_mode & 0o077 == 0
        created.append(name)
        return fd, name

    monkeypatch.setattr("autocoder.v0.tui.tempfile.mkstemp", private_request)
    try:
        with Fixture({"module.py": "VALUE = 1\n"}) as fixture:
            config, _, _ = setup_task(tmp_path, fixture.repository)
            policy = json.loads(config.read_text())
            policy["endpoint"] = f"http://127.0.0.1:{server.server_port}"
            config.write_text(json.dumps(policy))
            terminal = Terminal(config)
            terminal.key("n")
            terminal.input = "Fix module.py; $(this stays task text)"
            terminal.submit()
            assert ready.wait(timeout=5)
            with pytest.raises(ValueError, match="Stop the running task"):
                terminal.key("q")
            release.set()
            finish(terminal.stream)
            assert terminal.stream.result["status"] == "BLOCKED_ENVIRONMENT"
            journal = journal_for(load_project(config), terminal.stream.task_id)
            initial = journal.read()[0]
            assert journal.load(initial["evidence_ref"])["request"] == terminal.input
            assert created and not any(os.path.exists(name) for name in created)
            assert terminal.key("q") is True
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_detaching_event_reader_does_not_cancel_task_but_stop_does(tmp_path):
    with Fixture({"module.py": "VALUE = 1\n"}) as fixture:
        config, journal, _ = setup_task(tmp_path, fixture.repository)
        journal.emit("PHASE", status="RUNNING")
        original = journal.path.read_bytes()
        client = CommandClient(config)
        client.launch("events", journal.task_id)
        deadline = time.monotonic() + 5
        while not client.snapshot() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert client.active
        client.close()
        assert not client.active
        assert journal.path.read_bytes() == original
        assert not (journal.directory / "cancel").exists()
        client.launch("cancel", journal.task_id)
        finish(client)
        assert client.returncode == 0
        assert (journal.directory / "cancel").exists()
