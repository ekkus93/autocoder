import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from autocoder.budget import Budget
from autocoder.fixtures import Fixture
from autocoder.protocol import digest
from autocoder.v0.cli import journal_for
from autocoder.v0.dependencies import ArtifactCache
from autocoder.v0.schema import Check, DependencyArtifact, Preparation, Project
from autocoder.v0.verification import VerificationRunner, passed
from autocoder.v0.workspace import Workspace


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        calls = 0

        def do_GET(self):
            Handler.calls += 1
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"inert package bytes")

        def log_message(self, *args):
            pass

    service = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{service.server_port}/package.bin", Handler
    service.shutdown()
    service.server_close()
    thread.join(timeout=2)


def test_inert_download_is_hash_pinned_bounded_and_reused(tmp_path, server):
    from autocoder.protocol import Limits
    from autocoder.v0.journal import Journal

    url, handler = server
    journal = Journal(tmp_path / "task", "project", "task")
    journal.emit("CREATED")
    cache = ArtifactCache(tmp_path / "cache", Budget(Limits()), journal)
    artifact = DependencyArtifact(
        name="package.bin", url=url, sha256=digest(b"inert package bytes")
    )
    path = cache.acquire(artifact)
    assert path.read_bytes() == b"inert package bytes"
    assert cache.acquire(artifact) == path and handler.calls == 1
    with pytest.raises(ValueError, match="digest mismatch"):
        cache.acquire(artifact.model_copy(update={"sha256": "0" * 64}))
    with pytest.raises(ValueError, match="byte cap"):
        cache.acquire(artifact.model_copy(update={"sha256": "1" * 64, "max_bytes": 2}))
    assert not list((tmp_path / "cache").glob(".download-*"))


def test_dependency_hook_and_read_only_check_cannot_escape(tmp_path, server):
    url, _ = server
    secret = tmp_path / "sentinel"
    secret.write_text("private host data")
    outside = tmp_path / "outside"
    hook = f"""
from pathlib import Path
import json,socket
result={{}}
try:
    Path({str(secret)!r}).read_text()
    result['read_blocked']=False
except OSError:
    result['read_blocked']=True
try:
    Path({str(outside)!r}).write_text('escape')
    result['write_blocked']=False
except OSError:
    result['write_blocked']=True
try:
    socket.create_connection(('127.0.0.1',11434),timeout=1)
    result['network_blocked']=False
except OSError:
    result['network_blocked']=True
try:
    Path('/artifacts/package.bin').write_text('tamper')
    result['artifact_read_only']=False
except OSError:
    result['artifact_read_only']=True
assert Path('/artifacts/package.bin').read_bytes()==b'inert package bytes'
Path('.autocoder-deps').mkdir()
Path('.autocoder-deps/results.json').write_text(json.dumps(result))
"""
    readonly_check = """
import json,pathlib
assert all(json.loads(pathlib.Path('/deps/results.json').read_text()).values())
try:
    pathlib.Path('/deps/illegal').write_text('bad')
    raise AssertionError('writable dependencies')
except OSError:
    pass
"""
    check = Check(name="prepared", command=["/usr/bin/python3", "-I", "-c", readonly_check])
    with Fixture({"module.py": "VALUE=1\n", "setup.py": hook}) as fixture:
        project = Project(
            repository=fixture.repository,
            state_dir=tmp_path / "state",
            readable_paths=["module.py"],
            editable_paths=["module.py"],
            checks=[check],
            preparation=Preparation(
                artifacts=[
                    DependencyArtifact(
                        name="package.bin", url=url, sha256=digest(b"inert package bytes")
                    )
                ],
                command=["/usr/bin/python3", "-I", "setup.py"],
            ),
        )
        journal = journal_for(project, "a" * 32, create=True)
        journal.emit("CREATED")
        workspace = Workspace(project, journal)
        workspace.create()
        runner = VerificationRunner(workspace, Budget(project.limits))
        record = runner.run(check, "candidate")
        assert passed([record]), record
        assert not outside.exists() and secret.read_text() == "private host data"
        ready = [r for r in journal.read() if r["kind"] == "DEPENDENCIES_READY"]
        assert len(ready) == 1
        other = VerificationRunner(workspace, Budget(project.limits))
        assert other.dependencies == runner.dependencies
        assert len([r for r in journal.read() if r["kind"] == "PREPARATION_STARTED"]) == 1
