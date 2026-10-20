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
privileged setup was not executed on the developer host. A temporary local
`uv build` produced both the wheel and source archive; wheel contents included
the terminal and CI modules. The temporary distributions were removed.

## Hosted qualification

The initial CI revision was `da179b5ed04a57b9b83bd5a1cdd360b6b62cf1f4`.

| Event | Run | Result | Suite | Uploaded artifacts |
| --- | --- | --- | --- | --- |
| Branch push | [39348852944](https://github.com/ekkus93/autocoder/actions/runs/39348852944) | success | 77 passed in 34.02s | 0 |
| Pull request | [39348890696](https://github.com/ekkus93/autocoder/actions/runs/39348890696) | success | 77 passed in 39.94s | 0 |

Hosted setup, actual sandbox qualification, Ruff checks and all tests passed.
The artifact API returned empty lists for both completed runs; release build and
upload steps were skipped. The cache API reported zero saved caches. Ordinary
GitHub job logs remain visible; these are separate from uploaded build artifacts.
The PR run checks GitHub's merge ref; the push run checks the exact source head.

The first runs used the existing checkout v4 pin and reported a Node 20
deprecation warning. The final configuration pins checkout v7.0.1 (Node 24),
setup-uv v10.3.0, and upload-artifact v7.0.2; follow-up PR checks validate that
configuration. The Python application and runner preparation remain unchanged.

No release tag or GitHub release was created to exercise uploads. The positive
release path has local packaging and workflow validation, not a live upload claim.
These runs verify repository CI; no app task's human/integration acceptance was
changed or inferred from them.

## Recorded artifacts

Raw records remain under `/home/phil/.local/share/autocoder/stage0/`.

| Artifact | SHA-256 |
| --- | --- |
| `github-ci-local-verification.log` | `a92f36ae1179f97c986cd562fab25c7639ef7568c320b3e12ef1154de2b12e38` |
| `github-ci-push.log` | `ee7792f52d01486f48ba2f93d1e8ca1ec604a8360e73a817a6609a8b36a20f60` |
| `github-ci-pr.log` | `3983194ea406aa568e9f8e87a7526a2b37aa4a1cb73d0212501f95655cf42533` |
| `github-ci-push-run.json` | `55bab6941f526a0253d0318ff4160b38c87badf37dd9e33157cc4fa839093b98` |
| `github-ci-pr-run.json` | `1d2aca6588ade85cd073ffd5a85b8646be86672b03847616a5e8e4713bb466e9` |
| `github-ci-push-artifacts.json` | `bf6638afd0bdbf03a3236bb78ff0fe1a70b76eb9f5ba9b8102624fde8ac48cef` |
| `github-ci-pr-artifacts.json` | `bf6638afd0bdbf03a3236bb78ff0fe1a70b76eb9f5ba9b8102624fde8ac48cef` |

## Scope of publication

The remote default branch contains the design baseline. The dedicated CI branch
includes the previously local implementation because CI needs that code and its
complete test suite. Publication in [PR #1](https://github.com/ekkus93/autocoder/pull/1) does not merge the default branch. Historic
benchmark registrations and local task acceptance remain unchanged.
