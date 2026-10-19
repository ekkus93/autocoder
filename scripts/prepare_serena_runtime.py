"""Prepare the trusted pinned navigation runtime outside candidate repositories."""

import argparse
import importlib.metadata
import json
import os
import shutil
import subprocess
from pathlib import Path

from autocoder.protocol import digest
from autocoder.v0.verification import directory_digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime", type=Path, required=True, help="New absolute directory outside the checkout"
    )
    parser.add_argument(
        "--node", type=Path, required=True, help="Reviewed installed Node executable"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    runtime = args.runtime.resolve()
    if not args.runtime.is_absolute() or runtime.is_relative_to(root) or runtime.exists():
        raise ValueError("Choose a new absolute runtime directory outside the checkout")
    node = args.node.resolve()
    if not node.is_file() or node.stat().st_size > 256_000_000:
        raise ValueError("Expected a reviewed bounded Node executable")
    subprocess.run(
        [
            "uv",
            "sync",
            "--project",
            str(root / "experiments/serena"),
            "--locked",
            "--python",
            "/usr/bin/python3",
        ],
        check=True,
        env=dict(os.environ, UV_PROJECT_ENVIRONMENT=str(runtime)),
    )
    shutil.copyfile(node, runtime / "bin/node")
    (runtime / "bin/node").chmod(0o755)
    packages = {
        p.metadata["Name"]: p.version
        for p in importlib.metadata.distributions(
            path=[str(runtime / "lib/python3.12/site-packages")]
        )
    }
    node_version = subprocess.check_output([str(node), "--version"], text=True, timeout=5).strip()
    (runtime / "inventory.json").write_text(
        json.dumps(
            {
                "packages": packages,
                "node_version": node_version,
                "node_sha256": digest(node.read_bytes()),
                "lock_sha256": digest((root / "experiments/serena/uv.lock").read_bytes()),
            },
            sort_keys=True,
            indent=2,
        )
    )
    print(
        json.dumps(
            {"serena_runtime": str(runtime), "serena_runtime_sha256": directory_digest(runtime)},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
