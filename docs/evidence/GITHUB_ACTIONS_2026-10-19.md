# Hosted GitHub Actions qualification

## Requested behavior

The owner requested GitHub Actions CI and artifact storage only for tagged
releases. The workflow uses hosted Ubuntu 24.04, pinned uv/Python/actions, locked
dependencies, qualified bubblewrap/systemd execution, lint, formatting and the full
suite. Only successful `v*` tag pushes build/upload distributions, JUnit XML and
sandbox JSON; artifacts expire after 14 days. Ordinary branch/PR/manual runs
upload nothing. Dependency cache saving is disabled.

## Local verification

- `actionlint .github/workflows/verify.yml`: pass.
- `shellcheck .github/scripts/prepare-runner.sh`: pass.
- `bash -n .github/scripts/prepare-runner.sh`: pass.
- `uv run ruff check .` and `uv run ruff format --check .`: pass.
- `uv run pytest -q`: 77 passed; raw log at
  `/home/phil/.local/share/autocoder/stage0/github-ci-local-verification.log`.
- `git diff --check`: pass.

The runner preparation script is restricted to GitHub-hosted Linux. Its
privileged setup was not executed on the developer host. Hosted execution and
artifact API inspection are pending the first branch run. No test release tag
will be created merely to exercise uploads.

## Scope of publication

The remote default branch contains the design baseline. The dedicated CI branch
includes the previously local implementation because CI needs that code and its
complete test suite. Publication does not merge the default branch. Historic
benchmark registrations and local task acceptance remain unchanged.
