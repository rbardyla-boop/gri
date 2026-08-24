from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from experiments.erc3a.acquire_member import acquire_member
from experiments.erc3a.channel_schema import CHANNEL_SCHEMA, SAMPLE_COUNT, SAMPLE_RATE_HZ, TIME_COLUMN

from .protocol import ARCHIVE_URL, canonical_json, expected_columns, sha256_json


class TimebaseQualificationError(ValueError):
    pass


def canonical_time_vector_sha256(time_values: Any) -> str:
    values = np.asarray(time_values, dtype=np.float64)
    little_endian = np.asarray(values, dtype="<f8")
    return hashlib.sha256(little_endian.tobytes(order="C")).hexdigest()


def _schema_error(columns: list[str]) -> str:
    return f"column schema mismatch: expected {len(expected_columns())} frozen names, got {len(columns)}"


def qualify_time_vector(time_values: Any, columns: list[str]) -> dict:
    """Apply the preregistered time-axis contract without accessing signal columns."""

    frozen = set(expected_columns())
    if len(columns) != len(frozen) or len(set(columns)) != len(columns) or set(columns) != frozen:
        raise TimebaseQualificationError(_schema_error(columns))
    values = np.asarray(time_values, dtype=np.float64)
    if values.ndim != 1 or len(values) != SAMPLE_COUNT:
        raise TimebaseQualificationError(f"time vector length must be {SAMPLE_COUNT}")
    if not np.isfinite(values).all():
        raise TimebaseQualificationError("time vector contains nonfinite values")
    if not np.all(np.diff(values) > 0):
        raise TimebaseQualificationError("time vector is not strictly increasing")
    if abs(float(values[0])) > 1e-9:
        raise TimebaseQualificationError("time vector does not start at zero")
    intervals = np.diff(values)
    median_dt = float(np.median(intervals))
    if not np.isfinite(median_dt) or median_dt <= 0:
        raise TimebaseQualificationError("time vector median interval is not positive")
    rate_hz = 1.0 / median_dt
    if not 6390.0 <= rate_hz <= 6410.0:
        raise TimebaseQualificationError(f"time vector rate is outside 6390-6410 Hz: {rate_hz}")
    max_abs_interval_deviation = float(np.max(np.abs(intervals - median_dt)))
    if max_abs_interval_deviation > 1e-9:
        raise TimebaseQualificationError(
            f"time vector interval jitter exceeds 1e-9 s: {max_abs_interval_deviation}"
        )
    return {
        "sample_count": int(values.size),
        "first_time_s": float(values[0]),
        "last_time_s": float(values[-1]),
        "median_interval_s": median_dt,
        "effective_rate_hz": rate_hz,
        "max_abs_interval_deviation_s": max_abs_interval_deviation,
        "canonical_time_vector_sha256": canonical_time_vector_sha256(values),
    }


def qualify_dataframe(frame: Any) -> dict:
    """Inspect only DataFrame metadata and the time_s column.

    In particular, this function deliberately never indexes any current or
    voltage column.  The calibration gate cannot compute a signal statistic.
    """

    if not isinstance(frame, pd.DataFrame):
        raise TimebaseQualificationError("payload object is not a pandas DataFrame")
    columns = [str(column) for column in frame.columns]
    if tuple(frame.shape) != (SAMPLE_COUNT, len(expected_columns())):
        raise TimebaseQualificationError(f"DataFrame shape must be {(SAMPLE_COUNT, len(expected_columns()))}")
    # This is the only column access in the calibration layer.
    time_values = pd.to_numeric(frame[TIME_COLUMN], errors="raise").to_numpy(dtype=np.float64)
    return qualify_time_vector(time_values, columns)


def event_index(time_values: Any, t_evnt_start: float) -> int:
    """Frozen post-calibration event alignment rule."""

    values = np.asarray(time_values, dtype=np.float64)
    return int(np.searchsorted(values, float(t_evnt_start), side="left"))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run_calibration(
    *,
    calibration_map_path: Path,
    index_path: Path,
    output_dir: Path,
) -> dict:
    calibration_map = _load_json(calibration_map_path)
    index = _load_json(index_path)
    if len(calibration_map) != 8:
        raise ValueError("calibration map must contain exactly 8 cases")
    if index["selected_member_count"] != 72:
        raise ValueError("ERC-3B index must bind 8 calibration and 64 science members")
    by_opaque = {row["opaque_id"]: row for row in index["selected_members"]}
    if len(by_opaque) != 72:
        raise ValueError("duplicate opaque IDs in acquisition index")

    output_dir.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []
    attempted = 0
    for acquisition_row in calibration_map:
        opaque = acquisition_row["opaque_id"]
        index_row = by_opaque.get(opaque)
        if index_row is None or index_row.get("role") != "calibration":
            raise ValueError(f"calibration/index binding missing for {opaque}")
        attempted += 1
        case: dict = {"opaque_id": opaque, "payload_sha256": None, "status": "FAIL"}
        try:
            acquired = acquire_member(
                archive_url=ARCHIVE_URL,
                acquisition_row=acquisition_row,
                index_row=index_row,
            )
            case["payload_sha256"] = acquired.payload_sha256
            frame = pd.read_pickle(io.BytesIO(acquired.payload))
            case["object_type"] = type(frame).__name__
            case["shape"] = list(frame.shape) if hasattr(frame, "shape") else None
            case["columns"] = [str(column) for column in frame.columns] if isinstance(frame, pd.DataFrame) else None
            case["time_axis"] = qualify_dataframe(frame)
            case["status"] = "PASS"
        except Exception as exc:  # Preserve all eight calibration attempts in the receipt.
            case["error_type"] = type(exc).__name__
            case["error"] = str(exc)
        cases.append(case)

    passed = [case for case in cases if case["status"] == "PASS"]
    errors: list[str] = []
    if attempted != 8:
        errors.append(f"calibration attempts {attempted} != 8")
    if len(passed) != 8:
        errors.append(f"qualified calibration cases {len(passed)} != 8")
    hashes = {case["time_axis"]["canonical_time_vector_sha256"] for case in passed}
    if len(hashes) != 1:
        errors.append(f"calibration time-vector hash count {len(hashes)} != 1")

    summary = None
    if len(passed) == 8 and len(hashes) == 1:
        summaries = [case["time_axis"] for case in passed]
        summary = summaries[0]
        if any(item != summary for item in summaries[1:]):
            errors.append("calibration time-axis summaries are not identical")

    status = "ERC3B_TIMEBASE_QUALIFICATION_PASS" if not errors else "ERC3B_TIMEBASE_QUALIFICATION_FAIL"
    contract = {
        "unit": "ERC-3B",
        "status": status,
        "calibration_case_count": 8,
        "calibration_waveforms_opened": attempted,
        "scientific_waveforms_opened": 0,
        "waveform_members_opened": attempted,
        "scientific_predictions": 0,
        "scorer_opened": False,
        "archive_payload_access_scope": "calibration-members-only",
        "time_axis_contract": {
            "shape": [SAMPLE_COUNT, 49],
            "columns": "exact frozen set: time_s + 48 channels; source order irrelevant",
            "finite": True,
            "strictly_increasing": True,
            "first_time_tolerance_s": 1e-9,
            "rate_interval_hz": [6390.0, 6410.0],
            "max_interval_deviation_tolerance_s": 1e-9,
            "all_calibration_vectors_byte_identical": len(hashes) == 1 and len(passed) == 8,
            "canonical_encoding": "little-endian IEEE-754 float64 contiguous bytes",
        },
        "qualified_time_axis_summary": summary,
        "errors": errors,
        "same_set_rescue_authorized": False,
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    }
    contract["contract_sha256"] = sha256_json(contract)
    receipt = {
        "unit": "ERC-3B",
        "status": status,
        "cases": cases,
        "calibration_ids_are_opaque_only": True,
        "scientific_predictions": 0,
        "scorer_opened": False,
        "same_set_rescue_authorized": False,
    }
    receipt["receipt_sha256"] = sha256_json(receipt)
    (output_dir / "ERC3B_TIMEBASE_CONTRACT.json").write_text(
        json.dumps(contract, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "ERC3B_TIMEBASE_CALIBRATION_RECEIPT.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(contract, sort_keys=True, indent=2))
    return contract


def main() -> None:
    parser = argparse.ArgumentParser(description="Qualify ERC-3B time_s using calibration members only")
    parser.add_argument("--calibration-map", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    contract = run_calibration(
        calibration_map_path=args.calibration_map,
        index_path=args.index,
        output_dir=args.output_dir,
    )
    if contract["status"] != "ERC3B_TIMEBASE_QUALIFICATION_PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
