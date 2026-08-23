from __future__ import annotations

import argparse
import json
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

REPO_ID = "phamquiluan/RCAEval"
REVISION = "92c773ab7bb79f525ec7d5dc53d96a74dbebce4d"
EXPECTED_CASES = 90


def required_paths(repo_files: list[str]) -> tuple[list[str], list[str]]:
    metrics = sorted(
        path
        for path in repo_files
        if path.startswith("re3") and path.endswith("/metrics.parquet")
    )
    inject = sorted(
        path
        for path in repo_files
        if path.startswith("re3") and path.endswith("/inject_time.txt")
    )
    return metrics, inject


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    # Avoid glob/filter semantics entirely.  Enumerate the exact pinned
    # revision, assert the expected RE3 inventory, then download only those
    # explicit metric and injection-time files.
    api = HfApi()
    repo_files = api.list_repo_files(
        repo_id=REPO_ID,
        repo_type="dataset",
        revision=REVISION,
    )
    metric_paths, inject_paths = required_paths(repo_files)
    if len(metric_paths) != EXPECTED_CASES or len(inject_paths) != EXPECTED_CASES:
        raise SystemExit(
            "pinned RE3 inventory mismatch: "
            f"metrics={len(metric_paths)} inject_time={len(inject_paths)}"
        )

    selected = metric_paths + inject_paths
    for filename in selected:
        hf_hub_download(
            repo_id=REPO_ID,
            repo_type="dataset",
            revision=REVISION,
            filename=filename,
            local_dir=str(args.output),
        )

    case_count = sum(1 for _ in args.output.glob("re3*/metrics.parquet"))
    inject_count = sum(1 for _ in args.output.glob("re3*/inject_time.txt"))
    result = {
        "repo_id": REPO_ID,
        "revision": REVISION,
        "resolved_path": str(args.output.resolve()),
        "repo_file_count": len(repo_files),
        "selected_file_count": len(selected),
        "metric_case_count": case_count,
        "inject_time_count": inject_count,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if case_count != EXPECTED_CASES or inject_count != EXPECTED_CASES:
        raise SystemExit(
            f"expected {EXPECTED_CASES} RE3 cases, "
            f"found metrics={case_count} inject_time={inject_count}"
        )


if __name__ == "__main__":
    main()
