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

`benchmarks/v1/` contains provisional frozen thresholds/budgets and a draft set of
four Python and four Rust tasks. Its checksum lock detects changed or added assets:

```sh
uv run autocoder verify-protocol --expected-sha256 dfaecd3da603dfda996895486d109bfe01c5752d5432e27a4cf96b4ee2a7628e
```

There is no scored runner yet. Oracle coverage, exact micro-trial registration,
scoring scripts and integration qualification remain incomplete (P0-05/P0-07).
Scored commands must require an explicit registration digest when introduced.
To change frozen gates or budgets, create a new benchmark directory/version, record
the rationale, and freeze its asset hashes before scoring. Never silently tune
thresholds against observed scores.

The sandbox probe uses isolated namespaces, read-only system mounts, a writable
throwaway candidate directory and no host home mount. It checks a hidden sentinel,
outside writes, network namespace isolation and worktree writes. Failed startup is
`BLOCKED_ENVIRONMENT`, never evidence that negative tests passed. This preliminary
probe is not a production sandbox executor. No candidate execution is provided
until isolation and evaluator boundaries are qualified.

Source: `src/autocoder/`; tests: `tests/`; specification and evidence summaries:
`docs/`. `Fixture` owns its entire temporary repository/worktree pair and cleans
only that pair. It never resets, cleans or writes the user's checkout.
