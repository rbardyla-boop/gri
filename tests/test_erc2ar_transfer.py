from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.erc2ar.stage_damadics import EVENTS, SOURCE_POSITIONS, adapted_window


def test_frozen_event_set_and_distribution():
    assert [e["item"] for e in EVENTS] == [1,2,4,5,6,7,8,9,10,11,13,14,19]
    assert sum(e["actuator"] == "A1" for e in EVENTS) == 6
    assert sum(e["actuator"] == "A2" for e in EVENTS) == 5
    assert sum(e["actuator"] == "A3" for e in EVENTS) == 2
    assert len({e["opaque_id"] for e in EVENTS}) == 13


def test_official_positions_are_disjoint_and_exact():
    assert SOURCE_POSITIONS == {
        "A1": [1,2,3,4,5,6],
        "A2": [17,18,19,20,21,22],
        "A3": [23,24,25,26,27,28],
    }
    flat = [x for values in SOURCE_POSITIONS.values() for x in values]
    assert len(flat) == len(set(flat)) == 18


def test_adapter_preserves_time_and_only_18_frozen_signals():
    rows = 1000
    data = np.arange(rows * 33, dtype=float).reshape(rows, 33)
    data[:, 0] = np.arange(rows)
    frame = pd.DataFrame(data)
    out = adapted_window(frame, 500)
    assert out.shape == (600, 19)
    assert out["time"].iloc[0] == 200
    assert out["time"].iloc[-1] == 799
    expected_cols = ["time"] + [f"{a}_sig{i:02d}" for a in ("A1","A2","A3") for i in range(1,7)]
    assert list(out.columns) == expected_cols
    assert np.array_equal(out["A1_sig01"].to_numpy(), frame.iloc[200:800, 1].to_numpy())
    assert np.array_equal(out["A2_sig06"].to_numpy(), frame.iloc[200:800, 22].to_numpy())
    assert np.array_equal(out["A3_sig06"].to_numpy(), frame.iloc[200:800, 28].to_numpy())


def test_all_adapted_suffixes_stay_generic_symptom_path():
    forbidden = {"cpu","mem","socket","diskio"}
    names = [f"{a}_sig{i:02d}" for a in ("A1","A2","A3") for i in range(1,7)]
    assert all(name.rsplit("_",1)[1] not in forbidden for name in names)
