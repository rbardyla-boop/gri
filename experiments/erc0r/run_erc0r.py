from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from experiments.erc0.run_erc0 import (
    ANOMALY_THRESHOLD,
    PACKET_CAPACITY,
    GraphIndex,
    METHODS as ERC0_METHODS,
    _anomalous,
    _coherent_coverage,
    build_packet,
    canonical_json,
    extract_features,
    generate_case,
    sha256_text,
    signal_payload,
    verify_packet,
    verify_source_hashes,
)


REGISTERED_SIZES = (32, 128, 512, 2048)
REGISTERED_CASES_PER_SIZE = 32
FRESH_SEED_PREFIX = 2026082400
ERC0_OLD_SEED_PREFIX = 2026082300


def _is_anomalous_before(features, upstream: str, candidate: str) -> bool:
    u = features[upstream]
    c = features[candidate]
    return (
        u.score >= ANOMALY_THRESHOLD
        and u.onset is not None
        and c.onset is not None
        and u.onset <= c.onset
    )


def rank_quiet_parent(case, features, graph: GraphIndex):
    del case
    anomalies = {f.node_id for f in _anomalous(features)}

    def key(node: str):
        feature = features[node]
        if node not in anomalies:
            return (1, 10**9, 1.0, 10**9, 0.0, node)
        direct_upstream = sum(
            1 for parent in graph.parents[node] if _is_anomalous_before(features, parent, node)
        )
        coverage, _ = _coherent_coverage(node, features, graph)
        return (
            0,
            direct_upstream,
            -coverage,
            feature.onset if feature.onset is not None else 10**9,
            -feature.score,
            node,
        )

    return tuple(sorted(graph.nodes, key=key))


def frontier_terms(node: str, features, graph: GraphIndex):
    feature = features[node]
    if feature.onset is None:
        return 10**9, 1.0, 0.0
    anomalies = _anomalous(features)
    total_weight = sum(f.score for f in anomalies) or 1.0
    upstream_count = 0
    upstream_weight = 0.0
    for ancestor in graph.ancestors(node):
        if _is_anomalous_before(features, ancestor, node):
            upstream_count += 1
            upstream_weight += features[ancestor].score
    downstream_coverage, _ = _coherent_coverage(node, features, graph)
    return upstream_count, upstream_weight / total_weight, downstream_coverage


def rank_frontier(case, features, graph: GraphIndex):
    del case
    anomalies = {f.node_id for f in _anomalous(features)}

    def key(node: str):
        feature = features[node]
        if node not in anomalies:
            return (1, 10**9, 1.0, 0.0, 10**9, 0.0, node)
        upstream_count, upstream_weight, coverage = frontier_terms(node, features, graph)
        return (
            0,
            upstream_count,
            upstream_weight,
            -coverage,
            feature.onset if feature.onset is not None else 10**9,
            -feature.score,
            node,
        )

    return tuple(sorted(graph.nodes, key=key))


METHODS = dict(ERC0_METHODS)
METHODS.update(
    {
        "quiet_parent": rank_quiet_parent,
        "frontier": rank_frontier,
    }
)


def _case_seeds(size: int, cases_per_size: int):
    return tuple(FRESH_SEED_PREFIX + size * 1000 + i for i in range(cases_per_size))


def _old_case_ids(size: int):
    return {f"ERC0-N{size}-S{ERC0_OLD_SEED_PREFIX + size * 1000 + i}" for i in range(24)}


def run_benchmark(sizes=REGISTERED_SIZES, cases_per_size=REGISTERED_CASES_PER_SIZE):
    rows = []
    failures = []
    for size in sizes:
        old_ids = _old_case_ids(size)
        for seed in _case_seeds(size, cases_per_size):
            case, truth = generate_case(size, seed)
            if case.case_id in old_ids:
                failures.append(f"{case.case_id}: reused ERC-0 case ID")
            if not verify_source_hashes(case):
                failures.append(f"{case.case_id}: source hash mismatch")
            features = extract_features(case)
            graph = GraphIndex(case)
            raw_bytes = len(
                canonical_json(
                    {
                        "case_id": case.case_id,
                        "edges": case.edges,
                        "signals": [signal_payload(s.node_id, s.pre, s.post) for s in case.signals],
                    }
                ).encode("utf-8")
            )
            method_rows = {}
            for name, method in METHODS.items():
                ranking = method(case, features, graph)
                if len(ranking) != len(case.node_ids) or set(ranking) != set(case.node_ids):
                    failures.append(f"{case.case_id}:{name}: invalid ranking")
                packet = ()
                packet_sha = None
                packet_bytes = None
                packet_ok = None
                if name in {"ancestor_coverage", "backward_slice", "relay", "quiet_parent", "frontier"}:
                    packet, packet_sha = build_packet(case, ranking, features, graph)
                    packet_ok = verify_packet(case, packet, packet_sha)
                    packet_bytes = len(canonical_json(list(packet)).encode("utf-8"))
                    if not packet_ok:
                        failures.append(f"{case.case_id}:{name}: packet provenance invalid")
                method_rows[name] = {
                    "top1": ranking[0] == truth.root_id,
                    "top3": truth.root_id in ranking[:3],
                    "rank": ranking.index(truth.root_id) + 1,
                    "prediction": ranking[0],
                    "packet_count": len(packet) if packet else None,
                    "packet_bytes": packet_bytes,
                    "packet_sha256": packet_sha,
                    "packet_ok": packet_ok,
                }
            rows.append(
                {
                    "case_id": case.case_id,
                    "size": size,
                    "seed": seed,
                    "root_id": truth.root_id,
                    "raw_bytes": raw_bytes,
                    "methods": method_rows,
                }
            )

    metrics = {}
    for name in METHODS:
        top1 = sum(int(row["methods"][name]["top1"]) for row in rows) / len(rows)
        top3 = sum(int(row["methods"][name]["top3"]) for row in rows) / len(rows)
        by_size = {}
        for size in sizes:
            subset = [row for row in rows if row["size"] == size]
            by_size[str(size)] = {
                "n": len(subset),
                "top1": sum(int(row["methods"][name]["top1"]) for row in subset) / len(subset),
                "top3": sum(int(row["methods"][name]["top3"]) for row in subset) / len(subset),
            }
        packet_counts = [row["methods"][name]["packet_count"] for row in rows if row["methods"][name]["packet_count"] is not None]
        packet_bytes = [row["methods"][name]["packet_bytes"] for row in rows if row["methods"][name]["packet_bytes"] is not None]
        metrics[name] = {
            "top1": top1,
            "top3": top3,
            "by_size": by_size,
            "max_packet_count": max(packet_counts) if packet_counts else None,
            "median_packet_count": statistics.median(packet_counts) if packet_counts else None,
            "median_packet_bytes": statistics.median(packet_bytes) if packet_bytes else None,
        }

    def clears_quality(name: str) -> bool:
        m = metrics[name]
        by_size = [m["by_size"][str(size)]["top1"] for size in sizes]
        scale_drop = max(0.0, by_size[0] - by_size[-1])
        packet_ok = m["max_packet_count"] is None or m["max_packet_count"] <= PACKET_CAPACITY
        return (
            m["top1"] >= 0.90
            and m["top3"] >= 0.98
            and all(value >= 0.85 for value in by_size)
            and scale_drop <= 0.07
            and packet_ok
        )

    largest_wrong_fraction = 1.0 - metrics["largest"]["top1"]
    topology_shortcut = metrics["topology_only"]["top1"] >= 0.35
    non_topological = max(("largest", "earliest"), key=lambda n: metrics[n]["top1"])
    inherited_topological = max(("ancestor_coverage", "backward_slice", "relay"), key=lambda n: metrics[n]["top1"])
    best_simple = max((inherited_topological, "quiet_parent"), key=lambda n: metrics[n]["top1"])
    frontier = metrics["frontier"]["top1"]
    all_best = max(metrics, key=lambda n: metrics[n]["top1"])

    if failures or largest_wrong_fraction < 0.30:
        status = "ERC0R_INTEGRITY_INVALID"
    elif topology_shortcut:
        status = "ERC0R_CONSTRUCTION_SHORTCUT"
    elif clears_quality(non_topological) and metrics[all_best]["top1"] - metrics[non_topological]["top1"] <= 0.02:
        status = "ERC0R_NONTOPOLOGICAL_SUFFICIENT"
    elif clears_quality("ancestor_coverage") and frontier - metrics["ancestor_coverage"]["top1"] <= 0.02:
        status = "ERC0R_ANCESTOR_COVERAGE_SUFFICIENT"
    elif clears_quality("quiet_parent") and frontier - metrics["quiet_parent"]["top1"] <= 0.02:
        status = "ERC0R_QUIET_PARENT_SUFFICIENT"
    elif (
        clears_quality("frontier")
        and frontier - metrics[best_simple]["top1"] >= 0.05
        and frontier - metrics[non_topological]["top1"] >= 0.15
    ):
        status = "ERC0R_FRONTIER_ADVANCE"
    else:
        status = "ERC0R_FRESH_SEED_FAIL"

    raw_bytes = [row["raw_bytes"] for row in rows]
    frontier_packet_bytes = [row["methods"]["frontier"]["packet_bytes"] for row in rows]
    ratios = [raw / packet for raw, packet in zip(raw_bytes, frontier_packet_bytes) if packet]

    return {
        "unit": "ERC-0R",
        "status": status,
        "parent_terminal_status": "ERC0_SYNTHETIC_FAIL",
        "claim_scope": "fresh-seed synthetic disturbance-frontier mechanics only",
        "scientific_model_calls": 0,
        "sizes": list(sizes),
        "cases_per_size": cases_per_size,
        "case_count": len(rows),
        "seed_prefix": FRESH_SEED_PREFIX,
        "gates": {
            "quality_top1_min": 0.90,
            "quality_each_size_top1_min": 0.85,
            "quality_top3_min": 0.98,
            "scaling_drop_max": 0.07,
            "packet_capacity_max": PACKET_CAPACITY,
            "topology_only_shortcut_max_exclusive": 0.35,
            "largest_anomaly_wrong_fraction_min": 0.30,
            "non_topological_margin_min": 0.15,
            "frontier_simple_margin_min": 0.05,
            "simplicity_equivalence_band": 0.02,
        },
        "integrity": {
            "pass": not failures and largest_wrong_fraction >= 0.30,
            "failures": failures,
            "largest_anomaly_wrong_fraction": largest_wrong_fraction,
        },
        "metrics": metrics,
        "selected_controls": {
            "best_non_topological": non_topological,
            "best_inherited_topological": inherited_topological,
            "best_simple_before_frontier": best_simple,
            "best_overall": all_best,
        },
        "frontier_compression": {
            "median_raw_bytes": statistics.median(raw_bytes),
            "median_packet_bytes": statistics.median(frontier_packet_bytes),
            "median_raw_to_packet_ratio": statistics.median(ratios),
            "minimum_raw_to_packet_ratio": min(ratios),
        },
        "rows_sha256": sha256_text(canonical_json(rows)),
        "rows": rows,
    }


def compact_report(report: dict):
    value = dict(report)
    value.pop("rows", None)
    value["record_sha256"] = sha256_text(canonical_json(value))
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = compact_report(run_benchmark())
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
