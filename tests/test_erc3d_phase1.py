from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from experiments.erc3a.channel_schema import CHANNEL_SCHEMA, SAMPLE_COUNT, SAMPLE_RATE_HZ, TIME_COLUMN
from experiments.erc3d import quantized_time_calibration as calibration
from experiments.erc3d.producer_boundary import assert_clean
from experiments.erc3d.protocol import EXPECTED_COLUMNS


def _endpoint_quantized() -> np.ndarray:
    nominal = (np.arange(SAMPLE_COUNT, dtype=np.float64) + 1.0) / SAMPLE_RATE_HZ
    return np.rint(nominal * 1_000_000.0) / 1_000_000.0


def _frame(time_values: np.ndarray | None = None) -> pd.DataFrame:
    values = {TIME_COLUMN: _endpoint_quantized() if time_values is None else time_values}
    values.update({channel: np.zeros(SAMPLE_COUNT, dtype=np.float64) for channel in CHANNEL_SCHEMA})
    return pd.DataFrame(values, columns=[TIME_COLUMN, *CHANNEL_SCHEMA])


def test_quantized_endpoint_grid_passes_and_origin_is_recorded() -> None:
    timing, reasons = calibration.diagnose_time_vector(_endpoint_quantized(), list(EXPECTED_COLUMNS))
    assert reasons == []
    assert timing["first_time_s"] == pytest.approx(0.000156)
    assert timing["last_time_s"] == pytest.approx(1.0)
    assert timing["min_raw_dt_s"] == pytest.approx(0.000156)
    assert timing["median_raw_dt_s"] == pytest.approx(0.000156)
    assert timing["max_raw_dt_s"] == pytest.approx(0.000157)
    assert timing["max_integer_microsecond_residual_s"] == pytest.approx(0.0)
    assert timing["max_endpoint_grid_residual_s"] == pytest.approx(0.5e-6)
    assert timing["raw_time_vector_sha256"] is not None
    assert timing["integer_microsecond_vector_sha256"] is not None


@pytest.mark.parametrize(
    ("name", "make_values", "reason"),
    [
        ("not_quantized", lambda: _endpoint_quantized() + 1e-9, "integer-microsecond"),
        ("wrong_endpoint", lambda: _endpoint_quantized() + 1e-5, "endpoint-grid"),
        ("wrong_last", lambda: np.concatenate([_endpoint_quantized()[:-1], [0.999999]]), "last timestamp"),
        ("nonmonotonic", lambda: _endpoint_quantized() + np.where(np.arange(SAMPLE_COUNT) == 100, -1e-3, 0.0), "strictly increasing"),
    ],
)
def test_quantized_contract_rejects_representation_failures(name: str, make_values, reason: str) -> None:
    del name
    timing, reasons = calibration.diagnose_time_vector(make_values(), list(EXPECTED_COLUMNS))
    assert timing["raw_time_vector_sha256"] is not None
    assert any(reason in item for item in reasons)


def test_schema_failure_still_preserves_timing_diagnostics() -> None:
    columns = [TIME_COLUMN, *CHANNEL_SCHEMA[:-1], "ALIEN_CHANNEL"]
    timing, reasons = calibration.diagnose_time_vector(_endpoint_quantized(), columns)
    assert timing["integer_microsecond_vector_sha256"] is not None
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

    frame = GuardedFrame(_frame())
    timing, reasons, _ = calibration._case_diagnostics(frame)
    assert reasons == []
    assert timing["last_time_s"] == pytest.approx(1.0)


def test_runner_opens_only_eight_calibration_members_and_requires_common_hashes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calibration_map = [{"opaque_id": f"cal-{i}", "sample_id": i, "t_evnt_start": 0.25} for i in range(8)]
    selected = [
        {**row, "role": "calibration", "path": f"{row['sample_id']}_sample_hv_double_line_90kv.pkl"}
        for row in calibration_map
    ]
    selected.extend(
        {
            "opaque_id": f"sci-{i}", "sample_id": i + 100, "t_evnt_start": 0.25,
            "role": "science", "path": f"{i + 100}_sample_hv_double_line_90kv.pkl",
        }
        for i in range(64)
    )
    raw = io.BytesIO()
    _frame().to_pickle(raw)
    opened: list[str] = []

    def fake_acquire_member(*, acquisition_row, index_row, **kwargs):
        del kwargs
        assert index_row["role"] == "calibration"
        opened.append(acquisition_row["opaque_id"])
        return SimpleNamespace(payload=raw.getvalue(), payload_sha256="payload-sha")

    monkeypatch.setattr(calibration, "acquire_member", fake_acquire_member)
    map_path = tmp_path / "calibration.json"
    index_path = tmp_path / "index.json"
    map_path.write_text(json.dumps(calibration_map))
    index_path.write_text(json.dumps({"selected_member_count": 72, "selected_members": selected}))
    contract = calibration.run_calibration(calibration_map_path=map_path, index_path=index_path, output_dir=tmp_path / "out")
    assert contract["status"] == "ERC3D_QUANTIZED_TIME_QUALIFICATION_PASS"
    assert len(opened) == 8
    assert contract["science_waveforms_opened"] == 0
    assert contract["science_signal_columns_read"] == 0
    assert contract["scientific_predictions"] == 0
    assert contract["scorer_opened"] is False
    receipt = json.loads((tmp_path / "out/ERC3D_QUANTIZED_TIME_CALIBRATION_RECEIPT.json").read_text())
    assert len(receipt["cases"]) == 8
    assert len({case["timing"]["raw_time_vector_sha256"] for case in receipt["cases"]}) == 1
    assert len({case["timing"]["integer_microsecond_vector_sha256"] for case in receipt["cases"]}) == 1


def test_identity_scanner_rejects_truth_and_source_identity(tmp_path: Path) -> None:
    for key in ("sample_id", "fault_target", "sc_type", "sc_location", "phase_label", "truth"):
        path = tmp_path / f"{key}.json"
        path.write_text(json.dumps({"opaque_id": "x", key: "leak"}))
        with pytest.raises(AssertionError, match="identity leakage"):
            assert_clean([path])
