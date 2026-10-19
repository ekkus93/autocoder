# autocoder

Local-first coding-loop experiments using Python, `uv`, Git and Ollama. This is
Stage 0 infrastructure, **not a working autonomous coding application**. Scope and
dependency gates are defined in [docs/SPEC.md](docs/SPEC.md) and
[docs/TODO.md](docs/TODO.md).

## Development

Native Ubuntu requires Git, Python 3.12+ and `uv`; Docker/Podman are unnecessary.
The existing Apache-2.0 license is retained deliberately for the application.
Integration and model licenses must be qualified separately.

```sh
uv sync --locked
uv run autocoder --version
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

`uv` creates `.venv`; the committed `uv.lock` pins development and runtime packages.
Python uses four-space indentation, Ruff formatting, and `snake_case` names. Tests
live in `tests/test_*.py`. There is no coverage threshold yet. The complete local
suite is the current verification gate; remote CI has not been configured or run.

## Stage 0 commands

Run from the repository root, using a fresh output directory for each invocation:

```sh
uv run autocoder smoke --output /tmp/autocoder-smoke-01
uv run autocoder inventory --output /tmp/autocoder-inventory-01
uv run autocoder sandbox-probe --output /tmp/autocoder-sandbox-01
```

The smoke experiment checks clean, identical fixture worktrees at a pinned SHA.
It runs no model-generated code and does not measure coding ability. Each experiment
writes `manifest.json` before running, followed by versioned `result.json` and
`events.jsonl`. Raw evidence belongs outside this checkout; existing directories
are rejected. Exit status is 0 for verified results and 2 for blocked/failed runs.
Inventory writes only its manifest.

Global options precede the subcommand:

```sh
uv run autocoder --endpoint http://127.0.0.1:11434 --model qwen3.5:9b inventory --output /tmp/autocoder-model-01
```

The manifest captures model digest, template, model license, quantization, runtime
versions, installed Python packages, source hashes and host/GPU observations.
Missing integrations remain explicitly unknown/unavailable. Inventory does not
load a model or measure inference throughput.

## Benchmark registration and execution boundary

Frozen registrations live under `benchmarks/`: v1 is the initial draft; v2/v3
bind the component experiments; v4 binds the first complete pilot; v5 registers
the corrective flat-edit/public-feedback condition. Each directory has a checksum
lock. Engine hashes additionally bind executable controller sources. Reproduce
older experiments from their recorded commit rather than editing frozen assets.

```sh
uv run python scripts/run_pilot_v5.py \
  --expected-sha256 c04da250ab2f317ff8f4dabef3f18d91530e75811d6ed5a68f730e89ade87307 \
  --output /tmp/autocoder-pilot-v5-01
```

This is a sequential, bounded 42-run suite (eight tasks per arm, followed by the
preselected repeats), requiring the registered model digest, baseline binary and
isolated Aider environment. It makes real inference requests. Baseline bindings
and fairness limitations are in `benchmarks/v5/`; they include machine-specific
binary paths. Change bindings only in a newly frozen registration before scoring.
The Aider runtime is independently prepared with
`uv sync --project experiments/aider --locked --python /usr/bin/python3`;
the native baseline sandbox requires its interpreter under read-only `/usr`.
OpenCode's exact executable path, version and SHA-256 are registered in
`baseline-bindings.json`. The runner refuses a different binary or model digest.
See [component evidence](docs/evidence/STAGE0_COMPONENTS_2026-10-19.md) for measured
scope, failures and selected primitives. The [Stage 0 decision packet](docs/evidence/STAGE0_DECISION_2026-10-19.md)
records the current gate: minimum feasibility passes; the product decision remains open.

The evaluator requires bubblewrap, an effective user-namespace/AppArmor policy,
`prlimit`, a user systemd manager with cgroup limits, and a Rust toolchain for Rust
tasks. Commands run offline with read-only system/toolchain mounts and a writable
throwaway worktree; the host home and private oracle files are absent. Memory,
process, CPU, file, output and wall limits apply. Startup qualification failure
blocks execution; no host fallback is provided. Baseline model access goes through
a bounded inference-only proxy, without giving clients host network access.

Run `uv run autocoder sandbox-probe --output /tmp/autocoder-sandbox-02` on a new
host. A startup failure is `BLOCKED_ENVIRONMENT`, not a passed negative test.
The [dependency policy](docs/DEPENDENCY_PREPARATION.md) distinguishes trusted
controller bootstrap from candidate build/install hooks. Candidate fixtures use
only standard libraries; arbitrary dependency acquisition is not implemented.

Source: `src/autocoder/`; tests: `tests/`; specification and evidence summaries:
`docs/`. `Fixture` owns its entire temporary repository/worktree pair and cleans
only that pair. It never resets, cleans or writes the user's checkout.
