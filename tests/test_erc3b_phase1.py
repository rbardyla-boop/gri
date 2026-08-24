from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from experiments.erc3a.channel_schema import CHANNEL_SCHEMA, SAMPLE_COUNT, TIME_COLUMN
from experiments.erc3b import timebase_calibration
from experiments.erc3b.producer_boundary import assert_clean
from experiments.erc3b.protocol import EXPECTED_TARGETS, EXPECTED_TYPES
from experiments.erc3b.select_metadata import select


def _time() -> np.ndarray:
    return np.arange(SAMPLE_COUNT, dtype=np.float64) / 6400.0


def _columns() -> list[str]:
    return [TIME_COLUMN, *CHANNEL_SCHEMA]


def _frame() -> pd.DataFrame:
    values = {TIME_COLUMN: _time()}
    values.update({channel: np.zeros(SAMPLE_COUNT, dtype=np.float64) for channel in CHANNEL_SCHEMA})
    return pd.DataFrame(values, columns=_columns())


def test_timebase_qualifier_accepts_canonical_fixture_and_hashes_little_endian_bytes() -> None:
    summary = timebase_calibration.qualify_dataframe(_frame())
    expected = hashlib.sha256(_time().astype("<f8").tobytes()).hexdigest()
    assert summary["sample_count"] == 6400
    assert summary["effective_rate_hz"] == pytest.approx(6400.0)
    assert summary["max_abs_interval_deviation_s"] == pytest.approx(0.0, abs=1e-15)
    assert summary["canonical_time_vector_sha256"] == expected


@pytest.mark.parametrize(
    ("name", "mutate", "message"),
    [
        ("nonmonotonic", lambda values: values.__setitem__(100, values[99]), "not strictly increasing"),
        ("nonfinite", lambda values: values.__setitem__(100, np.nan), "nonfinite"),
        ("jittered", lambda values: values.__setitem__(100, values[100] + 2e-9), "jitter"),
        ("out_of_band_rate", lambda values: values.__setitem__(slice(None), np.arange(SAMPLE_COUNT) / 6300.0), "outside"),
    ],
)
def test_timebase_qualifier_rejects_preregistered_bad_vectors(name: str, mutate, message: str) -> None:
    del name
    values = _time()
    mutate(values)
    with pytest.raises(ValueError, match=message):
        timebase_calibration.qualify_time_vector(values, _columns())


def test_timebase_qualifier_rejects_wrong_schema() -> None:
    with pytest.raises(ValueError, match="column schema mismatch"):
        timebase_calibration.qualify_time_vector(_time(), [TIME_COLUMN, *CHANNEL_SCHEMA[:-1], "ALIEN"])


def test_calibration_accessor_never_reads_signal_columns() -> None:
    class GuardedFrame(pd.DataFrame):
        @property
        def _constructor(self):  # pragma: no cover - pandas metadata hook
            return GuardedFrame

        def __getitem__(self, key):
            if key != TIME_COLUMN:
                raise AssertionError(f"signal column accessed during calibration: {key}")
            return super().__getitem__(key)

    base = _frame()
    guarded = GuardedFrame(base)
    assert timebase_calibration.qualify_dataframe(guarded)["sample_count"] == 6400


def test_event_alignment_is_searchsorted_left() -> None:
    values = np.array([0.0, 0.5, 1.0, 1.5], dtype=np.float64)
    assert timebase_calibration.event_index(values, 1.0) == 2
    assert timebase_calibration.event_index(values, 1.1) == 3


def test_selection_is_balanced_and_disjoint_from_calibration() -> None:
    rows = []
    sample = 10000
    for target in EXPECTED_TARGETS:
        for sc_type in EXPECTED_TYPES:
            for _ in range(10):
                rows.append(
                    {
                        "sample_id": sample,
                        "fault_target": target,
                        "sc_type": sc_type,
                        "t_evnt_start": 0.25,
                    }
                )
                sample += 1
    calibration, calibration_public, science, science_public, scorer = select(rows, set())
    assert len(calibration) == len(calibration_public) == 8
    assert len(science) == len(science_public) == len(scorer) == 64
    assert not {row["sample_id"] for row in calibration} & {row["sample_id"] for row in science}
    counts = {}
    for row in scorer:
        key = row["truth"]["fault_target"], row["truth"]["sc_type"]
        counts[key] = counts.get(key, 0) + 1
    assert set(counts.values()) == {4}


def test_identity_scanner_rejects_all_phase1_forbidden_fields(tmp_path: Path) -> None:
    for key in ("sample_id", "fault_target", "sc_type", "sc_location", "resistance"):
        path = tmp_path / f"{key}.json"
        path.write_text(json.dumps({"opaque_id": "x", key: 1}))
        with pytest.raises(AssertionError, match="identity leakage"):
            assert_clean([path])


def test_calibration_runner_opens_only_eight_calibration_members(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
            "sample_id": 100 + index,
            "t_evnt_start": 0.25,
            "role": "science",
            "path": f"{100 + index}_sample_hv_double_line_90kv.pkl",
        }
        for index in range(64)
    )
    index = {"selected_member_count": 72, "selected_members": selected}
    map_path = tmp_path / "calibration.json"
    index_path = tmp_path / "index.json"
    map_path.write_text(json.dumps(calibration_map))
    index_path.write_text(json.dumps(index))
    frame_bytes = io.BytesIO()
    _frame().to_pickle(frame_bytes)
    opened: list[str] = []

    def fake_acquire_member(*, acquisition_row, index_row, **kwargs):
        del kwargs
        assert index_row["role"] == "calibration"
        opened.append(acquisition_row["opaque_id"])
        return SimpleNamespace(payload=frame_bytes.getvalue(), payload_sha256="payload")

    monkeypatch.setattr(timebase_calibration, "acquire_member", fake_acquire_member)
    contract = timebase_calibration.run_calibration(
        calibration_map_path=map_path,
        index_path=index_path,
        output_dir=tmp_path / "out",
    )
    assert contract["status"] == "ERC3B_TIMEBASE_QUALIFICATION_PASS"
    assert len(opened) == 8
    assert contract["scientific_waveforms_opened"] == 0
    assert contract["scientific_predictions"] == 0
    assert contract["scorer_opened"] is False
