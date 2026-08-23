from __future__ import annotations

import argparse
import json
from pathlib import Path

from huggingface_hub import snapshot_download

REPO_ID = "phamquiluan/RCAEval"
REVISION = "92c773ab7bb79f525ec7d5dc53d96a74dbebce4d"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    resolved = snapshot_download(
        repo_id=REPO_ID,
        repo_type="dataset",
        revision=REVISION,
        # Use the dataset maintainer's documented suite-level selector.  The
        # earlier nested file glob selected zero files under huggingface_hub
        # 1.28.0.  Staging below still copies only metrics.parquet and
        # inject_time.txt into the candidate/scorer split.
        allow_patterns="re3*",
        local_dir=str(args.output),
    )
    case_count = sum(1 for _ in args.output.glob("re3*/metrics.parquet"))
    result = {
        "repo_id": REPO_ID,
        "revision": REVISION,
        "resolved_path": str(Path(resolved).resolve()),
        "metric_case_count": case_count,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if case_count != 90:
        raise SystemExit(f"expected 90 RE3 metric cases, found {case_count}")


if __name__ == "__main__":
    main()
