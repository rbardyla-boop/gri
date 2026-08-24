from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.erc1.compiler import compile_case, sha256_file
from experiments.erc2ar.baseline import baseline_case
from experiments.erc2ar.contract import EVENTS_PUBLIC, EXPECTED_CASES, SIGNAL_COLUMNS, expected_opaque_ids
from experiments.erc2ar.stage_live import project_fields


def main() -> None:
    assert len(EVENTS_PUBLIC) == EXPECTED_CASES == 13
    assert len(set(expected_opaque_ids())) == EXPECTED_CASES
    assert [item for item, _ in SIGNAL_COLUMNS] == [2,3,4,5,6,7,18,19,20,21,22,23,24,25,26,27,28,29]

    fields = [str(i).encode("ascii") for i in range(1, 34)]
    projected = project_fields(fields)
    assert projected["A1_P1"] == 2.0 and projected["A1_X"] == 7.0
    assert projected["A2_P1"] == 18.0 and projected["A2_X"] == 23.0
    assert projected["A3_P1"] == 24.0 and projected["A3_X"] == 29.0
    assert len(projected) == 18

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        oid = "E1-syntheticadapter"
        times = np.arange(600, dtype=np.int64)
        data: dict[str, np.ndarray] = {"time": times}
        for _, name in SIGNAL_COLUMNS:
            data[name] = np.zeros(600, dtype=np.float64)
        data["A2_P1"][300:] = 10.0
        data["A2_P2"][300:] = 8.0
        frame = pd.DataFrame(data)
        metrics = root / f"{oid}.parquet"
        frame.to_parquet(metrics, index=False, engine="pyarrow", compression=None)
        meta = {
            "opaque_id": oid,
            "inject_time": 300,
            "source_metrics_sha256": "0" * 64,
            "staged_metrics_sha256": sha256_file(metrics),
        }
        meta_path = root / f"{oid}.json"
        meta_path.write_text(json.dumps(meta, sort_keys=True, indent=2) + "\n", encoding="utf-8")

        compiled = compile_case(metrics, meta_path)
        baseline = baseline_case(metrics, meta_path)
        assert compiled["root_cause_service_ranking"][0] == "A2"
        assert baseline["actuator_ranking"][0] == "A2"
        assert compiled["packet_count"] <= 16
        assert all(row["evidence_kind"] == "symptom" for row in compiled["packet"])

    print("ERC2AR_PRE_LIVE_SYNTHETIC_PASS")


if __name__ == "__main__":
    main()
