#!/usr/bin/env bash
set -euo pipefail

# FORGE / TE0 local sandbox launcher.
# Runtime network is disabled. The repo is mounted read-only. Only /scratch is writable.
# This is a containment aid for bounded research tooling, not a proof against kernel/container escapes.

repo="$(git rev-parse --show-toplevel)"
scratch="${FORGE_SCRATCH:-$repo/.forge-scratch}"
image="${FORGE_IMAGE:-python:3.11-slim}"
mkdir -p "$scratch"

engine=""
if command -v podman >/dev/null 2>&1; then
  engine=podman
elif command -v docker >/dev/null 2>&1; then
  engine=docker
else
  echo "FORGE_SANDBOX_UNAVAILABLE: install rootless Podman or Docker" >&2
  exit 2
fi

# Fail closed: do not pull an image during a scientific/development run.
if ! "$engine" image inspect "$image" >/dev/null 2>&1; then
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

# Optional narrow local-model capability. The broker socket must live inside
# the already-mounted scratch directory; the sandbox still receives no IP
# network. The host-side broker validates model name/request schema and only
# forwards approved /api/chat requests to local Ollama.
if [[ -n "${FORGE_MODEL_BROKER:-}" ]]; then
  broker="$(readlink -f "$FORGE_MODEL_BROKER")"
  scratch_real="$(readlink -f "$scratch")"
  case "$broker" in
    "$scratch_real"/*) ;;
    *)
      echo "FORGE_BROKER_OUTSIDE_SCRATCH: $broker" >&2
      exit 4
      ;;
  esac
  if [[ ! -S "$broker" ]]; then
    echo "FORGE_BROKER_SOCKET_MISSING: $broker" >&2
    exit 5
  fi
  container_broker="/scratch/${broker#"$scratch_real"/}"
  args+=(--env="FORGE_MODEL_BROKER=$container_broker")
fi

if [[ "$engine" == podman ]]; then
  args+=(--userns=keep-id)
fi

if [[ $# -eq 0 ]]; then
  run_id="te0-e0-$(date -u +%Y%m%dT%H%M%SZ)-$$"
  set -- python -B -m experiments.forge.qualify_te0_e0 --scratch "/scratch/$run_id"
fi

exec "$engine" "${args[@]}" "$image" "$@"
