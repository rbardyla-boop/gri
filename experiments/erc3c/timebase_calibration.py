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

from .protocol import ARCHIVE_URL, EXPECTED_COLUMNS, canonical_json, sha256_json


class TimebaseQualificationError(ValueError):
    pass


def _little_endian_bytes(values: Any) -> bytes:
    array = np.asarray(values, dtype=np.float64)
    return np.asarray(array, dtype="<f8").tobytes(order="C")


def vector_sha256(values: Any) -> str:
    return hashlib.sha256(_little_endian_bytes(values)).hexdigest()


def _empty_summary() -> dict:
    return {
        "first_time_s": None,
        "last_time_s": None,
        "median_dt_s": None,
        "effective_rate_hz": None,
        "max_interval_jitter_s": None,
        "max_normalized_grid_residual_s": None,
        "raw_time_vector_sha256": None,
        "normalized_time_vector_sha256": None,
    }


def diagnose_time_vector(time_values: Any, columns: list[str]) -> tuple[dict, list[str]]:
    """Compute every safe timing diagnostic before assigning PASS/FAIL."""

    summary = _empty_summary()
    reasons: list[str] = []
    expected = set(EXPECTED_COLUMNS)
    if len(columns) != len(EXPECTED_COLUMNS) or len(set(columns)) != len(columns) or set(columns) != expected:
        reasons.append("exact frozen 49-name schema failed")
    try:
        values = np.asarray(time_values, dtype=np.float64)
    except Exception as exc:
        reasons.append(f"time_s numeric conversion failed: {type(exc).__name__}: {exc}")
        return summary, reasons

    if values.ndim != 1 or values.size != SAMPLE_COUNT:
        reasons.append(f"time_s length/shape failed: expected ({SAMPLE_COUNT},), got {values.shape}")
        return summary, reasons

    summary["raw_time_vector_sha256"] = vector_sha256(values)
    summary["first_time_s"] = float(values[0])
    summary["last_time_s"] = float(values[-1])
    finite = bool(np.isfinite(values).all())
    if not finite:
        reasons.append("time_s contains nonfinite values")
        return summary, reasons

    intervals = np.diff(values)
    strictly_increasing = bool(np.all(intervals > 0))
    if not strictly_increasing:
        reasons.append("time_s is not strictly increasing")

    median_dt = float(np.median(intervals))
    summary["median_dt_s"] = median_dt
    if not np.isfinite(median_dt) or median_dt <= 0:
        reasons.append("median dt is not finite and positive")
    else:
        effective_rate = 1.0 / median_dt
        summary["effective_rate_hz"] = effective_rate
        if abs(median_dt - (1.0 / SAMPLE_RATE_HZ)) > 1e-9:
            reasons.append("median dt differs from 1/6400 s by more than 1e-9 s")
        jitter = float(np.max(np.abs(intervals - median_dt)))
        summary["max_interval_jitter_s"] = jitter
        if jitter > 1e-9:
            reasons.append("interval jitter exceeds 1e-9 s")

    relative = values - values[0]
    nominal = np.arange(SAMPLE_COUNT, dtype=np.float64) / SAMPLE_RATE_HZ
    summary["normalized_time_vector_sha256"] = vector_sha256(relative)
    residual = float(np.max(np.abs(relative - nominal)))
    summary["max_normalized_grid_residual_s"] = residual
    if residual > 1e-7:
        reasons.append("normalized time grid residual exceeds 1e-7 s")
    return summary, reasons


def qualify_dataframe(frame: Any) -> dict:
    """Inspect metadata and time_s only; signal columns are never indexed."""

    if not isinstance(frame, pd.DataFrame):
        raise TimebaseQualificationError("payload object is not a pandas DataFrame")
    columns = [str(column) for column in frame.columns]
    shape = tuple(frame.shape)
    if shape != (SAMPLE_COUNT, len(EXPECTED_COLUMNS)):
        raise TimebaseQualificationError(
            f"DataFrame shape failed: expected {(SAMPLE_COUNT, len(EXPECTED_COLUMNS))}, got {shape}"
        )
    if TIME_COLUMN not in frame.columns:
        raise TimebaseQualificationError("time_s column is missing")
    # The calibration layer has exactly one data-column access, and it is time_s.
    summary, reasons = diagnose_time_vector(
        pd.to_numeric(frame[TIME_COLUMN], errors="raise").to_numpy(dtype=np.float64),
        columns,
    )
    if reasons:
        raise TimebaseQualificationError("; ".join(reasons))
    return summary


def event_index(t_evnt_start: float) -> int:
    nominal_time = np.arange(SAMPLE_COUNT, dtype=np.float64) / SAMPLE_RATE_HZ
    return int(np.searchsorted(nominal_time, float(t_evnt_start), side="left"))


def _case_diagnostics(frame: Any) -> tuple[dict, list[str], dict]:
    summary = _empty_summary()
    reasons: list[str] = []
    meta = {"object_type": type(frame).__name__, "shape": None, "columns": None}
    if not isinstance(frame, pd.DataFrame):
        return summary, ["payload object is not a pandas DataFrame"], meta
    meta["shape"] = list(frame.shape)
    meta["columns"] = [str(column) for column in frame.columns]
    if tuple(frame.shape) != (SAMPLE_COUNT, len(EXPECTED_COLUMNS)):
        reasons.append(f"DataFrame shape failed: expected {(SAMPLE_COUNT, len(EXPECTED_COLUMNS))}, got {tuple(frame.shape)}")
    if TIME_COLUMN not in frame.columns:
        reasons.append("time_s column is missing")
        return summary, reasons, meta
    try:
        time_values = pd.to_numeric(frame[TIME_COLUMN], errors="raise").to_numpy(dtype=np.float64)
    except Exception as exc:
        reasons.append(f"time_s numeric conversion failed: {type(exc).__name__}: {exc}")
        return summary, reasons, meta
    timing_summary, timing_reasons = diagnose_time_vector(time_values, meta["columns"])
    summary.update(timing_summary)
    reasons.extend(timing_reasons)
    return summary, reasons, meta


def run_calibration(*, calibration_map_path: Path, index_path: Path, output_dir: Path) -> dict:
    calibration_map = json.loads(calibration_map_path.read_text(encoding="utf-8"))
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if len(calibration_map) != 8:
        raise ValueError("calibration map must contain exactly 8 cases")
    if index.get("selected_member_count") != 72:
        raise ValueError("ERC-3C index must contain exactly 72 selected members")
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
            "timing": _empty_summary(),
            "status": "FAIL",
            "reasons": [],
        }
        try:
            acquired = acquire_member(archive_url=ARCHIVE_URL, acquisition_row=acquisition_row, index_row=index_row)
            case["payload_sha256"] = acquired.payload_sha256
            frame = pd.read_pickle(io.BytesIO(acquired.payload))
            summary, reasons, meta = _case_diagnostics(frame)
            case["object_type"] = meta["object_type"]
            case["shape"] = meta["shape"]
            case["columns"] = meta["columns"]
            case["timing"] = summary
            case["status"] = "PASS" if not reasons else "FAIL"
            case["reasons"] = reasons or ["all frozen differential-grid rules passed"]
        except Exception as exc:
            case["reasons"] = [f"{type(exc).__name__}: {exc}"]
        cases.append(case)

    status = "ERC3C_INDEX_TIME_QUALIFICATION_PASS" if opened == 8 and all(case["status"] == "PASS" for case in cases) else "ERC3C_INDEX_TIME_QUALIFICATION_FAIL"
    contract = {
        "unit": "ERC-3C",
        "status": status,
        "calibration_case_count": 8,
        "calibration_waveforms_opened": opened,
        "science_waveforms_opened": 0,
        "science_signal_columns_read": 0,
        "scientific_predictions": 0,
        "scorer_opened": False,
        "same_set_rescue_authorized": False,
        "time_origin_gate": "recorded_not_gated",
        "timing_summary_count": len(cases),
        "normalized_time_vector_sha256_set": sorted({case["timing"]["normalized_time_vector_sha256"] for case in cases if case["timing"]["normalized_time_vector_sha256"]}),
        "raw_time_vector_sha256_set": sorted({case["timing"]["raw_time_vector_sha256"] for case in cases if case["timing"]["raw_time_vector_sha256"]}),
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
    }
    contract["contract_sha256"] = sha256_json(contract)
    receipt = {
        "unit": "ERC-3C",
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
    (output_dir / "ERC3C_INDEX_TIME_CONTRACT.json").write_text(json.dumps(contract, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (output_dir / "ERC3C_INDEX_TIME_CALIBRATION_RECEIPT.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(contract, sort_keys=True, indent=2))
    return contract


def main() -> None:
    parser = argparse.ArgumentParser(description="ERC-3C differential-grid calibration using eight members only")
    parser.add_argument("--calibration-map", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    contract = run_calibration(calibration_map_path=args.calibration_map, index_path=args.index, output_dir=args.output_dir)
    if contract["status"] != "ERC3C_INDEX_TIME_QUALIFICATION_PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
