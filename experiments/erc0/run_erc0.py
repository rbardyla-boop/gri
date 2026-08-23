from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


REGISTERED_SIZES = (32, 128, 512, 2048)
REGISTERED_CASES_PER_SIZE = 24
ANOMALY_THRESHOLD = 2.5
PACKET_CAPACITY = 16


@dataclass(frozen=True)
class NodeSignal:
    node_id: str
    pre: tuple[float, ...]
    post: tuple[float, ...]
    source_sha256: str


@dataclass(frozen=True)
class VisibleCase:
    case_id: str
    node_ids: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]
    signals: tuple[NodeSignal, ...]


@dataclass(frozen=True)
class Truth:
    root_id: str
    affected_ids: tuple[str, ...]


@dataclass(frozen=True)
class Feature:
    node_id: str
    score: float
    onset: Optional[int]
    source_sha256: str


@dataclass(frozen=True)
class MethodResult:
    ranking: tuple[str, ...]
    packet: tuple[dict, ...] = ()
    packet_sha256: Optional[str] = None


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def signal_payload(node_id: str, pre: Iterable[float], post: Iterable[float]) -> dict:
    return {"node_id": node_id, "pre": list(pre), "post": list(post)}


def signal_sha256(node_id: str, pre: Iterable[float], post: Iterable[float]) -> str:
    return sha256_text(canonical_json(signal_payload(node_id, pre, post)))


def _noise(rng: random.Random) -> float:
    # Bounded approximately bell-shaped noise using only random.random().
    return round((sum(rng.random() for _ in range(6)) - 3.0) * 0.18, 6)


def _children_from_internal(parents: list[list[int]]) -> list[list[int]]:
    children = [[] for _ in parents]
    for child, ps in enumerate(parents):
        for parent in ps:
            children[parent].append(child)
    return children


def _descendant_counts_internal(children: list[list[int]]) -> list[int]:
    n = len(children)
    bits = [0] * n
    for node in range(n - 1, -1, -1):
        value = 0
        for child in children[node]:
            value |= 1 << child
            value |= bits[child]
        bits[node] = value
    return [value.bit_count() for value in bits]


def _make_internal_graph(n: int, rng: random.Random) -> list[list[int]]:
    parents: list[list[int]] = [[] for _ in range(n)]
    for child in range(1, n):
        # A random recursive backbone guarantees connectivity; occasional second
        # parents create convergent paths without violating acyclicity.
        primary = rng.randrange(child)
        parents[child].append(primary)
        if child >= 4 and rng.random() < 0.22:
            secondary = rng.randrange(child)
            if secondary != primary:
                parents[child].append(secondary)
    return parents


def _distances_from_root(parents: list[list[int]], root: int) -> list[Optional[int]]:
    dist: list[Optional[int]] = [None] * len(parents)
    dist[root] = 0
    for node in range(root + 1, len(parents)):
        upstream = [dist[p] for p in parents[node] if dist[p] is not None]
        if upstream:
            dist[node] = 1 + min(int(x) for x in upstream)
    return dist


def generate_case(n: int, seed: int) -> tuple[VisibleCase, Truth]:
    rng = random.Random(seed)

    # Regenerate only graph structure until there are enough nontrivial roots.
    while True:
        parents = _make_internal_graph(n, rng)
        children = _children_from_internal(parents)
        desc_counts = _descendant_counts_internal(children)
        eligible = [i for i, count in enumerate(desc_counts) if 3 <= count <= max(8, int(0.85 * n))]
        if eligible:
            break

    root = rng.choice(eligible)
    dist = _distances_from_root(parents, root)
    affected = {i for i, d in enumerate(dist) if d is not None}

    # Opaque labels destroy any direct relation between internal topological index
    # and the identifier shown to candidate methods.
    labels = [f"Q{value:08x}" for value in range(n)]
    rng.shuffle(labels)
    visible_id = {i: labels[i] for i in range(n)}

    root_amp = 1.05 + 0.45 * rng.random()
    shifts = [0.0] * n
    onsets: list[Optional[int]] = [None] * n

    for node in affected:
        depth = int(dist[node] or 0)
        if node == root:
            shift = root_amp
            onset = 1
        else:
            # Downstream symptoms may be substantially larger than the root.
            shift = root_amp * (0.82 + 0.55 * rng.random()) * (1.0 + 0.13 * min(depth, 6))
            onset = min(18, 1 + 2 * depth + rng.randrange(3))
            # Sensor weakness/dropout without deleting the underlying component.
            if rng.random() < 0.10:
                shift *= 0.28
        shifts[node] = shift
        onsets[node] = onset

    unaffected = [i for i in range(n) if i not in affected]
    distractor_count = min(len(unaffected), max(2, n // 64))
    for node in rng.sample(unaffected, distractor_count) if distractor_count else []:
        shifts[node] = 1.35 + 2.35 * rng.random()
        onsets[node] = rng.randrange(0, 19)

    signals: list[NodeSignal] = []
    for node in range(n):
        base = -0.5 + rng.random()
        pre = tuple(round(base + _noise(rng), 6) for _ in range(24))
        post_values = []
        for t in range(24):
            value = base + _noise(rng)
            if onsets[node] is not None and t >= int(onsets[node]):
                value += shifts[node]
            post_values.append(round(value, 6))
        post = tuple(post_values)
        nid = visible_id[node]
        digest = signal_sha256(nid, pre, post)
        signals.append(NodeSignal(nid, pre, post, digest))

    edges = []
    for child, ps in enumerate(parents):
        for parent in ps:
            edges.append((visible_id[parent], visible_id[child]))

    # Sort all model-visible records by opaque ID, not by topological position.
    node_ids = tuple(sorted(labels))
    signals.sort(key=lambda x: x.node_id)
    edges.sort()

    case_id = f"ERC0-N{n}-S{seed}"
    visible = VisibleCase(case_id, node_ids, tuple(edges), tuple(signals))
    truth = Truth(visible_id[root], tuple(sorted(visible_id[i] for i in affected)))
    return visible, truth


def _quartiles(values: tuple[float, ...]) -> tuple[float, float]:
    ordered = sorted(values)
    n = len(ordered)
    lower = ordered[: n // 2]
    upper = ordered[(n + 1) // 2 :]
    return statistics.median(lower), statistics.median(upper)


def extract_feature(signal: NodeSignal) -> Feature:
    baseline = statistics.median(signal.pre)
    post_med = statistics.median(signal.post)
    mad = statistics.median(abs(x - baseline) for x in signal.pre)
    q1, q3 = _quartiles(signal.pre)
    iqr = q3 - q1
    diffs = tuple(signal.pre[i + 1] - signal.pre[i] for i in range(len(signal.pre) - 1))
    diff_scale = statistics.pstdev(diffs) / math.sqrt(2.0) if diffs else 0.0
    scale = max(1.4826 * mad, iqr / 1.349, diff_scale, 0.03)
    score = min(30.0, abs(post_med - baseline) / scale)
    threshold = max(3.0 * scale, 0.22)
    onset = None
    for idx, value in enumerate(signal.post):
        if abs(value - baseline) >= threshold:
            onset = idx
            break
    return Feature(signal.node_id, round(score, 9), onset, signal.source_sha256)


def extract_features(case: VisibleCase) -> dict[str, Feature]:
    return {signal.node_id: extract_feature(signal) for signal in case.signals}


class GraphIndex:
    def __init__(self, case: VisibleCase):
        self.nodes = tuple(case.node_ids)
        self.index = {node: i for i, node in enumerate(self.nodes)}
        self.parents = {node: [] for node in self.nodes}
        self.children = {node: [] for node in self.nodes}
        indegree = {node: 0 for node in self.nodes}
        for parent, child in case.edges:
            self.parents[child].append(parent)
            self.children[parent].append(child)
            indegree[child] += 1

        ready = sorted(node for node, degree in indegree.items() if degree == 0)
        topo = []
        while ready:
            node = ready.pop(0)
            topo.append(node)
            for child in sorted(self.children[node]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
                    ready.sort()
        if len(topo) != len(self.nodes):
            raise ValueError("ERC0 graph is not acyclic")
        self.topo = tuple(topo)

        self.desc_bits: dict[str, int] = {}
        for node in reversed(self.topo):
            bits = 0
            for child in self.children[node]:
                bits |= 1 << self.index[child]
                bits |= self.desc_bits[child]
            self.desc_bits[node] = bits

        self.anc_bits: dict[str, int] = {}
        for node in self.topo:
            bits = 0
            for parent in self.parents[node]:
                bits |= 1 << self.index[parent]
                bits |= self.anc_bits[parent]
            self.anc_bits[node] = bits

    def descendants(self, node: str) -> set[str]:
        bits = self.desc_bits[node]
        return {candidate for candidate in self.nodes if bits & (1 << self.index[candidate])}

    def ancestors(self, node: str) -> set[str]:
        bits = self.anc_bits[node]
        return {candidate for candidate in self.nodes if bits & (1 << self.index[candidate])}

    def is_descendant(self, upstream: str, downstream: str) -> bool:
        return bool(self.desc_bits[upstream] & (1 << self.index[downstream]))


def _anomalous(features: dict[str, Feature]) -> list[Feature]:
    values = [feature for feature in features.values() if feature.score >= ANOMALY_THRESHOLD and feature.onset is not None]
    if values:
        return values
    return sorted(features.values(), key=lambda f: (-f.score, f.node_id))[:1]


def _coherent_coverage(node: str, features: dict[str, Feature], graph: GraphIndex) -> tuple[float, int]:
    source = features[node]
    if source.onset is None:
        return 0.0, 0
    anomalies = _anomalous(features)
    total_weight = sum(f.score for f in anomalies) or 1.0
    covered_weight = source.score
    covered_count = 1
    for feature in anomalies:
        if feature.node_id == node or feature.onset is None:
            continue
        if graph.is_descendant(node, feature.node_id) and feature.onset >= source.onset:
            covered_weight += feature.score
            covered_count += 1
    return covered_weight / total_weight, covered_count


def rank_random(case: VisibleCase, features: dict[str, Feature], graph: GraphIndex) -> tuple[str, ...]:
    del features, graph
    return tuple(sorted(case.node_ids, key=lambda node: sha256_text(case.case_id + "|" + node)))


def rank_topology_only(case: VisibleCase, features: dict[str, Feature], graph: GraphIndex) -> tuple[str, ...]:
    del case, features
    return tuple(sorted(graph.nodes, key=lambda n: (-graph.desc_bits[n].bit_count(), n)))


def rank_largest(case: VisibleCase, features: dict[str, Feature], graph: GraphIndex) -> tuple[str, ...]:
    del case, graph
    return tuple(sorted(features, key=lambda n: (-features[n].score, n)))


def rank_earliest(case: VisibleCase, features: dict[str, Feature], graph: GraphIndex) -> tuple[str, ...]:
    del case, graph
    return tuple(
        sorted(
            features,
            key=lambda n: (
                features[n].onset if features[n].onset is not None else 10**9,
                -features[n].score,
                n,
            ),
        )
    )


def rank_ancestor_coverage(case: VisibleCase, features: dict[str, Feature], graph: GraphIndex) -> tuple[str, ...]:
    del case
    scored = []
    for node in features:
        coverage, count = _coherent_coverage(node, features, graph)
        scored.append((node, coverage, count))
    return tuple(
        node
        for node, _, _ in sorted(
            scored,
            key=lambda item: (
                -item[1],
                -item[2],
                features[item[0]].onset if features[item[0]].onset is not None else 10**9,
                -features[item[0]].score,
                item[0],
            ),
        )
    )


def rank_backward_slice(case: VisibleCase, features: dict[str, Feature], graph: GraphIndex) -> tuple[str, ...]:
    del case
    symptoms = sorted(_anomalous(features), key=lambda f: (-f.score, f.node_id))[:3]
    allowed: set[str] = set()
    for symptom in symptoms:
        allowed.add(symptom.node_id)
        allowed.update(graph.ancestors(symptom.node_id))

    def key(node: str) -> tuple:
        coverage, count = _coherent_coverage(node, features, graph)
        feature = features[node]
        anomalous_penalty = 0 if feature.score >= ANOMALY_THRESHOLD and feature.onset is not None else 1
        return (
            anomalous_penalty,
            feature.onset if feature.onset is not None else 10**9,
            -coverage,
            -count,
            -feature.score,
            node,
        )

    primary = sorted(allowed, key=key)
    remainder = sorted((node for node in graph.nodes if node not in allowed), key=key)
    return tuple(primary + remainder)


def rank_relay(case: VisibleCase, features: dict[str, Feature], graph: GraphIndex) -> tuple[str, ...]:
    del case
    anomalies = _anomalous(features)
    max_score = max((f.score for f in anomalies), default=1.0)
    finite_onsets = [f.onset for f in anomalies if f.onset is not None]
    max_onset = max(finite_onsets) if finite_onsets else 1
    scored = []
    for node, feature in features.items():
        coverage, count = _coherent_coverage(node, features, graph)
        local = min(1.0, feature.score / max_score) if max_score else 0.0
        if feature.onset is None:
            early = 0.0
            observable = 0.0
        else:
            early = 1.0 - min(1.0, feature.onset / max(1, max_onset))
            observable = 1.0 if feature.score >= ANOMALY_THRESHOLD else 0.25
        # Fixed before benchmark execution. Coverage carries most weight; local
        # anomaly and onset only break/temper topology-heavy explanations.
        relay = observable * (0.68 * coverage + 0.22 * local + 0.10 * early)
        scored.append((node, relay, coverage, count))
    return tuple(
        node
        for node, _, _, _ in sorted(
            scored,
            key=lambda item: (-item[1], -item[2], -item[3], item[0]),
        )
    )


METHODS = {
    "random": rank_random,
    "topology_only": rank_topology_only,
    "largest": rank_largest,
    "earliest": rank_earliest,
    "ancestor_coverage": rank_ancestor_coverage,
    "backward_slice": rank_backward_slice,
    "relay": rank_relay,
}


def build_packet(case: VisibleCase, ranking: tuple[str, ...], features: dict[str, Feature], graph: GraphIndex) -> tuple[tuple[dict, ...], str]:
    candidate = ranking[0]
    source = features[candidate]
    records = [
        {
            "node_id": candidate,
            "score": source.score,
            "onset": source.onset,
            "source_sha256": source.source_sha256,
            "reason": "candidate",
        }
    ]
    coherent = []
    for feature in _anomalous(features):
        if feature.node_id == candidate or feature.onset is None or source.onset is None:
            continue
        if graph.is_descendant(candidate, feature.node_id) and feature.onset >= source.onset:
            coherent.append(feature)
    coherent.sort(key=lambda f: (-f.score, f.onset if f.onset is not None else 10**9, f.node_id))
    for feature in coherent[: PACKET_CAPACITY - 1]:
        records.append(
            {
                "node_id": feature.node_id,
                "score": feature.score,
                "onset": feature.onset,
                "source_sha256": feature.source_sha256,
                "reason": "coherent_downstream",
            }
        )
    digest = sha256_text(canonical_json(records))
    return tuple(records), digest


def verify_source_hashes(case: VisibleCase) -> bool:
    return all(signal.source_sha256 == signal_sha256(signal.node_id, signal.pre, signal.post) for signal in case.signals)


def verify_packet(case: VisibleCase, packet: tuple[dict, ...], packet_sha256: str) -> bool:
    if len(packet) > PACKET_CAPACITY:
        return False
    source_map = {signal.node_id: signal for signal in case.signals}
    for record in packet:
        signal = source_map.get(record["node_id"])
        if signal is None or signal.source_sha256 != record["source_sha256"]:
            return False
        if signal.source_sha256 != signal_sha256(signal.node_id, signal.pre, signal.post):
            return False
    return packet_sha256 == sha256_text(canonical_json(list(packet)))


def _case_seeds(size: int, cases_per_size: int) -> tuple[int, ...]:
    base = 2026082300 + size * 1000
    return tuple(base + i for i in range(cases_per_size))


def run_benchmark(sizes: tuple[int, ...] = REGISTERED_SIZES, cases_per_size: int = REGISTERED_CASES_PER_SIZE) -> dict:
    rows = []
    integrity_failures = []
    for size in sizes:
        for seed in _case_seeds(size, cases_per_size):
            case, truth = generate_case(size, seed)
            if hasattr(case, "root_id"):
                integrity_failures.append(f"{case.case_id}: truth leaked into visible case")
            if not verify_source_hashes(case):
                integrity_failures.append(f"{case.case_id}: source hash mismatch")
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
                if set(ranking) != set(case.node_ids) or len(ranking) != len(case.node_ids):
                    integrity_failures.append(f"{case.case_id}:{name}: invalid ranking coverage")
                packet = ()
                packet_sha = None
                packet_bytes = None
                packet_ok = None
                if name in {"ancestor_coverage", "backward_slice", "relay"}:
                    packet, packet_sha = build_packet(case, ranking, features, graph)
                    packet_ok = verify_packet(case, packet, packet_sha)
                    packet_bytes = len(canonical_json(list(packet)).encode("utf-8"))
                    if not packet_ok:
                        integrity_failures.append(f"{case.case_id}:{name}: packet provenance invalid")
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
        selected = [row for row in rows]
        top1 = sum(int(row["methods"][name]["top1"]) for row in selected) / len(selected)
        top3 = sum(int(row["methods"][name]["top3"]) for row in selected) / len(selected)
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

    largest_wrong_fraction = 1.0 - metrics["largest"]["top1"]
    topology_shortcut = metrics["topology_only"]["top1"] >= 0.35

    def clears_quality(name: str) -> bool:
        m = metrics[name]
        size_values = [m["by_size"][str(size)]["top1"] for size in sizes]
        scaling_drop = max(0.0, size_values[0] - size_values[-1])
        packet_ok = m["max_packet_count"] is None or m["max_packet_count"] <= PACKET_CAPACITY
        return (
            m["top1"] >= 0.85
            and m["top3"] >= 0.95
            and all(value >= 0.75 for value in size_values)
            and scaling_drop <= 0.10
            and packet_ok
        )

    non_topological = max(("largest", "earliest"), key=lambda n: metrics[n]["top1"])
    simple_topological = max(("ancestor_coverage", "backward_slice"), key=lambda n: metrics[n]["top1"])
    relay = metrics["relay"]["top1"]

    if integrity_failures or largest_wrong_fraction < 0.30:
        status = "ERC0_INTEGRITY_INVALID"
    elif topology_shortcut:
        status = "ERC0_CONSTRUCTION_SHORTCUT"
    elif clears_quality(non_topological) and (max(m["top1"] for m in metrics.values()) - metrics[non_topological]["top1"] <= 0.02):
        status = "ERC0_NONTOPOLOGICAL_SUFFICIENT"
    elif clears_quality(simple_topological) and relay - metrics[simple_topological]["top1"] <= 0.02:
        status = "ERC0_SIMPLE_SLICE_SUFFICIENT"
    elif (
        clears_quality("relay")
        and relay - metrics[simple_topological]["top1"] >= 0.05
        and relay - metrics[non_topological]["top1"] >= 0.15
    ):
        status = "ERC0_RELAY_ADVANCE"
    else:
        status = "ERC0_SYNTHETIC_FAIL"

    raw_bytes = [row["raw_bytes"] for row in rows]
    relay_packet_bytes = [row["methods"]["relay"]["packet_bytes"] for row in rows]
    compression = [raw / packet for raw, packet in zip(raw_bytes, relay_packet_bytes) if packet]

    return {
        "unit": "ERC-0",
        "status": status,
        "claim_scope": "synthetic transparent fault-localization mechanics only",
        "scientific_model_calls": 0,
        "sizes": list(sizes),
        "cases_per_size": cases_per_size,
        "case_count": len(rows),
        "gates": {
            "quality_top1_min": 0.85,
            "quality_each_size_top1_min": 0.75,
            "quality_top3_min": 0.95,
            "packet_capacity_max": PACKET_CAPACITY,
            "scaling_drop_max": 0.10,
            "topology_only_shortcut_max_exclusive": 0.35,
            "largest_anomaly_must_be_wrong_fraction_min": 0.30,
            "topology_claim_non_topological_margin_min": 0.15,
            "erc_specific_simple_margin_min": 0.05,
            "simplicity_equivalence_band": 0.02,
        },
        "integrity": {
            "pass": not integrity_failures and largest_wrong_fraction >= 0.30,
            "failures": integrity_failures,
            "largest_anomaly_wrong_fraction": largest_wrong_fraction,
            "source_provenance_all_pass": not any("source hash" in value or "packet provenance" in value for value in integrity_failures),
        },
        "metrics": metrics,
        "selected_controls": {
            "best_non_topological": non_topological,
            "best_simple_topological": simple_topological,
        },
        "relay_compression": {
            "median_raw_bytes": statistics.median(raw_bytes),
            "median_packet_bytes": statistics.median(relay_packet_bytes),
            "median_raw_to_packet_ratio": statistics.median(compression),
            "minimum_raw_to_packet_ratio": min(compression),
        },
        "rows_sha256": sha256_text(canonical_json(rows)),
        "rows": rows,
    }


def report_without_rows(report: dict) -> dict:
    value = dict(report)
    value.pop("rows", None)
    value["record_sha256"] = sha256_text(canonical_json(value))
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = run_benchmark()
    compact = report_without_rows(report)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(compact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(compact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
