from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ERC3A_ROOT = REPO_ROOT / "experiments" / "erc3a"
PROTOCOL_PATH = REPO_ROOT / "docs" / "ERC3A-PROTECT90-ONSET-PRECEDENCE.md"
RUNTIME_BINDING = {
    "python": "3.11.16",
    "numpy": "2.2.6",
    "pandas": "2.3.2",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def _file_hashes(paths: list[Path]) -> dict[str, str]:
    result = {}
    for path in sorted(set(paths)):
        if not path.is_file():
            raise FileNotFoundError(path)
        try:
            label = str(path.relative_to(REPO_ROOT))
        except ValueError:
            label = f"external/{path.name}"
        result[label] = sha256_file(path)
    return result


def build_candidate(
    *,
    output: Path,
    scorer_map: Path | None = None,
    index: Path | None = None,
) -> dict:
    source_files = sorted(ERC3A_ROOT.glob("*.py"))
    test_files = [REPO_ROOT / "tests" / "test_erc3a_prelive.py"]
    workflow_files = sorted((REPO_ROOT / ".github" / "workflows").glob("erc3a*.yml"))
    selection_files = [
        ERC3A_ROOT / "ERC3A_PUBLIC_SELECTION.json",
        ERC3A_ROOT / "ERC3A_ACQUISITION_MAP.json",
        ERC3A_ROOT / "ERC3A_METADATA_SELECTION_RECORD.json",
        ERC3A_ROOT / "ERC3A_PRODUCER_MANIFEST.json",
    ]
    if index is not None:
        selection_files.append(index)
    hashes = {
        "protocol": _file_hashes([PROTOCOL_PATH]),
        "executable_source": _file_hashes(source_files + test_files),
        "workflow": _file_hashes(workflow_files),
        "selection_and_bindings": _file_hashes(selection_files),
        "acquisition_mapping_rule": _file_hashes([ERC3A_ROOT / "acquire_member.py"]),
        "payload_bridge": _file_hashes([ERC3A_ROOT / "stage_waveforms.py"]),
        "producer_manifest_rule": _file_hashes([ERC3A_ROOT / "manifest.py"]),
        "batch_runner": _file_hashes([ERC3A_ROOT / "run_batch.py"]),
        "scorer": _file_hashes([ERC3A_ROOT / "scoring.py"]),
        "locator": _file_hashes([ERC3A_ROOT / "locator.py"]),
    }
    if scorer_map is not None:
        hashes["scorer_map_receipt"] = _file_hashes([scorer_map])

    candidate = {
        "unit": "ERC-3A",
        "status": "ERC3A_PRELIVE_FREEZE_CANDIDATE_READY",
        "runtime_binding": RUNTIME_BINDING,
        "waveform_archive_downloaded": False,
        "waveform_members_opened": 0,
        "selected_member_payload_bytes_read": 0,
        "scientific_predictions": 0,
        "same_set_rescue_authorized": False,
        "real_waveform_episodes_executed": 0,
        "synthetic_fixture_predictions_only": True,
        "hashes": hashes,
    }
    candidate["freeze_candidate_sha256"] = hashlib.sha256(canonical_bytes(candidate)).hexdigest()
    output.write_text(json.dumps(candidate, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scorer-map", type=Path)
    parser.add_argument("--index", type=Path)
    args = parser.parse_args()
    result = build_candidate(
        output=args.output,
        scorer_map=args.scorer_map.resolve() if args.scorer_map else None,
        index=args.index.resolve() if args.index else None,
    )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
