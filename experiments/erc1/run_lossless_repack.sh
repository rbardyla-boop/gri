#!/usr/bin/env bash
set -euo pipefail

repo="$(git rev-parse --show-toplevel)"
cd "$repo"
branch="erc1-mco04-cleanroom"
revision="92c773ab7bb79f525ec7d5dc53d96a74dbebce4d"

git fetch -q origin "$branch"
head="$(git rev-parse HEAD)"
remote="$(git rev-parse "refs/remotes/origin/$branch")"
if [[ "$head" != "$remote" ]]; then
  echo "STOP: HEAD $head != origin/$branch $remote" >&2
  exit 2
fi
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
  echo "STOP: worktree is not clean" >&2
  git status --short >&2
  exit 2
fi

python - <<'PY'
import importlib
for name in ("numpy", "pandas", "pyarrow", "huggingface_hub"):
    importlib.import_module(name)
print("ERC1_DEPENDENCIES_OK")
PY

cache_root="${ERC1_CACHE_ROOT:-$HOME/.cache/gri-erc1}"
data_root="${ERC1_DATA_ROOT:-$cache_root/rcaeval-re3-$revision}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
run_root="$cache_root/runs/$stamp"
mkdir -p "$run_root"

case_count="$(find "$data_root" -mindepth 2 -maxdepth 2 -name metrics.parquet 2>/dev/null | wc -l | tr -d ' ')"
if [[ "$case_count" != "90" ]]; then
  rm -rf "$data_root"
  python -m experiments.erc1.download_lossless_repack --output "$data_root"
fi

python -m experiments.erc1.stage \
  --data-root "$data_root" \
  --output-root "$run_root/staged" \
  --evidence-class LOSSLESS_REPACK_REPRODUCTION \
  --source-revision "$revision" \
  | tee "$run_root/STAGE_STDOUT.txt"

python -m experiments.erc1.compiler \
  --candidate-dir "$run_root/staged/candidate" \
  --output "$run_root/PREDICTIONS_LIVE.json" \
  | tee "$run_root/LIVE_STDOUT.txt"

python -m experiments.erc1.compiler \
  --candidate-dir "$run_root/staged/candidate" \
  --output "$run_root/PREDICTIONS_REPLAY.json" \
  | tee "$run_root/REPLAY_STDOUT.txt"

if ! cmp -s "$run_root/PREDICTIONS_LIVE.json" "$run_root/PREDICTIONS_REPLAY.json"; then
  echo "STOP: deterministic replay bytes differ" >&2
  sha256sum "$run_root/PREDICTIONS_LIVE.json" "$run_root/PREDICTIONS_REPLAY.json" >&2
  exit 3
fi

echo "ERC1_REPLAY_BYTES_IDENTICAL"

python -m experiments.erc1.score \
  --staging-root "$run_root/staged" \
  --live "$run_root/PREDICTIONS_LIVE.json" \
  --replay "$run_root/PREDICTIONS_REPLAY.json" \
  --output "$run_root/ERC1_REPRODUCTION_REPORT.json" \
  | tee "$run_root/SCORE_STDOUT.txt"

python - "$run_root/ERC1_REPRODUCTION_REPORT.json" <<'PY'
import json, sys
p = json.load(open(sys.argv[1]))
print()
print("=== ERC-1 TERMINAL SUMMARY ===")
print("status:", p["status"])
print("evidence_class:", p["evidence_class"])
print("source_revision:", p["source_revision"])
print("replay_exact:", p["replay_exact"])
print("opacity_provenance_ok:", p["opacity_provenance_ok"])
print("scientific:", {k:v for k,v in p["scientific"].items() if k != "disagreements"} if p.get("scientific") else None)
print("disagreements:", p.get("scientific", {}).get("disagreements") if p.get("scientific") else None)
print("prediction_seal_sha256:", p["prediction_seal_sha256"])
print("record_sha256:", p["record_sha256"])
PY

echo "ERC1_RUN_ROOT=$run_root"
