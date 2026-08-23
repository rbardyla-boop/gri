#!/usr/bin/env bash
set -euo pipefail

# FORGE / TE0 local sandbox launcher.
# Runtime network is disabled. The repo is read-only. Only scratch is writable.
# This is a containment aid for bounded research tooling, not a proof against
# kernel/container escapes or hostile native code.

repo="$(git rev-parse --show-toplevel)"
scratch="${FORGE_SCRATCH:-$repo/.forge-scratch}"
image="${FORGE_IMAGE:-python:3.11-slim}"
requested_backend="${FORGE_SANDBOX_BACKEND:-auto}"
mkdir -p "$scratch"
repo="$(readlink -f "$repo")"
scratch="$(readlink -f "$scratch")"

broker=""
if [[ -n "${FORGE_MODEL_BROKER:-}" ]]; then
  broker="$(readlink -f "$FORGE_MODEL_BROKER")"
  case "$broker" in
    "$scratch"/*) ;;
    *)
      echo "FORGE_BROKER_OUTSIDE_SCRATCH: $broker" >&2
      exit 4
      ;;
  esac
  if [[ ! -S "$broker" ]]; then
    echo "FORGE_BROKER_SOCKET_MISSING: $broker" >&2
    exit 5
  fi
fi

bwrap_usable() {
  command -v bwrap >/dev/null 2>&1 || return 1
  bwrap \
    --die-with-parent \
    --new-session \
    --unshare-user \
    --unshare-pid \
    --unshare-uts \
    --unshare-ipc \
    --unshare-net \
    --ro-bind / / \
    --proc /proc \
    --dev /dev \
    --tmpfs /tmp \
    -- /usr/bin/true >/dev/null 2>&1
}

backend=""
case "$requested_backend" in
  auto)
    if bwrap_usable; then
      backend=bwrap
    elif command -v podman >/dev/null 2>&1; then
      backend=podman
    elif command -v docker >/dev/null 2>&1; then
      backend=docker
    else
      echo "FORGE_SANDBOX_UNAVAILABLE: install bubblewrap, rootless Podman, or Docker" >&2
      exit 2
    fi
    ;;
  bwrap)
    if ! bwrap_usable; then
      echo "FORGE_BWRAP_UNAVAILABLE_OR_UNUSABLE" >&2
      exit 2
    fi
    backend=bwrap
    ;;
  podman|docker)
    if ! command -v "$requested_backend" >/dev/null 2>&1; then
      echo "FORGE_SANDBOX_BACKEND_MISSING: $requested_backend" >&2
      exit 2
    fi
    backend="$requested_backend"
    ;;
  *)
    echo "FORGE_UNKNOWN_SANDBOX_BACKEND: $requested_backend" >&2
    exit 2
    ;;
esac

if [[ $# -eq 0 ]]; then
  run_id="te0-e0-$(date -u +%Y%m%dT%H%M%SZ)-$$"
  if [[ "$backend" == bwrap ]]; then
    set -- python -B -m experiments.forge.qualify_te0_e0 --scratch "$scratch/$run_id"
  else
    set -- python -B -m experiments.forge.qualify_te0_e0 --scratch "/scratch/$run_id"
  fi
fi

if [[ "$backend" == bwrap ]]; then
  # Root is read-only. Rebind only scratch writable at the same absolute path.
  # No RLIMIT_NPROC is used: on a desktop it is charged against the host UID
  # and can break namespace creation before the sandbox exists.
  args=(
    --die-with-parent
    --new-session
    --unshare-user
    --unshare-pid
    --unshare-uts
    --unshare-ipc
    --unshare-net
    --ro-bind / /
    --bind "$scratch" "$scratch"
    --proc /proc
    --dev /dev
    --tmpfs /tmp
    --chdir "$repo"
    --setenv PYTHONDONTWRITEBYTECODE 1
    --setenv PYTHONHASHSEED 0
  )
  if [[ -n "$broker" ]]; then
    # Socket is reachable only because its parent scratch directory is the
    # single writable bind. There is still no IP network inside the sandbox.
    args+=(--setenv FORGE_MODEL_BROKER "$broker")
  fi
  exec bwrap "${args[@]}" -- "$@"
fi

# Container backends. Fail closed: do not pull an image during a run.
if ! "$backend" image inspect "$image" >/dev/null 2>&1; then
  echo "FORGE_IMAGE_MISSING: pre-pull '$image' outside the experiment, then rerun" >&2
  exit 3
fi

args=(
  run --rm
  --pull=never
  --network=none
  --read-only
  --cap-drop=ALL
  --security-opt=no-new-privileges
  --pids-limit=128
  --memory="${FORGE_MEMORY:-4g}"
  --cpus="${FORGE_CPUS:-4}"
  --tmpfs=/tmp:rw,nosuid,nodev,noexec,size=512m
  --mount="type=bind,src=$repo,dst=/repo,ro"
  --mount="type=bind,src=$scratch,dst=/scratch,rw"
  --env=PYTHONDONTWRITEBYTECODE=1
  --env=PYTHONHASHSEED=0
  -w /repo
)

if [[ -n "$broker" ]]; then
  container_broker="/scratch/${broker#"$scratch"/}"
  args+=(--env="FORGE_MODEL_BROKER=$container_broker")
fi

if [[ "$backend" == podman ]]; then
  args+=(--userns=keep-id)
fi

exec "$backend" "${args[@]}" "$image" "$@"
