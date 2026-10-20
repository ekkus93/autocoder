#!/usr/bin/env bash
# Configure only an ephemeral GitHub-hosted Ubuntu runner, never a developer host.
set -euo pipefail

if [[ ${GITHUB_ACTIONS:-} != true || ${RUNNER_ENVIRONMENT:-} != github-hosted || ${RUNNER_OS:-} != Linux ]]; then
  echo 'This setup script requires a GitHub-hosted Linux runner.' >&2
  exit 1
fi

sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends bubblewrap ripgrep apparmor dbus-user-session build-essential

# Ubuntu 24.04 can restrict unprivileged user namespaces through AppArmor.
# Grant the installed executable access, retaining the system-wide restriction.
if ! bwrap --unshare-user --ro-bind / / -- /usr/bin/true; then
  sudo tee /etc/apparmor.d/autocoder-ci-bwrap >/dev/null <<'PROFILE'
abi <abi/4.0>,
include <tunables/global>
profile autocoder-ci-bwrap /usr/bin/bwrap flags=(unconfined) {
  userns,
}
PROFILE
  sudo apparmor_parser -r /etc/apparmor.d/autocoder-ci-bwrap
fi

runner_uid=$(id -u)
runner_user=$(id -un)
sudo loginctl enable-linger "$runner_user"
sudo systemctl start "user@${runner_uid}.service"
export XDG_RUNTIME_DIR="/run/user/$runner_uid"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
printf 'XDG_RUNTIME_DIR=%s\nDBUS_SESSION_BUS_ADDRESS=%s\n' \
  "$XDG_RUNTIME_DIR" "$DBUS_SESSION_BUS_ADDRESS" >> "$GITHUB_ENV"

# Fail early unless the actual memory/task-limited scope can execute bubblewrap.
systemd-run --user --scope --quiet \
  --property=MemoryMax=2G --property=MemorySwapMax=0 --property=TasksMax=64 \
  bwrap --unshare-all --ro-bind / / -- /usr/bin/true
rustup which rustc
install -d -m 700 "$RUNNER_TEMP/autocoder-ci" "$RUNNER_TEMP/autocoder-ci/reports"
