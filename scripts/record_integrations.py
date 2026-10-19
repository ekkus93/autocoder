"""Record the independently installed Serena pin and local tool licensing evidence."""

import json
import subprocess
from pathlib import Path

from autocoder.protocol import digest

ROOT = Path(__file__).resolve().parents[1]
SERENA_PIN = "d9e4c796fae0207ba6848d1df4b331122a5567b5"
SOURCE = f"git+https://github.com/oraios/serena.git@{SERENA_PIN}"


def run(*arguments):
    return subprocess.run(arguments, capture_output=True, text=True, check=True, timeout=60).stdout


def main():
    metadata = run(
        "uv",
        "tool",
        "run",
        "--from",
        SOURCE,
        "python",
        "-c",
        (
            "import importlib.metadata as m,json; "
            "print(json.dumps({n:{'version':m.version(n),'license':"
            "m.metadata(n).get('License-Expression') or m.metadata(n).get('License')} "
            "for n in ('serena-agent','mcp','pydantic')}))"
        ),
    )
    tool_list = run("uv", "tool", "run", "--from", SOURCE, "serena", "tools", "list", "--all")
    licenses = {}
    for name in ("git", "bubblewrap", "ripgrep", "python3.12", "gcc-13"):
        path = Path("/usr/share/doc", name, "copyright")
        licenses[name] = (
            {"path": str(path), "sha256": digest(path.read_bytes())}
            if path.is_file()
            else {"status": "unavailable"}
        )
    record = {
        "serena": {
            "source": SOURCE,
            "commit": SERENA_PIN,
            "packages": json.loads(metadata),
            "tool_inventory": tool_list,
            "application_license": "GPL-3.0-or-later",
            "solidlsp_license": "MIT",
            "license_source": f"https://github.com/oraios/serena/blob/{SERENA_PIN}/LICENSE",
            "integration": "Independent MCP process; no Serena imports or vendored source",
        },
        "system_copyright_files": licenses,
        "other_tool_licenses": {
            "uv": "MIT OR Apache-2.0",
            "ollama": "MIT",
            "rust": "MIT OR Apache-2.0",
            "opencode": "MIT",
        },
        "not_yet_installed": ["aider", "microsoft-agent-framework"],
    }
    target = ROOT / "benchmarks/integrations.json"
    target.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(target)


if __name__ == "__main__":
    main()
