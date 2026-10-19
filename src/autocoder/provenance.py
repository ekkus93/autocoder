"""Read-only reproducibility inventory. Unknown measurements stay explicitly unknown."""

import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from autocoder import __version__
from autocoder.protocol import digest, utc_now


def command(argv: list[str]) -> dict:
    if not shutil.which(argv[0]):
        return {"status": "unavailable"}
    try:
        process = subprocess.run(argv, capture_output=True, text=True, timeout=10)
        return {
            "status": "observed",
            "exit_code": process.returncode,
            "stdout": process.stdout[:16384],
            "stderr": process.stderr[:4096],
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}


def request_json(endpoint: str, route: str, body: dict | None = None) -> dict:
    url = urllib.parse.urlsplit(endpoint)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        raise ValueError("Endpoint must be an HTTP(S) origin without credentials or query")
    request = urllib.request.Request(
        endpoint.rstrip("/") + route,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    # Do not forward local inference metadata through ambient proxy settings.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=10) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Ollama inventory response too large")
    return json.loads(raw)


def inventory(repository: Path, endpoint: str, model: str) -> dict:
    packages = {}
    for name in ("local-autocoder", "pydantic", "pytest", "ruff", "serena-agent", "mcp"):
        try:
            metadata = importlib.metadata.metadata(name)
            packages[name] = {
                "version": metadata["Version"],
                "license": metadata.get("License-Expression")
                or metadata.get("License")
                or "unknown",
            }
        except importlib.metadata.PackageNotFoundError:
            packages[name] = {"status": "not_installed_in_runner_environment"}
    ollama = {}
    for route in ("/api/version", "/api/tags", "/api/ps"):
        try:
            ollama[route] = request_json(endpoint, route)
        except Exception as error:
            ollama[route] = {"status": "unavailable", "error_type": type(error).__name__}
    try:
        show = request_json(endpoint, "/api/show", {"model": model})
        # Preserve exact template and licensing evidence, not a paraphrase.
        ollama["model"] = {
            key: show.get(key, "unknown")
            for key in (
                "details",
                "model_info",
                "template",
                "parameters",
                "license",
                "capabilities",
            )
        }
    except Exception as error:
        ollama["model"] = {"status": "unavailable", "error_type": type(error).__name__}
    source_hashes = {}
    for pattern in ("src/**/*.py", "benchmarks/v1/*", "pyproject.toml", "uv.lock"):
        for path in repository.glob(pattern):
            if path.is_file():
                source_hashes[str(path.relative_to(repository))] = digest(path.read_bytes())
    gpu = []
    for device in Path("/sys/class/drm").glob("card[0-9]*/device"):
        if not device.parent.name.removeprefix("card").isdigit():
            continue
        gpu.append(
            {
                name: (device / name).read_text().strip()
                for name in ("vendor", "device", "mem_info_vram_total", "mem_info_vram_used")
                if (device / name).is_file()
            }
        )
    return {
        "schema_version": 1,
        "utc_time": utc_now(),
        "runner_version": __version__,
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu": platform.processor(),
        "packages": packages,
        "model_name": model,
        "ollama": ollama,
        "gpu_sysfs": gpu,
        "source_sha256": source_hashes,
        "git": command(["git", "-C", str(repository), "rev-parse", "HEAD"]),
        "working_tree": command(["git", "-C", str(repository), "status", "--porcelain"]),
        "tools": {
            name: command([name, "--version"])
            for name in (
                "git",
                "uv",
                "ollama",
                "bwrap",
                "rg",
                "cargo",
                "rustc",
                "opencode",
                "aider",
            )
        },
        "gpu_pci": command(["lspci", "-nn"]),
        "tool_inventory": ["fixture_integrity", "protocol_verification", "sandbox_probe"],
        "limitations": [
            "No inference or model quality is measured by inventory collection.",
            "Serena version is unknown unless installed in the runner environment.",
            "Tool licenses must be qualified before selecting integrations.",
        ],
    }
