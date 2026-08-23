from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ID = "phamquiluan/RCAEval"
REVISION = "afeacb11bcc94dadfd1c8f483ee4377b2b8b614e"
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


def case_directory(path: str) -> str:
    return path.rsplit("/", 1)[0]


def validate_inventory(metric_paths: list[str], inject_paths: list[str]) -> None:
    metric_cases = {case_directory(path) for path in metric_paths}
    inject_cases = {case_directory(path) for path in inject_paths}
    if len(metric_paths) != EXPECTED_CASES or len(inject_paths) != EXPECTED_CASES:
        raise ValueError(
            "pinned RE3 inventory mismatch: "
            f"metrics={len(metric_paths)} inject_time={len(inject_paths)}"
        )
    if metric_cases != inject_cases or len(metric_cases) != EXPECTED_CASES:
        missing_inject = sorted(metric_cases - inject_cases)
        missing_metrics = sorted(inject_cases - metric_cases)
        raise ValueError(
            "pinned RE3 case pairing mismatch: "
            f"metric_cases={len(metric_cases)} inject_cases={len(inject_cases)} "
            f"missing_inject={len(missing_inject)} missing_metrics={len(missing_metrics)}"
        )


def main() -> None:
    # Runtime-only dependency. The pure inventory selector and validator remain
    # testable in the pre-data qualification environment without network code.
    from huggingface_hub import HfApi, hf_hub_download

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    # Enumerate the exact MCO-04-pinned data-bearing revision, assert the full
    # RE3 metric/timestamp inventory, then download only those explicit files.
    api = HfApi()
    repo_files = api.list_repo_files(
        repo_id=REPO_ID,
        repo_type="dataset",
        revision=REVISION,
    )
    metric_paths, inject_paths = required_paths(repo_files)
    try:
        validate_inventory(metric_paths, inject_paths)
    except ValueError as exc:
        raise SystemExit(f"ERC1B_DATA_BINDING_INVALID_PRE_PREDICTION: {exc}") from exc

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
        "unit": "ERC-1B",
        "status": "ERC1B_DATA_INVENTORY_DOWNLOADED",
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
            "ERC1B_DATA_BINDING_INVALID_PRE_PREDICTION: "
            f"downloaded metrics={case_count} inject_time={inject_count}"
        )


if __name__ == "__main__":
    main()
