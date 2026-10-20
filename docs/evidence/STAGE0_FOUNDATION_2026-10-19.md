# Stage 0 foundation and sandbox checkpoint

- Code revision: `3162163b25c460842f8d6b599aa4ad8cad26b4fc`.
- UTC: `2026-10-19T11:15:32.717543+00:00` (smoke); sandbox evidence in the same run series.
- Scope: foundation infrastructure only. No scored evaluation, candidate-generated code,
  full v0 loop, remote CI, or human/hardware acceptance is claimed.

## Verified work

- **P0-01:** Python 3.12/`uv` package, pinned `uv.lock`, Ruff and pytest, native
  Ubuntu development instructions. Existing Apache-2.0 application license retained
  deliberately; third-party integration licensing remains a separate qualification.
- **P0-02:** headless `smoke`, `inventory`, `sandbox-probe`, and `verify-protocol`
  commands. Versioned Pydantic result records, JSONL records, exclusive evidence
  directories, source/model/host inventory emitted before experiments.
- **P0-03:** owned disposable Git repositories plus detached task worktrees, deterministic
  base commits, cleanup confined to the owned temporary directory. Regression tests prove
  repeated bases match and candidate mutations do not alter fixture originals.
- **P1D-01:** repeatable bubblewrap startup/policy probe on the actual host, with an
  observed failure recorded. Completion of this diagnostic does **not** pass the isolation gate.

## Commands and results

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run autocoder smoke --output /home/phil/.local/share/autocoder/stage0/foundation-smoke-3162163
uv run autocoder sandbox-probe --output /home/phil/.local/share/autocoder/stage0/sandbox-probe-3162163
```

Environment sync, lint and formatting passed. All **17 tests passed**. Smoke exited 0,
checked clean identical worktrees at base `6321007069154b20d06da02dd9ea1eff17b72cd4`,
and returned `VERIFIED_LOCAL`. This measures fixture integrity, not coding ability.
Sandbox probe exited 2 and returned `BLOCKED_ENVIRONMENT`.

## Host findings and required assistance

- Ubuntu 24.04.4; bubblewrap 0.9.0; Git 2.43.0; `uv` 0.12.9; Python 3.12.10.
- Ollama server 0.40.5; local client reports 0.17.4. The mismatch is recorded, not
  silently treated as the same build.
- Reference model: `qwen3.5:9b`, Q4_K_M, digest
  `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`.
- No model inference or context/residency/throughput benchmark has run.
- Both `kernel.unprivileged_userns_clone` and
  `kernel.apparmor_restrict_unprivileged_userns` read `1`.
- `/etc/apparmor.d/bwrap` does not exist on this host.

Observed startup error:

```text
bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted
```

Kernel journal at 2026-10-19 04:10:22 and 04:14:14 local time records
`userns_create` transitioning `/usr/bin/bwrap` from `unconfined` into
`unprivileged_userns`, followed by `apparmor="DENIED"` for `setpcap` and
`net_admin`. These are observed denials, not an inference from the startup error.

**Assistance needed:** arrange an approved, narrowly scoped AppArmor policy for
`/usr/bin/bwrap` that permits sandbox namespace setup, or provide another host with
validated confinement. No host security settings were changed. The checklist's
P1D gate and `SPEC.md` §§6.2/8.2 require validated isolation before autonomous
candidate execution and physically inaccessible held-out scoring.

After the host policy is addressed, rerun `sandbox-probe` into a fresh directory.
Successful startup must then be followed by all negative probes and evaluator
boundary tests; startup alone does not qualify unattended execution.

## Work remaining before scored evaluation

P0-04 inventory collection is implemented, but Serena/component versions and licenses
are not qualified. P0-05 includes a draft eight-task catalog and five experiment-family
descriptions, but exact micro-trials, complete oracle coverage and scoring scripts
remain unfinished. P0-06 has checksummed provisional thresholds and a verifier;
the future scored runner must require an explicit registration digest. P0-07 has
protected-file comparison support but no qualified external evaluator. P0-08 has
validated budget counters but no inference usage reservations/cancellation integration.
These items remain unchecked.

The frozen draft digest is
`dfaecd3da603dfda996895486d109bfe01c5752d5432e27a4cf96b4ee2a7628e`.
No benchmark scores were used to choose it. Changes require a new registration
version, as documented in README and the registration itself.

## Evidence inventory

Raw manifests include detailed host/model/template/license data and remain outside
the repository. The records below bind this summary to their exact content.

| Artifact | SHA-256 |
| --- | --- |
| `/home/phil/.local/share/autocoder/stage0/verification-3162163/format.log` | `7ff2df5e4a19c344d6ea2dfc25c25d2370159894cbac570f392753b22180e09c` |
| `/home/phil/.local/share/autocoder/stage0/verification-3162163/lint.log` | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |
| `/home/phil/.local/share/autocoder/stage0/verification-3162163/sync.log` | `7f134cf7fc9f393b7846b6d822b2e912994c58c9051e749a03827f9c7d5dea36` |
| `/home/phil/.local/share/autocoder/stage0/verification-3162163/tests.log` | `90a02c2f0887ae18b27c15d6989d067f96af5b8ba0e086da2ab3bc1baa1650e9` |
| `/home/phil/.local/share/autocoder/stage0/foundation-smoke-3162163/events.jsonl` | `f7dca6b21f44bda669d9c24ac4b043e6157055a6f05e779371e5532e12ed7d76` |
| `/home/phil/.local/share/autocoder/stage0/foundation-smoke-3162163/manifest.json` | `75435c77e3c2084027b2a7022ad57ee12c22d1cb07e02b4c0971ebd436cfbb06` |
| `/home/phil/.local/share/autocoder/stage0/foundation-smoke-3162163/result.json` | `a85f8f96258b146a0432f53df116e942d84e3dc90e18dae4c5345eb3d5bfa387` |
| `/home/phil/.local/share/autocoder/stage0/sandbox-probe-3162163/events.jsonl` | `84c041a33f6073f5d41e46720f42749734ed3e8c10bcc71636579e04616507ef` |
| `/home/phil/.local/share/autocoder/stage0/sandbox-probe-3162163/manifest.json` | `9c876123d14b9c63c80da2b759f6c06d00a9b7e991849f9a15fd522715088a13` |
| `/home/phil/.local/share/autocoder/stage0/sandbox-probe-3162163/result.json` | `cdfe29256fccc589e8366add3d8c67e4a3213d22c8078f50d27edee5d6012ee4` |
| `/home/phil/.local/share/autocoder/stage0/sandbox-probe-3162163/sandbox.json` | `59f7ec6c0035c90b63da2176e65b685119a53ca8834d54df4c7c125cd5f61efe` |
