from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from experiments.erc3a.channel_schema import CHANNEL_SCHEMA, SAMPLE_COUNT, SAMPLE_RATE_HZ, TIME_COLUMN
from experiments.erc3c import timebase_calibration
from experiments.erc3c.producer_boundary import assert_clean
from experiments.erc3c.protocol import EXPECTED_COLUMNS


def _time(origin: float = 0.0) -> np.ndarray:
    return origin + np.arange(SAMPLE_COUNT, dtype=np.float64) / SAMPLE_RATE_HZ


def _frame(time_values: np.ndarray | None = None) -> pd.DataFrame:
    values = {TIME_COLUMN: _time() if time_values is None else time_values}
    values.update({channel: np.zeros(SAMPLE_COUNT, dtype=np.float64) for channel in CHANNEL_SCHEMA})
    return pd.DataFrame(values, columns=[TIME_COLUMN, *CHANNEL_SCHEMA])


def test_nonzero_raw_origin_is_recorded_but_passes_nominal_differential_grid() -> None:
    summary, reasons = timebase_calibration.diagnose_time_vector(_time(17.25), list(EXPECTED_COLUMNS))
    assert reasons == []
    assert summary["first_time_s"] == pytest.approx(17.25)
    assert summary["last_time_s"] == pytest.approx(17.25 + 6399 / 6400)
    assert summary["median_dt_s"] == pytest.approx(1 / 6400)
    assert summary["effective_rate_hz"] == pytest.approx(6400)
    assert summary["max_interval_jitter_s"] <= 1e-9
    assert summary["max_normalized_grid_residual_s"] <= 1e-7
    assert summary["raw_time_vector_sha256"] != summary["normalized_time_vector_sha256"]


@pytest.mark.parametrize(
    ("name", "make_values", "reason"),
    [
        ("rate", lambda: _time(0.5) * 6400 / 6300, "median dt"),
        ("jitter", lambda: _time(0.5) + np.where(np.arange(SAMPLE_COUNT) >= 100, 2e-9, 0.0), "jitter"),
        ("residual", lambda: _time(0.5) + np.arange(SAMPLE_COUNT) * (2e-7 / 6399), "residual"),
        ("nonfinite", lambda: np.where(np.arange(SAMPLE_COUNT) == 12, np.nan, _time(0.5)), "nonfinite"),
        ("nonmonotonic", lambda: _time(0.5) + np.where(np.arange(SAMPLE_COUNT) == 100, -1e-3, 0.0), "strictly increasing"),
    ],
)
def test_differential_grid_rejects_spacing_and_integrity_violations(name: str, make_values, reason: str) -> None:
    del name
    summary, reasons = timebase_calibration.diagnose_time_vector(make_values(), list(EXPECTED_COLUMNS))
    assert summary["raw_time_vector_sha256"] is not None
    assert reasons and any(reason in item for item in reasons)


def test_wrong_schema_is_rejected_but_timing_diagnostics_are_preserved() -> None:
    columns = [TIME_COLUMN, *CHANNEL_SCHEMA[:-1], "ALIEN_CHANNEL"]
    summary, reasons = timebase_calibration.diagnose_time_vector(_time(2.0), columns)
    assert summary["median_dt_s"] == pytest.approx(1 / 6400)
    assert summary["normalized_time_vector_sha256"] is not None
    assert any("schema" in item for item in reasons)


def test_calibration_never_indexes_signal_columns() -> None:
    class GuardedFrame(pd.DataFrame):
        @property
        def _constructor(self):  # pragma: no cover - pandas metadata hook
            return GuardedFrame

        def __getitem__(self, key):
            if key != TIME_COLUMN:
                raise AssertionError(f"signal column accessed: {key}")
            return super().__getitem__(key)

    frame = GuardedFrame(_frame(_time(0.75)))
    summary, reasons, _ = timebase_calibration._case_diagnostics(frame)
    assert reasons == []
    assert summary["first_time_s"] == pytest.approx(0.75)


def test_event_coordinate_uses_nominal_grid() -> None:
    nominal = np.arange(SAMPLE_COUNT, dtype=np.float64) / SAMPLE_RATE_HZ
    for index in (0, 1, 128, 6399):
        assert timebase_calibration.event_index(float(nominal[index])) == index
    assert timebase_calibration.event_index(float(nominal[128] + 1e-8)) == 129


def test_identity_scanner_rejects_phase_and_truth_fields(tmp_path: Path) -> None:
    for key in ("sample_id", "fault_target", "sc_type", "sc_location", "phase_label", "truth"):
        path = tmp_path / f"{key}.json"
        path.write_text(json.dumps({"opaque_id": "x", key: "leak"}))
        with pytest.raises(AssertionError, match="identity leakage"):
            assert_clean([path])


def test_runner_preserves_all_eight_diagnostics_and_never_opens_science(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calibration_map = [
        {"opaque_id": f"cal-{index}", "sample_id": index, "t_evnt_start": 0.25}
        for index in range(8)
    ]
    selected = [
        {**row, "role": "calibration", "path": f"{row['sample_id']}_sample_hv_double_line_90kv.pkl"}
        for row in calibration_map
    ]
    selected.extend(
        {
            "opaque_id": f"sci-{index}",
            "sample_id": index + 100,
            "t_evnt_start": 0.25,
            "role": "science",
            "path": f"{index + 100}_sample_hv_double_line_90kv.pkl",
        }
        for index in range(64)
    )
    raw = io.BytesIO()
    _frame(_time(9.0)).to_pickle(raw)
    opened: list[str] = []

    def fake_acquire_member(*, acquisition_row, index_row, **kwargs):
        del kwargs
        assert index_row["role"] == "calibration"
        opened.append(acquisition_row["opaque_id"])
        return SimpleNamespace(payload=raw.getvalue(), payload_sha256="payload-sha")

    monkeypatch.setattr(timebase_calibration, "acquire_member", fake_acquire_member)
    map_path = tmp_path / "calibration.json"
    index_path = tmp_path / "index.json"
    map_path.write_text(json.dumps(calibration_map))
    index_path.write_text(json.dumps({"selected_member_count": 72, "selected_members": selected}))
    contract = timebase_calibration.run_calibration(
        calibration_map_path=map_path,
        index_path=index_path,
        output_dir=tmp_path / "out",
    )
    assert contract["status"] == "ERC3C_INDEX_TIME_QUALIFICATION_PASS"
    assert len(opened) == 8
    receipt = json.loads((tmp_path / "out/ERC3C_INDEX_TIME_CALIBRATION_RECEIPT.json").read_text())
    assert len(receipt["cases"]) == 8
    assert all(set(case["timing"]) == {
        "first_time_s", "last_time_s", "median_dt_s", "effective_rate_hz",
        "max_interval_jitter_s", "max_normalized_grid_residual_s",
        "raw_time_vector_sha256", "normalized_time_vector_sha256",
    } for case in receipt["cases"])
    assert contract["science_waveforms_opened"] == 0
    assert contract["science_signal_columns_read"] == 0
    assert contract["scientific_predictions"] == 0
    assert contract["scorer_opened"] is False
