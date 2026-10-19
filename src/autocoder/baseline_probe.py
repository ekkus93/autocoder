"""Run baseline clients in namespaces with inference-only connectivity and no shell tool."""

import json
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from autocoder.budget import Budget
from autocoder.fixtures import git
from autocoder.model_proxy import ModelProxy
from autocoder.sandbox import argv, probe

ROOT = Path(__file__).resolve().parents[2]


def baseline_config(arm: str, task: dict, config: Path) -> list[str]:
    editable = [name for name in task["files"] if name not in task["protected"]]
    if arm == "aider":
        settings = (
            "- name: ollama_chat/qwen3.5:9b\n  edit_format: diff\n  extra_params:\n"
            "    num_ctx: 32768\n    temperature: 0\n    seed: 42\n    think: false\n"
        )
        (config / "settings.yml").write_text(settings)
        (config / "metadata.json").write_text(
            json.dumps(
                {
                    "ollama_chat/qwen3.5:9b": {
                        "max_input_tokens": 28672,
                        "max_output_tokens": 4096,
                        "max_tokens": 4096,
                        "input_cost_per_token": 0,
                        "output_cost_per_token": 0,
                        "litellm_provider": "ollama_chat",
                        "mode": "chat",
                    }
                }
            )
        )
        command = [
            "/baseline/bin/python",
            "/baseline/bin/aider",
            "--model",
            "ollama_chat/qwen3.5:9b",
            "--model-settings-file",
            "/config/settings.yml",
            "--model-metadata-file",
            "/config/metadata.json",
            "--message",
            task["prompt"],
            "--yes-always",
            "--no-auto-commits",
            "--no-dirty-commits",
            "--no-auto-test",
            "--no-auto-lint",
            "--no-suggest-shell-commands",
            "--no-check-update",
            "--no-detect-urls",
            "--no-analytics",
            "--no-gitignore",
            "--no-add-gitignore-files",
            "--map-tokens",
            "1024",
            "--chat-history-file",
            "/tmp/chat.md",
            "--input-history-file",
            "/tmp/input.txt",
            *editable,
        ]
        if task.get("map_probe"):
            del command[command.index("--message") : command.index("--message") + 2]
            if editable:
                del command[-len(editable) :]
            command += ["--show-repo-map"]
            command[command.index("--map-tokens") + 1] = str(task["map_probe"])
        return command
    configuration = {
        "$schema": "https://opencode.ai/config.json",
        "model": "local/qwen3.5:9b",
        "small_model": "local/qwen3.5:9b",
        "share": "disabled",
        "autoupdate": False,
        "provider": {
            "local": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Local Ollama",
                "options": {"baseURL": "http://127.0.0.1:11435/v1", "apiKey": "local-placeholder"},
                "models": {
                    "qwen3.5:9b": {
                        "name": "Qwen3.5 9B",
                        "tool_call": True,
                        "limit": {"context": 32768, "output": 2048},
                    }
                },
            }
        },
        "permission": {
            "*": "deny",
            "read": "allow",
            "glob": "allow",
            "grep": "allow",
            "edit": "allow",
            "question": "deny",
            "bash": "deny",
            "task": "deny",
            "external_directory": "deny",
            "webfetch": "deny",
            "websearch": "deny",
        },
        "agent": {
            "build": {
                "steps": 10,
                "prompt": (
                    "Repair the bounded fixture using file tools. Read before editing. "
                    "Keep changes scoped to the task and preserve tests/configuration. "
                    "Verification is external. Finish after applying the source changes."
                ),
            }
        },
        "instructions": [],
        "plugin": [],
        "mcp": {},
    }
    # Source reads and writes are confined by OS mounts; protected edits are rejected by evaluator.
    (config / "opencode.json").write_text(json.dumps(configuration))
    return [
        "/baseline/opencode",
        "run",
        "--pure",
        "--format",
        "json",
        "--model",
        "local/qwen3.5:9b",
        task["prompt"]
        + " Source files: "
        + ", ".join(editable)
        + ". Use file tools only; verification is external. "
        "Do not edit tests or package configuration.",
    ]


def run_baseline(arm: str, task: dict, endpoint: str, budget: Budget, output: Path) -> dict:
    if probe()["status"] != "VERIFIED_LOCAL":
        raise RuntimeError("Baseline isolation qualification failed")
    with tempfile.TemporaryDirectory(prefix="autocoder-baseline-") as temporary:
        root = Path(temporary)
        work, config, sockets = root / "candidate", root / "config", root / "sockets"
        for path in (work, config, sockets):
            path.mkdir()
        # Copy only the fixture source; make a real task-local .git for baseline clients.
        for name, content in task["files"].items():
            target = work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        git(work, "init", "--object-format=sha1", "--initial-branch=fixture")
        git(work, "config", "user.name", "Autocoder Fixture")
        git(work, "config", "user.email", "fixture@localhost")
        git(work, "add", "--all")
        git(work, "commit", "--no-gpg-sign", "-m", "Pinned fixture base")
        command = baseline_config(arm, task, config)
        (config / "command.json").write_text(json.dumps(command))
        executable = [
            "/usr/bin/prlimit",
            "--cpu=60",
            "--fsize=8388608",
            "--nofile=256",
            "--",
            "/usr/bin/python3",
            "/bridge.py",
        ]
        arguments = argv(work, executable)
        delimiter = arguments.index("--")
        dependency = (
            ROOT / "experiments/aider/.venv"
            if arm == "aider"
            else Path(shutil.which("opencode")).resolve().parent
        )
        arguments[delimiter:delimiter] = [
            "--ro-bind",
            str(dependency),
            "/baseline",
            "--ro-bind",
            str(sockets),
            "/model-socket",
            "--ro-bind",
            str(config),
            "/config",
            "--ro-bind",
            str(ROOT / "scripts/baseline_bridge.py"),
            "/bridge.py",
            "--setenv",
            "OPENCODE_CONFIG",
            "/config/opencode.json",
            "--setenv",
            "OPENBLAS_NUM_THREADS",
            "1",
        ]
        proxy = ModelProxy(
            sockets / "inference.sock", endpoint, "qwen3.5:9b", budget, output / "proxy.jsonl"
        )
        unit = f"autocoder-baseline-{uuid.uuid4().hex}.scope"
        arguments = [
            "systemd-run",
            "--user",
            "--scope",
            "--quiet",
            "--unit",
            unit,
            "--property=MemoryMax=2G",
            "--property=TasksMax=64",
            *arguments,
        ]
        started = time.monotonic()
        try:
            process = subprocess.run(
                arguments, capture_output=True, timeout=budget.remaining_seconds
            )
            stdout, stderr = process.stdout[:65536], process.stderr[:65536]
            status = "finished"
            code = process.returncode
        except subprocess.TimeoutExpired as error:
            status, code = "timeout", None
            stdout, stderr = (error.stdout or b"")[:65536], (error.stderr or b"")[:65536]
        finally:
            subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True, timeout=10)
            proxy.close()
        result = {
            "status": status,
            "exit_code": code,
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
            "seconds": time.monotonic() - started,
            "proxy_error": proxy.error,
            "usage": budget.snapshot().model_dump(),
        }
        # Preserve a bounded candidate snapshot for the independent external scorer.
        from autocoder.evaluator import source_snapshot

        snapshot = output / "candidate"
        snapshot.mkdir()
        source_snapshot(work, snapshot)
        return result
