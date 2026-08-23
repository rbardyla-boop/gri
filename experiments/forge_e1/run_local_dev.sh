#!/usr/bin/env bash
set -euo pipefail

repo="$(git rev-parse --show-toplevel)"
cd "$repo"

expected_branch="te0-e1-interface-repair"
branch="$(git branch --show-current)"
if [[ "$branch" != "$expected_branch" ]]; then
  echo "TE0_E1_WRONG_BRANCH: expected $expected_branch, got $branch" >&2
  exit 2
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "TE0_E1_WORKTREE_NOT_CLEAN" >&2
  exit 2
fi
if ! command -v bwrap >/dev/null 2>&1; then
  echo "TE0_E1_BWRAP_REQUIRED" >&2
  exit 2
fi

run_id="te0-e1-dev-$(date -u +%Y%m%dT%H%M%SZ)"
scratch="${FORGE_SCRATCH:-$repo/.forge-scratch}/$run_id"
mkdir -p "$scratch"
scratch="$(readlink -f "$scratch")"

identity="$scratch/model-identity.json"
build_pool="$scratch/build-pool.jsonl"
dev_pool="$scratch/dev-pool.jsonl"
build_raw="$scratch/build-raw.jsonl"
dev_raw="$scratch/dev-raw.jsonl"
build_receipt="$scratch/build-collection.json"
dev_receipt="$scratch/dev-collection.json"
champion="$scratch/development-champion.json"
ledger="$scratch/ledger.jsonl"
broker_socket="$scratch/model-broker.sock"
broker_log="$scratch/model-broker.log"
summary="$scratch/TE0_E1_LOCAL_DEV_SUMMARY.json"

cleanup() {
  if [[ -n "${broker_pid:-}" ]]; then
    kill "$broker_pid" >/dev/null 2>&1 || true
    wait "$broker_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

python -B -m experiments.forge_e1.preflight_model \
  --output "$identity"

python -B -m experiments.forge_e1.generate_te0_e1 \
  --seed-text TE0-E1-PUBLIC-BUILD-v1 \
  --count 24 --prefix B \
  --output "$build_pool"
python -B -m experiments.forge_e1.generate_te0_e1 \
  --seed-text TE0-E1-PUBLIC-DEV-v1 \
  --count 24 --prefix D \
  --output "$dev_pool"

python -B -m experiments.forge.model_broker \
  --socket "$broker_socket" \
  --model llama3.1:8b \
  >"$broker_log" 2>&1 &
broker_pid=$!

for _ in $(seq 1 100); do
  [[ -S "$broker_socket" ]] && break
  sleep 0.1
done
if [[ ! -S "$broker_socket" ]]; then
  echo "TE0_E1_BROKER_START_FAIL" >&2
  cat "$broker_log" >&2 || true
  exit 3
fi

export FORGE_MODEL_BROKER="$broker_socket"
export FORGE_SANDBOX_BACKEND=bwrap
export FORGE_SCRATCH="$(dirname "$scratch")"

bash experiments/forge/sandbox.sh \
  python -B -m experiments.forge_e1.collect_te0_e1 \
  --phase BUILD \
  --pool "$build_pool" \
  --model-identity "$identity" \
  --broker-socket "$broker_socket" \
  --output "$build_raw" \
  --receipt "$build_receipt"

bash experiments/forge/sandbox.sh \
  python -B -m experiments.forge_e1.collect_te0_e1 \
  --phase DEV \
  --pool "$dev_pool" \
  --model-identity "$identity" \
  --broker-socket "$broker_socket" \
  --output "$dev_raw" \
  --receipt "$dev_receipt"

bash experiments/forge/sandbox.sh \
  python -B -m experiments.forge_e1.develop_te0_e1 \
  --build "$build_raw" \
  --dev "$dev_raw" \
  --output "$champion" \
  --ledger "$ledger"

python - "$identity" "$build_pool" "$dev_pool" "$build_raw" "$dev_raw" "$build_receipt" "$dev_receipt" "$champion" "$ledger" "$summary" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

paths = [Path(x) for x in sys.argv[1:-1]]
summary_path = Path(sys.argv[-1])
champion = json.loads(paths[7].read_text())
status = champion['status']
if status not in {
    'TE0_E1_DEVELOPMENT_CHAMPION_FROZEN',
    'TE0_E1_REPAIR_NOT_NEEDED',
    'TE0_E1_INTERFACE_REPAIR_FAIL',
}:
    raise SystemExit(f'unknown development status: {status}')

def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

result = {
    'schema_version': 1,
    'unit': 'TE0-E1',
    'status': status,
    'phase': 'LOCAL_BUILD_DEV_COMPLETE',
    'vault_created': False,
    'vault_seen': False,
    'scientific_semantic_claim': False,
    'artifacts': {p.name: sha(p) for p in paths if p.exists()},
}
summary_path.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
print(json.dumps(result, indent=2, sort_keys=True))
PY

echo
echo "TE0-E1 BUILD/DEV complete: $scratch"
echo "No Vault was generated or opened."
