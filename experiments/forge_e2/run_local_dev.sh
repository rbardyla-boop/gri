#!/usr/bin/env bash
set -euo pipefail

repo="$(git rev-parse --show-toplevel)"
cd "$repo"
remote_ref="${TE0_E2_REMOTE_REF:-refs/remotes/origin/te0-e2-gate-aware-composer}"
if ! git show-ref --verify --quiet "$remote_ref"; then
  echo "TE0_E2_REMOTE_REF_MISSING: fetch origin before running ($remote_ref)" >&2
  exit 2
fi
head_sha="$(git rev-parse HEAD)"
expected_sha="$(git rev-parse "$remote_ref")"
if [[ "$head_sha" != "$expected_sha" ]]; then
  echo "TE0_E2_HEAD_MISMATCH: HEAD=$head_sha expected=$expected_sha" >&2
  exit 2
fi
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
  echo "TE0_E2_WORKTREE_NOT_CLEAN" >&2
  git status --short >&2 || true
  exit 2
fi

run_id="te0-e2-dev-$(date -u +%Y%m%dT%H%M%SZ)"
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
summary="$scratch/TE0_E2_LOCAL_DEV_SUMMARY.json"

cleanup() {
  if [[ -n "${broker_pid:-}" ]]; then
    kill "$broker_pid" >/dev/null 2>&1 || true
    wait "$broker_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

python -B -m experiments.forge_e2.preflight_model --output "$identity"

python -B -m experiments.forge_e2.generate_te0_e2 \
  --seed-text TE0-E2-PUBLIC-BUILD-v1 --count 24 --prefix B2 --output "$build_pool"
python -B -m experiments.forge_e2.generate_te0_e2 \
  --seed-text TE0-E2-PUBLIC-DEV-v1 --count 24 --prefix D2 --output "$dev_pool"

python -B -m experiments.forge.model_broker \
  --socket "$broker_socket" --model llama3.1:8b \
  >"$broker_log" 2>&1 &
broker_pid=$!
for _ in $(seq 1 100); do
  [[ -S "$broker_socket" ]] && break
  sleep 0.1
done
if [[ ! -S "$broker_socket" ]]; then
  echo "TE0_E2_BROKER_START_FAIL" >&2
  cat "$broker_log" >&2 || true
  exit 3
fi

export FORGE_MODEL_BROKER="$broker_socket"
export FORGE_SANDBOX_BACKEND="${FORGE_SANDBOX_BACKEND:-auto}"
export FORGE_SCRATCH="$(dirname "$scratch")"

bash experiments/forge/sandbox.sh \
  python -B -m experiments.forge_e2.collect_te0_e2 \
  --phase BUILD --pool "$build_pool" --model-identity "$identity" \
  --broker-socket "$broker_socket" --output "$build_raw" --receipt "$build_receipt"

bash experiments/forge/sandbox.sh \
  python -B -m experiments.forge_e2.collect_te0_e2 \
  --phase DEV --pool "$dev_pool" --model-identity "$identity" \
  --broker-socket "$broker_socket" --output "$dev_raw" --receipt "$dev_receipt"

bash experiments/forge/sandbox.sh \
  python -B -m experiments.forge_e2.develop_te0_e2 \
  --build "$build_raw" --dev "$dev_raw" --output "$champion" --ledger "$ledger"

python - "$head_sha" "$identity" "$build_pool" "$dev_pool" "$build_raw" "$dev_raw" "$build_receipt" "$dev_receipt" "$champion" "$ledger" "$summary" <<'PY'
import hashlib, json, sys
from pathlib import Path
head = sys.argv[1]
paths = [Path(x) for x in sys.argv[2:-1]]
summary = Path(sys.argv[-1])
champion = json.loads(paths[7].read_text())
status = champion['status']
allowed = {'TE0_E2_DEVELOPMENT_CHAMPION_FROZEN','TE0_E2_REPAIR_NOT_NEEDED','TE0_E2_INTERFACE_REPAIR_FAIL'}
if status not in allowed:
    raise SystemExit(f'unknown development status: {status}')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
result = {
    'schema_version': 1,
    'unit': 'TE0-E2',
    'status': status,
    'phase': 'LOCAL_BUILD_DEV_COMPLETE',
    'source_head_sha': head,
    'vault_created': False,
    'vault_seen': False,
    'scientific_semantic_claim': False,
    'artifacts': {p.name: sha(p) for p in paths if p.exists()},
}
summary.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
print(json.dumps(result, indent=2, sort_keys=True))
PY

echo
echo "TE0-E2 BUILD/DEV complete: $scratch"
echo "Source head: $head_sha"
echo "No Vault was generated or opened."
