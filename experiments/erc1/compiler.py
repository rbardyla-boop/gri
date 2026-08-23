from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

WINDOW_SECONDS = 300
MIN_POINTS = 20
SCORE_CAP = 30.0
RESOURCE_SUFFIXES = {"cpu", "mem", "socket", "diskio"}
PACKET_CAPACITY = 16


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


@dataclass(frozen=True)
class FeatureRecord:
    evidence_id: str
    column: str
    service: str
    suffix: str
    evidence_kind: str
    source_metrics_sha256: str
    staged_metrics_sha256: str
    pre_start: int
    pre_end_exclusive: int
    post_start: int
    post_end_exclusive: int
    pre_count: int
    post_count: int
    pre_median: float
    post_median: float
    pre_p10: float
    post_p10: float
    pre_p90: float
    post_p90: float
    median_shift: float
    p10_shift: float
    p90_shift: float
    numerator: float
    scaled_mad: float
    scaled_iqr: float
    scaled_diff_std: float
    relative_median_floor: float
    magnitude_floor: float
    absolute_floor: float
    denominator: float
    score: float


def _finite(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    return values[np.isfinite(values)]


def _percentile(values: np.ndarray, q: float) -> float:
    return float(np.percentile(values, q, method="linear"))


def score_feature(
    opaque_id: str,
    column: str,
    times: np.ndarray,
    values: np.ndarray,
    inject_time: int,
    source_metrics_sha256: str,
    staged_metrics_sha256: str,
) -> FeatureRecord | None:
    if "_" not in column:
        return None
    service, suffix = column.rsplit("_", 1)
    pre_mask = (times >= inject_time - WINDOW_SECONDS) & (times < inject_time)
    post_mask = (times >= inject_time) & (times < inject_time + WINDOW_SECONDS)
    pre = _finite(values[pre_mask])
    post = _finite(values[post_mask])
    if len(pre) < MIN_POINTS or len(post) < MIN_POINTS:
        return None

    pre_median = float(np.median(pre))
    post_median = float(np.median(post))
    pre_p10 = _percentile(pre, 10)
    post_p10 = _percentile(post, 10)
    pre_p90 = _percentile(pre, 90)
    post_p90 = _percentile(post, 90)
    median_shift = abs(post_median - pre_median)
    p10_shift = abs(post_p10 - pre_p10)
    p90_shift = abs(post_p90 - pre_p90)
    numerator = max(median_shift, p10_shift, p90_shift)

    mad = float(np.median(np.abs(pre - pre_median)))
    q25 = _percentile(pre, 25)
    q75 = _percentile(pre, 75)
    scaled_mad = 1.4826 * mad
    scaled_iqr = (q75 - q25) / 1.349
    scaled_diff_std = (
        float(np.std(np.diff(pre), ddof=0) / math.sqrt(2.0)) if len(pre) >= 2 else 0.0
    )
    relative_median_floor = 0.01 * abs(pre_median)
    magnitude_floor = 0.001 * _percentile(np.abs(pre), 75)
    absolute_floor = 1e-8
    denominator = max(
        scaled_mad,
        scaled_iqr,
        scaled_diff_std,
        relative_median_floor,
        magnitude_floor,
        absolute_floor,
    )
    score = min(SCORE_CAP, numerator / denominator)
    evidence_id = "EV-" + sha256_text(opaque_id + "|" + column)[:20]
    return FeatureRecord(
        evidence_id=evidence_id,
        column=column,
        service=service,
        suffix=suffix,
        evidence_kind="resource" if suffix in RESOURCE_SUFFIXES else "symptom",
        source_metrics_sha256=source_metrics_sha256,
        staged_metrics_sha256=staged_metrics_sha256,
        pre_start=inject_time - WINDOW_SECONDS,
        pre_end_exclusive=inject_time,
        post_start=inject_time,
        post_end_exclusive=inject_time + WINDOW_SECONDS,
        pre_count=len(pre),
        post_count=len(post),
        pre_median=pre_median,
        post_median=post_median,
        pre_p10=pre_p10,
        post_p10=post_p10,
        pre_p90=pre_p90,
        post_p90=post_p90,
        median_shift=median_shift,
        p10_shift=p10_shift,
        p90_shift=p90_shift,
        numerator=numerator,
        scaled_mad=scaled_mad,
        scaled_iqr=scaled_iqr,
        scaled_diff_std=scaled_diff_std,
        relative_median_floor=relative_median_floor,
        magnitude_floor=magnitude_floor,
        absolute_floor=absolute_floor,
        denominator=denominator,
        score=score,
    )


def service_rank(
    features: list[FeatureRecord],
) -> tuple[list[str], dict[str, float], dict[str, list[FeatureRecord]]]:
    grouped: dict[str, list[FeatureRecord]] = {}
    for feature in features:
        grouped.setdefault(feature.service, []).append(feature)
    scores: dict[str, float] = {}
    for service, values in grouped.items():
        resources = sorted(
            (value for value in values if value.evidence_kind == "resource"),
            key=lambda value: (-value.score, value.column),
        )
        symptoms = sorted(
            (value for value in values if value.evidence_kind == "symptom"),
            key=lambda value: (-value.score, value.column),
        )
        resource_weights = (1.0, 1.0, 0.25, 0.25)
        symptom_weights = (0.20, 0.20)
        aggregate = sum(
            weight * item.score for weight, item in zip(resource_weights, resources[:4])
        )
        aggregate += sum(
            weight * item.score for weight, item in zip(symptom_weights, symptoms[:2])
        )
        scores[service] = float(aggregate)
    ranking = sorted(scores, key=lambda service: (-scores[service], service))
    return ranking, scores, grouped


def build_packet(
    opaque_id: str,
    ranking: list[str],
    grouped: dict[str, list[FeatureRecord]],
) -> tuple[list[dict], str]:
    if not ranking:
        return [], sha256_text("[]")
    selected: list[FeatureRecord] = []
    leader_values = grouped[ranking[0]]
    resources = sorted(
        (value for value in leader_values if value.evidence_kind == "resource"),
        key=lambda value: (-value.score, value.column),
    )
    symptoms = sorted(
        (value for value in leader_values if value.evidence_kind == "symptom"),
        key=lambda value: (-value.score, value.column),
    )
    selected.extend(resources[:4])
    selected.extend(symptoms[:2])

    for service in ranking[1:]:
        if len(selected) >= PACKET_CAPACITY:
            break
        values = sorted(grouped[service], key=lambda value: (-value.score, value.column))
        room = PACKET_CAPACITY - len(selected)
        selected.extend(values[: min(2, room)])

    packet: list[dict] = []
    for item in selected[:PACKET_CAPACITY]:
        row = asdict(item)
        row["opaque_id"] = opaque_id
        packet.append(row)
    return packet, sha256_text(canonical_json(packet))


def compile_case(metrics_path: Path, meta_path: Path) -> dict:
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    if sha256_file(metrics_path) != metadata["staged_metrics_sha256"]:
        raise ValueError(f"staged metric digest mismatch for {metadata['opaque_id']}")
    frame = pd.read_parquet(metrics_path)
    if "time" not in frame.columns:
        raise ValueError("candidate metrics missing time")
    times = pd.to_numeric(frame["time"], errors="raise").to_numpy(dtype=np.int64)
    inject_time = int(metadata["inject_time"])
    features: list[FeatureRecord] = []
    for column in frame.columns:
        if column == "time":
            continue
        values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=np.float64)
        record = score_feature(
            metadata["opaque_id"],
            column,
            times,
            values,
            inject_time,
            metadata["source_metrics_sha256"],
            metadata["staged_metrics_sha256"],
        )
        if record is not None:
            features.append(record)
    ranking, service_scores, grouped = service_rank(features)
    packet, packet_sha = build_packet(metadata["opaque_id"], ranking, grouped)
    return {
        "opaque_id": metadata["opaque_id"],
        "root_cause_service_ranking": ranking,
        "service_scores": service_scores,
        "feature_count": len(features),
        "packet_count": len(packet),
        "packet_sha256": packet_sha,
        "packet": packet,
    }


def compile_directory(candidate_dir: Path, output: Path) -> dict:
    meta_files = sorted(candidate_dir.glob("E1-*.json"))
    rows = []
    for meta_path in meta_files:
        opaque_id = meta_path.stem
        metrics_path = candidate_dir / f"{opaque_id}.parquet"
        if not metrics_path.exists():
            raise FileNotFoundError(metrics_path)
        rows.append(compile_case(metrics_path, meta_path))
    rows.sort(key=lambda row: row["opaque_id"])
    if not rows:
        raise ValueError("no candidate cases found")
    if any(row["packet_count"] > PACKET_CAPACITY for row in rows):
        raise ValueError("packet capacity exceeded")
    body = {"unit": "ERC-1", "case_count": len(rows), "predictions": rows}
    body["prediction_seal_sha256"] = sha256_text(canonical_json(rows))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(body, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compile_directory(args.candidate_dir, args.output)
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "predictions"},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
