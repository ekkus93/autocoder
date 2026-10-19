"""Runs inside the isolated baseline namespace; exposes only the mounted model proxy."""

import json
import os
import selectors
import socket
import socketserver
import subprocess
from pathlib import Path


class Forward(socketserver.BaseRequestHandler):
    def handle(self):
        upstream = socket.socket(socket.AF_UNIX)
        upstream.settimeout(300)
        upstream.connect("/model-socket/inference.sock")
        selector = selectors.DefaultSelector()
        selector.register(self.request, selectors.EVENT_READ, upstream)
        selector.register(upstream, selectors.EVENT_READ, self.request)
        try:
            while True:
                events = selector.select(300)
                if not events:
                    return
                for key, _ in events:
                    data = key.fileobj.recv(65536)
                    if not data:
                        return
                    key.data.sendall(data)
        finally:
            selector.close()
            upstream.close()


if __name__ == "__main__":
    import threading

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = Server(("127.0.0.1", 11435), Forward)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    os.environ.update(
        {
            "OLLAMA_API_BASE": "http://127.0.0.1:11435",
            "OPENAI_API_BASE": "http://127.0.0.1:11435/v1",
            "OPENAI_BASE_URL": "http://127.0.0.1:11435/v1",
            "OPENAI_API_KEY": "local-placeholder",
            "OLLAMA_API_KEY": "local-placeholder",
            "LITELLM_LOCAL_MODEL_COST_MAP": "true",
            "DO_NOT_TRACK": "1",
            "OPENCODE_DISABLE_SHARE": "true",
            "OPENCODE_DISABLE_AUTOUPDATE": "true",
            "OPENCODE_DISABLE_MODELS_FETCH": "true",
        }
    )
    command = json.loads(Path("/config/command.json").read_text())
    raise SystemExit(subprocess.run(command, cwd="/work", env=os.environ).returncode)
