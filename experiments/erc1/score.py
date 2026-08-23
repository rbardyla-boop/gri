from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_TOTAL = 90
EXPECTED_SCIENTIFIC = 63
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


def verify_prediction_file(path: Path) -> dict:
    body = json.loads(path.read_text(encoding="utf-8"))
    rows = body.get("predictions", [])
    if body.get("case_count") != len(rows):
        raise ValueError(f"case count mismatch in {path}")
    expected = sha256_text(canonical_json(rows))
    if body.get("prediction_seal_sha256") != expected:
        raise ValueError(f"prediction seal mismatch in {path}")
    return body


def score(
    staging_root: Path,
    live_path: Path,
    replay_path: Path,
    output: Path,
) -> dict:
    staging_manifest_path = staging_root / "STAGING_MANIFEST.json"
    labels_path = staging_root / "scorer_only" / "labels.json"
    candidate_dir = staging_root / "candidate"
    if not staging_manifest_path.exists() or not labels_path.exists():
        raise ValueError("staging/scorer artifacts missing")
    staging = json.loads(staging_manifest_path.read_text(encoding="utf-8"))
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    live = verify_prediction_file(live_path)
    replay = verify_prediction_file(replay_path)

    source_identity_ok = (
        staging.get("status") == "ERC1_STAGED"
        and staging.get("case_count") == EXPECTED_TOTAL
        and staging.get("scientific_count") == EXPECTED_SCIENTIFIC
        and staging.get("evidence_class") in {"EXACT_SOURCE_REPRODUCTION", "LOSSLESS_REPACK_REPRODUCTION"}
    )

    live_rows = {row["opaque_id"]: row for row in live["predictions"]}
    replay_rows = {row["opaque_id"]: row for row in replay["predictions"]}
    replay_exact = live.get("prediction_seal_sha256") == replay.get("prediction_seal_sha256") and live_rows == replay_rows

    labels_by_id = {row["opaque_id"]: row for row in labels}
    id_match = set(live_rows) == set(labels_by_id) and len(live_rows) == EXPECTED_TOTAL
    provenance_failures = []
    capacity_failures = []
    for opaque_id, row in live_rows.items():
        meta_path = candidate_dir / f"{opaque_id}.json"
        metrics_path = candidate_dir / f"{opaque_id}.parquet"
        if not meta_path.exists() or not metrics_path.exists():
            provenance_failures.append(f"{opaque_id}: candidate source missing")
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        staged_sha = sha256_file(metrics_path)
        if staged_sha != meta.get("staged_metrics_sha256"):
            provenance_failures.append(f"{opaque_id}: staged source digest mismatch")
        packet = row.get("packet", [])
        if len(packet) > PACKET_CAPACITY:
            capacity_failures.append(opaque_id)
        packet_sha = sha256_text(canonical_json(packet))
        if row.get("packet_sha256") != packet_sha:
            provenance_failures.append(f"{opaque_id}: packet digest mismatch")
        for record in packet:
            if record.get("opaque_id") != opaque_id:
                provenance_failures.append(f"{opaque_id}: cross-case packet record")
            if record.get("staged_metrics_sha256") != meta.get("staged_metrics_sha256"):
                provenance_failures.append(f"{opaque_id}: packet staged digest mismatch")
            if record.get("source_metrics_sha256") != meta.get("source_metrics_sha256"):
                provenance_failures.append(f"{opaque_id}: packet source digest mismatch")

    scientific = [row for row in labels if row["repetition"] != 1]
    engineering = [row for row in labels if row["repetition"] == 1]

    def evaluate(subset: list[dict]) -> dict:
        outcomes = []
        for truth in subset:
            pred = live_rows.get(truth["opaque_id"])
            ranking = pred.get("root_cause_service_ranking", []) if pred else []
            top1 = bool(ranking) and ranking[0] == truth["root_cause_service"]
            top3 = truth["root_cause_service"] in ranking[:3]
            outcomes.append({
                "opaque_id": truth["opaque_id"],
                "source_case": truth["source_case"],
                "system": truth["system"],
                "root_cause_service": truth["root_cause_service"],
                "prediction": ranking[0] if ranking else None,
                "top3": ranking[:3],
                "top1_correct": top1,
                "top3_correct": top3,
            })
        by_system = {}
        for system in sorted({row["system"] for row in outcomes}):
            values = [row for row in outcomes if row["system"] == system]
            by_system[system] = {
                "n": len(values),
                "top1": sum(int(row["top1_correct"]) for row in values) / len(values),
                "top3": sum(int(row["top3_correct"]) for row in values) / len(values),
            }
        n = len(outcomes)
        return {
            "n": n,
            "top1_count": sum(int(row["top1_correct"]) for row in outcomes),
            "top3_count": sum(int(row["top3_correct"]) for row in outcomes),
            "top1": sum(int(row["top1_correct"]) for row in outcomes) / n,
            "top3": sum(int(row["top3_correct"]) for row in outcomes) / n,
            "by_system": by_system,
            "disagreements": [row for row in outcomes if not row["top1_correct"]],
        }

    scientific_result = evaluate(scientific) if id_match else None
    engineering_result = evaluate(engineering) if id_match else None
    opacity_provenance_ok = id_match and replay_exact and not provenance_failures and not capacity_failures

    exact_target = False
    if scientific_result is not None:
        exact_target = (
            scientific_result["n"] == EXPECTED_SCIENTIFIC
            and scientific_result["top1_count"] == EXPECTED_SCIENTIFIC
            and scientific_result["top3_count"] == EXPECTED_SCIENTIFIC
            and all(value["top1"] == 1.0 for value in scientific_result["by_system"].values())
        )

    if not source_identity_ok:
        status = "ERC1_SOURCE_IDENTITY_INVALID"
    elif not opacity_provenance_ok:
        status = "ERC1_OPACITY_OR_PROVENANCE_INVALID"
    elif not exact_target:
        status = "ERC1_CLEANROOM_DISCREPANCY"
    elif staging["evidence_class"] == "EXACT_SOURCE_REPRODUCTION":
        status = "ERC1_MCO04_DIRECT_REPRODUCED_EXACT_SOURCE"
    elif staging["evidence_class"] == "LOSSLESS_REPACK_REPRODUCTION":
        status = "ERC1_MCO04_DIRECT_REPRODUCED_LOSSLESS_REPACK"
    else:
        status = "ERC1_INCOMPLETE"

    result = {
        "unit": "ERC-1",
        "status": status,
        "historical_target": "MCO-04 direct transparent compiler 63/63 scientific root-service top1",
        "evidence_class": staging.get("evidence_class"),
        "source_revision": staging.get("source_revision"),
        "source_identity_ok": source_identity_ok,
        "opacity_provenance_ok": opacity_provenance_ok,
        "replay_exact": replay_exact,
        "prediction_seal_sha256": live.get("prediction_seal_sha256"),
        "scientific": scientific_result,
        "engineering_diagnostic": engineering_result,
        "provenance_failures": provenance_failures,
        "capacity_failures": capacity_failures,
        "live_file_sha256": sha256_file(live_path),
        "replay_file_sha256": sha256_file(replay_path),
        "staging_manifest_record_sha256": staging.get("record_sha256"),
    }
    result["record_sha256"] = sha256_text(canonical_json(result))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-root", type=Path, required=True)
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = score(args.staging_root, args.live, args.replay, args.output)
    summary = dict(result)
    if summary.get("scientific"):
        summary["scientific"] = {k: v for k, v in summary["scientific"].items() if k != "disagreements"}
    if summary.get("engineering_diagnostic"):
        summary["engineering_diagnostic"] = {k: v for k, v in summary["engineering_diagnostic"].items() if k != "disagreements"}
    print(json.dumps(summary, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
