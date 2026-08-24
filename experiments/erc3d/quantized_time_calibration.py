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
from experiments.erc3a.channel_schema import SAMPLE_COUNT, SAMPLE_RATE_HZ, TIME_COLUMN

from .protocol import ARCHIVE_URL, EXPECTED_COLUMNS, sha256_json

INTEGER_MICROSECOND_RESIDUAL_TOLERANCE_S = 5e-13
ENDPOINT_GRID_RESIDUAL_TOLERANCE_S = 0.500001e-6
LAST_TIME_TOLERANCE_S = 5e-13


def raw_time_bytes(values: Any) -> bytes:
    return np.asarray(np.asarray(values, dtype=np.float64), dtype="<f8").tobytes(order="C")


def microsecond_counts(values: Any) -> np.ndarray:
    return np.rint(np.asarray(values, dtype=np.float64) * 1_000_000.0).astype("<i8")


def normalized_microsecond_bytes(values: Any) -> bytes:
    return microsecond_counts(values).tobytes(order="C")


def sha256_raw_time(values: Any) -> str:
    return hashlib.sha256(raw_time_bytes(values)).hexdigest()


def sha256_microsecond_vector(values: Any) -> str:
    return hashlib.sha256(normalized_microsecond_bytes(values)).hexdigest()


def _empty_timing() -> dict:
    return {
        "first_time_s": None,
        "last_time_s": None,
        "min_raw_dt_s": None,
        "median_raw_dt_s": None,
        "max_raw_dt_s": None,
        "max_integer_microsecond_residual_s": None,
        "max_endpoint_grid_residual_s": None,
        "raw_time_vector_sha256": None,
        "integer_microsecond_vector_sha256": None,
    }


def diagnose_time_vector(time_values: Any, columns: list[str]) -> tuple[dict, list[str]]:
    timing = _empty_timing()
    reasons: list[str] = []
    if len(columns) != len(EXPECTED_COLUMNS) or len(set(columns)) != len(columns) or set(columns) != set(EXPECTED_COLUMNS):
        reasons.append("exact frozen 49-name schema failed")
    try:
        values = np.asarray(time_values, dtype=np.float64)
    except Exception as exc:
        reasons.append(f"time_s numeric conversion failed: {type(exc).__name__}: {exc}")
        return timing, reasons
    if values.ndim != 1 or values.size != SAMPLE_COUNT:
        reasons.append(f"time_s length/shape failed: expected ({SAMPLE_COUNT},), got {values.shape}")
        return timing, reasons

    timing["raw_time_vector_sha256"] = sha256_raw_time(values)
    timing["first_time_s"] = float(values[0])
    timing["last_time_s"] = float(values[-1])
    if not np.isfinite(values).all():
        reasons.append("time_s contains nonfinite values")
        return timing, reasons

    intervals = np.diff(values)
    timing["min_raw_dt_s"] = float(np.min(intervals))
    timing["median_raw_dt_s"] = float(np.median(intervals))
    timing["max_raw_dt_s"] = float(np.max(intervals))
    if not np.all(intervals > 0):
        reasons.append("time_s is not strictly increasing")

    integer_counts = microsecond_counts(values)
    quantized = integer_counts.astype(np.float64) / 1_000_000.0
    timing["max_integer_microsecond_residual_s"] = float(np.max(np.abs(values - quantized)))
    timing["integer_microsecond_vector_sha256"] = hashlib.sha256(integer_counts.tobytes(order="C")).hexdigest()
    if timing["max_integer_microsecond_residual_s"] > INTEGER_MICROSECOND_RESIDUAL_TOLERANCE_S:
        reasons.append("integer-microsecond representation residual exceeds 5e-13 s")

    nominal_endpoint = (np.arange(SAMPLE_COUNT, dtype=np.float64) + 1.0) / SAMPLE_RATE_HZ
    timing["max_endpoint_grid_residual_s"] = float(np.max(np.abs(values - nominal_endpoint)))
    if timing["max_endpoint_grid_residual_s"] > ENDPOINT_GRID_RESIDUAL_TOLERANCE_S:
        reasons.append("endpoint-grid residual exceeds 0.500001 microsecond")
    if abs(float(values[-1]) - 1.0) > LAST_TIME_TOLERANCE_S:
        reasons.append("last timestamp is not 1.0 s within 5e-13 s")
    return timing, reasons


def _case_diagnostics(frame: Any) -> tuple[dict, list[str], dict]:
    timing = _empty_timing()
    reasons: list[str] = []
    meta = {"object_type": type(frame).__name__, "shape": None, "columns": None}
    if not isinstance(frame, pd.DataFrame):
        return timing, ["payload object is not a pandas DataFrame"], meta
    meta["shape"] = list(frame.shape)
    meta["columns"] = [str(column) for column in frame.columns]
    if tuple(frame.shape) != (SAMPLE_COUNT, len(EXPECTED_COLUMNS)):
        reasons.append(f"DataFrame shape failed: expected {(SAMPLE_COUNT, len(EXPECTED_COLUMNS))}, got {tuple(frame.shape)}")
    if TIME_COLUMN not in frame.columns:
        reasons.append("time_s column is missing")
        return timing, reasons, meta
    try:
        values = pd.to_numeric(frame[TIME_COLUMN], errors="raise").to_numpy(dtype=np.float64)
    except Exception as exc:
        reasons.append(f"time_s numeric conversion failed: {type(exc).__name__}: {exc}")
        return timing, reasons, meta
    timing, timing_reasons = diagnose_time_vector(values, meta["columns"])
    reasons.extend(timing_reasons)
    return timing, reasons, meta


def run_calibration(*, calibration_map_path: Path, index_path: Path, output_dir: Path) -> dict:
    calibration_map = json.loads(calibration_map_path.read_text(encoding="utf-8"))
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if len(calibration_map) != 8:
        raise ValueError("calibration map must contain exactly 8 cases")
    if index.get("selected_member_count") != 72:
        raise ValueError("index must contain exactly 72 selected members")
    by_opaque = {row["opaque_id"]: row for row in index["selected_members"]}
    if len(by_opaque) != 72:
        raise ValueError("duplicate opaque IDs in index")

    output_dir.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []
    opened = 0
    for acquisition_row in calibration_map:
        opaque = acquisition_row["opaque_id"]
        index_row = by_opaque.get(opaque)
        if index_row is None or index_row.get("role") != "calibration":
            raise ValueError(f"calibration/index binding missing for {opaque}")
        opened += 1
        case = {
            "opaque_id": opaque,
            "payload_sha256": None,
            "object_type": None,
            "shape": None,
            "columns": None,
            "timing": _empty_timing(),
            "status": "FAIL",
            "reasons": [],
        }
        try:
            acquired = acquire_member(archive_url=ARCHIVE_URL, acquisition_row=acquisition_row, index_row=index_row)
            case["payload_sha256"] = acquired.payload_sha256
            frame = pd.read_pickle(io.BytesIO(acquired.payload))
            timing, reasons, meta = _case_diagnostics(frame)
            case["object_type"] = meta["object_type"]
            case["shape"] = meta["shape"]
            case["columns"] = meta["columns"]
            case["timing"] = timing
            case["status"] = "PASS" if not reasons else "FAIL"
            case["reasons"] = reasons or ["all frozen quantized-time rules passed"]
        except Exception as exc:
            case["reasons"] = [f"{type(exc).__name__}: {exc}"]
        cases.append(case)

    raw_hashes = {case["timing"]["raw_time_vector_sha256"] for case in cases if case["timing"]["raw_time_vector_sha256"]}
    micro_hashes = {case["timing"]["integer_microsecond_vector_sha256"] for case in cases if case["timing"]["integer_microsecond_vector_sha256"]}
    cross_case_reasons: list[str] = []
    if len(raw_hashes) != 1:
        cross_case_reasons.append(f"expected one common raw time-vector SHA, got {len(raw_hashes)}")
    if len(micro_hashes) != 1:
        cross_case_reasons.append(f"expected one common integer-microsecond SHA, got {len(micro_hashes)}")
    if cross_case_reasons:
        for case in cases:
            case["status"] = "FAIL"
            case["reasons"].extend(cross_case_reasons)

    status = "ERC3D_QUANTIZED_TIME_QUALIFICATION_PASS" if opened == 8 and not cross_case_reasons and all(case["status"] == "PASS" for case in cases) else "ERC3D_QUANTIZED_TIME_QUALIFICATION_FAIL"
    contract = {
        "unit": "ERC-3D",
        "status": status,
        "calibration_case_count": 8,
        "calibration_waveforms_opened": opened,
        "science_waveforms_opened": 0,
        "science_signal_columns_read": 0,
        "scientific_predictions": 0,
        "scorer_opened": False,
        "same_set_rescue_authorized": False,
        "integer_microsecond_definition": "little-endian signed int64 counts of rint(time_s*1e6)",
        "common_raw_time_vector_sha256": sorted(raw_hashes),
        "common_integer_microsecond_vector_sha256": sorted(micro_hashes),
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
    }
    contract["contract_sha256"] = sha256_json(contract)
    receipt = {
        "unit": "ERC-3D",
        "status": status,
        "cases": cases,
        "calibration_waveforms_opened": opened,
        "science_waveforms_opened": 0,
        "science_signal_columns_read": 0,
        "scientific_predictions": 0,
        "scorer_opened": False,
        "same_set_rescue_authorized": False,
    }
    receipt["receipt_sha256"] = sha256_json(receipt)
    (output_dir / "ERC3D_QUANTIZED_TIME_CONTRACT.json").write_text(json.dumps(contract, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (output_dir / "ERC3D_QUANTIZED_TIME_CALIBRATION_RECEIPT.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(contract, sort_keys=True, indent=2))
    return contract


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibration-map", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    contract = run_calibration(calibration_map_path=args.calibration_map, index_path=args.index, output_dir=args.output_dir)
    if contract["status"] != "ERC3D_QUANTIZED_TIME_QUALIFICATION_PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
