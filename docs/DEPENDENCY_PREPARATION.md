# Stage 0 dependency execution policy

Stage 0 candidate fixtures currently use only Python's standard library and Rust's
standard library. Candidate builds and checks run offline inside `Sandbox`, using
read-only system files and an explicitly mounted read-only Rust toolchain.

## Bootstrap versus candidate dependencies

`uv sync --locked` prepares the trusted experiment controller's `.venv` from the
reviewed project manifest and lock. It is not an agent-callable operation.
Independently pinned Serena runs in its own `uv` environment, avoiding Python
package/license coupling with the controller. It is not imported into the engine.

Candidate dependency preparation must use two separate steps:

1. **Acquire inert artifacts.** The controller may download only explicitly
   configured package URLs/registries with a declared digest and size limit. Download
   wheels/crates as bytes; never import them, run a package manager's build/install
   hooks, or execute repository-provided download scripts on the host. Cache by
   digest outside candidate worktrees. Verify digests before reuse. Reject traversal,
   symlinks, special files and decompression-size violations during extraction.
2. **Install/build offline in isolation.** Make verified artifacts available read-only
   in a fresh sandbox. Put install outputs and compiler caches in task-local writable
   storage. Execute package metadata/build hooks, `setup.py`, Rust `build.rs`, tests
   and compilers only there, with network disabled and wall/CPU/memory/output limits.
   Dependency installation failure blocks the check; it never enables a host fallback.

A general network-enabled candidate package installer is not implemented. A task
that needs unavailable dependencies must return `BLOCKED_ENVIRONMENT`; the model
cannot authorize downloads or expand the sandbox mounts. Shared writable executable
caches are not qualified. A model endpoint stays outside the check sandbox.

## Isolation availability

There is no supervised execution mode or alternate backend in the current CLI.
`Sandbox` probes the configured bubblewrap policy at construction and raises
`SandboxUnavailable` if qualification fails. No candidate command is issued after a
failed probe. New hosts must pass the negative probes before unattended evaluation.
The administrator-approved executable-specific AppArmor allowance enables namespace
creation; bubblewrap's mounts, dropped capabilities and namespaces provide check
confinement. The system-wide user-namespace restriction remains enabled.

## Evidence

`tests/test_evaluator.py` exercises actual sandbox execution, external-oracle
inaccessibility, bounded processes/output, and base/fixed candidate scoring.
`tests/test_isolation.py` runs a deliberately hostile installation hook inside the
same sandbox and checks that it cannot read a host sentinel, write outside its
worktree or connect to host Ollama. These are controller tests, not model benchmark
scores. Any failure leaves isolation-dependent milestones incomplete.
