"""Stage 0 confinement probe only; never fall back to host candidate execution."""

import json
import subprocess
import tempfile
from pathlib import Path


def argv(worktree: Path, executable: list[str]) -> list[str]:
    arguments = [
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "HOME",
        "/tmp",
        "--setenv",
        "LANG",
        "C.UTF-8",
    ]
    for path in ("/usr", "/lib", "/lib64", "/bin"):
        if Path(path).exists():
            arguments += ["--ro-bind", path, path]
    arguments += [
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--bind",
        str(worktree.resolve()),
        "/work",
        "--chdir",
        "/work",
        "--",
    ]
    return arguments + executable


def probe() -> dict:
    with tempfile.TemporaryDirectory(prefix="autocoder-sandbox-") as temporary:
        root = Path(temporary)
        worktree = root / "candidate"
        worktree.mkdir()
        sentinel = root / "secret-sentinel"
        sentinel.write_text("private evaluator sentinel")
        # No candidate code is run. This trusted fixed probe measures boundary behavior.
        script = f"""
import json, pathlib, socket
results = {{}}
results["secret_hidden"] = not pathlib.Path({str(sentinel)!r}).exists()
try:
    pathlib.Path({str(root / "outside-write")!r}).write_text("escape")
    results["outside_write_blocked"] = False
except OSError:
    results["outside_write_blocked"] = True
try:
    connection = socket.create_connection(("127.0.0.1", 11434), timeout=1)
    connection.close()
    results["host_network_blocked"] = False
except OSError:
    results["host_network_blocked"] = True
host_netns = {Path("/proc/self/ns/net").readlink().name!r}
results["network_namespace_isolated"] = (
    pathlib.Path("/proc/self/ns/net").readlink().name != host_netns
)
pathlib.Path("/work/probe-output").write_text("allowed")
results["worktree_write_allowed"] = True
print(json.dumps(results))
"""
        arguments = argv(worktree, ["/usr/bin/python3", "-I", "-c", script])
        try:
            process = subprocess.run(arguments, capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as error:
            return {"status": "BLOCKED_ENVIRONMENT", "error_type": type(error).__name__}
        checks = {}
        if process.returncode == 0:
            try:
                checks = json.loads(process.stdout)
            except json.JSONDecodeError:
                pass
        passed = len(checks) == 5 and all(value is True for value in checks.values())
        return {
            "status": "VERIFIED_LOCAL" if passed else "BLOCKED_ENVIRONMENT",
            "exit_code": process.returncode,
            "stdout": process.stdout[:8192],
            "stderr": process.stderr[:8192],
            "checks": checks,
            "policy": {
                "namespaces": "all",
                "network": "unshared",
                "system_mounts": "read_only",
                "writable_mounts": ["candidate", "ephemeral_tmp"],
                "home": "not_mounted",
                "fallback_to_host_execution": False,
            },
            "host_policy": {
                name: Path("/proc/sys/kernel", name).read_text().strip()
                for name in ("unprivileged_userns_clone", "apparmor_restrict_unprivileged_userns")
                if Path("/proc/sys/kernel", name).exists()
            },
        }
