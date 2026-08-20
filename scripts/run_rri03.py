#!/usr/bin/env python3
"""Evaluate frozen RRI-02B models on the preregistered RRI-03 stress matrix."""

from __future__ import annotations

import hashlib
import json
import statistics
import subprocess
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gri_models.data import GraphExample, NUM_RELATIONS, RELATIONS, RELATION_TO_INDEX
from gri_models.gri05 import build_model
from gri_models.rri01 import tensor_state_hash
from gri_models.resume import load_checkpoint


INPUT_DIR = ROOT / "artifacts/rri02b"
OUTPUT_DIR = ROOT / "artifacts/rri03"
CHECKPOINT_DIR = INPUT_DIR / "checkpoints"
SEEDS = (1337, 1338, 1339, 1340, 1341)
RELATION_NAMES = tuple(r.value for r in RELATIONS)
SCENARIOS = (
    "depth_128", "depth_256", "depth_512",
    "scale_128", "scale_256", "scale_512", "scale_1024",
    "branching_paths", "distractor_paths", "simultaneous_chains", "new_compositions",
    "irrelevant_edges", "missing_irrelevant_facts", "contradictory_distractors",
)
FAMILIES = {
    "depth": ("depth_128", "depth_256", "depth_512"),
    "scale": ("scale_128", "scale_256", "scale_512", "scale_1024"),
    "structure": ("branching_paths", "distractor_paths", "simultaneous_chains", "new_compositions"),
    "corruption": ("irrelevant_edges", "missing_irrelevant_facts", "contradictory_distractors"),
}
SCENARIO_STEPS = {
    "depth_128": 128, "depth_256": 256, "depth_512": 512,
    "scale_128": 16, "scale_256": 16, "scale_512": 16, "scale_1024": 16,
    "branching_paths": 32, "distractor_paths": 32, "simultaneous_chains": 32,
    "new_compositions": 32, "irrelevant_edges": 32,
    "missing_irrelevant_facts": 32, "contradictory_distractors": 32,
}
PARAMETERS = 30_912


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def add_chain(edges: list[tuple[int, str, int]], start: int, length: int, relation: str) -> None:
    for offset in range(length):
        edges.append((start + offset, relation, start + offset + 1))


def build_case(scenario: str, case_index: int) -> dict:
    relation = RELATION_NAMES[case_index % len(RELATION_NAMES)]
    edges: list[tuple[int, str, int]] = []
    metadata = {"scenario": scenario, "case_index": case_index, "target_relation": relation}
    if scenario.startswith("depth_"):
        length = int(scenario.split("_")[1])
        n = length + 1
        add_chain(edges, 0, length, relation)
        query = (0, length)
        metadata.update({"chain_length": length, "entity_count": n})
    elif scenario.startswith("scale_"):
        n = int(scenario.split("_")[1])
        add_chain(edges, 0, 4, relation)
        for start in range(5, n - 1, 3):
            edges.append((start, RELATION_NAMES[(case_index + start) % len(RELATION_NAMES)], start + 1))
        query = (0, 4)
        metadata.update({"chain_length": 4, "entity_count": n, "distractors_disconnected": True})
    elif scenario == "branching_paths":
        n = 128
        add_chain(edges, 0, 12, relation)
        cursor = 13
        for path_node in range(0, 12, 2):
            edges.append((path_node, relation, cursor))
            edges.append((cursor, relation, cursor + 1))
            cursor += 2
        query = (0, 12)
        metadata.update({"chain_length": 12, "entity_count": n, "branch_count": 6})
    elif scenario == "distractor_paths":
        n = 128
        add_chain(edges, 0, 16, relation)
        cursor = 17
        for branch in range(6):
            distractor_relation = RELATION_NAMES[(case_index + branch + 1) % len(RELATION_NAMES)]
            add_chain(edges, cursor, 8 + branch % 3, distractor_relation)
            cursor += 9 + branch % 3
        query = (0, 16)
        metadata.update({"chain_length": 16, "entity_count": n, "disconnected_path_count": 6})
    elif scenario == "simultaneous_chains":
        n = 128
        chain_length = 8
        selected = case_index % 8
        for chain in range(8):
            chain_relation = RELATION_NAMES[chain]
            start = chain * (chain_length + 1)
            add_chain(edges, start, chain_length, chain_relation)
        start = selected * (chain_length + 1)
        relation = RELATION_NAMES[selected]
        query = (start, start + chain_length)
        metadata.update({"chain_length": chain_length, "entity_count": n, "simultaneous_chain_count": 8})
    elif scenario == "new_compositions":
        n = 128
        segment_lengths = (7, 8, 9)
        cursor = 0
        for segment_length in segment_lengths:
            add_chain(edges, cursor, segment_length, relation)
            cursor += segment_length
        query = (0, cursor)
        metadata.update({"segment_lengths": segment_lengths, "chain_length": sum(segment_lengths), "entity_count": n, "facts_order_reversed": True})
        edges.reverse()
    elif scenario == "irrelevant_edges":
        n = 128
        add_chain(edges, 0, 8, relation)
        for start in range(9, 126, 2):
            edges.append((start, RELATION_NAMES[(case_index + start) % len(RELATION_NAMES)], start + 1))
        query = (0, 8)
        metadata.update({"chain_length": 8, "entity_count": n, "irrelevant_edge_count": len(edges) - 8})
    elif scenario == "missing_irrelevant_facts":
        n = 128
        add_chain(edges, 0, 8, relation)
        complete_distractor = [(9 + i, RELATION_NAMES[(case_index + i + 1) % len(RELATION_NAMES)], 10 + i) for i in range(11)]
        edges.extend(edge for i, edge in enumerate(complete_distractor) if i % 2 == 0)
        query = (0, 8)
        metadata.update({"chain_length": 8, "entity_count": n, "removed_irrelevant_edge_count": 5})
    elif scenario == "contradictory_distractors":
        n = 128
        add_chain(edges, 0, 8, relation)
        cycle_relation = relation
        for i in range(4):
            edges.append((9 + i, cycle_relation, 9 + ((i + 1) % 4)))
        query = (0, 8)
        metadata.update({"chain_length": 8, "entity_count": n, "contradictory_component": "4-cycle outside query component"})
    else:
        raise ValueError(scenario)
    return {
        "sample_id": f"rri03-{scenario}-{case_index}",
        "scenario": scenario,
        "steps": SCENARIO_STEPS[scenario],
        "entity_count": n,
        "edges": [{"subject": s, "relation": r, "object": o} for s, r, o in edges],
        "query": {"subject": query[0], "object": query[1]},
        "answer": relation,
        "metadata": metadata,
    }


def generate_cases() -> dict[str, list[dict]]:
    return {scenario: [build_case(scenario, i) for i in range(8)] for scenario in SCENARIOS}


def case_to_example(case: dict) -> GraphExample:
    n = case["entity_count"]
    query_subject = case["query"]["subject"]
    query_object = case["query"]["object"]
    node_features = torch.zeros((n, 3), dtype=torch.float32)
    node_features[:, 0] = 1.0
    node_features[query_subject, 1] = 1.0
    node_features[query_object, 2] = 1.0
    edges = torch.zeros((n, n, NUM_RELATIONS), dtype=torch.float32)
    for edge in case["edges"]:
        edges[edge["subject"], edge["object"], RELATION_TO_INDEX[edge["relation"]]] = 1.0
    return GraphExample(
        node_features=node_features,
        edges=edges,
        query_subject=query_subject,
        query_object=query_object,
        label=RELATION_TO_INDEX[case["answer"]],
        sample_id=case["sample_id"],
        chain_length=case["metadata"].get("chain_length", 1),
    )


def pair_indices(edges: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    adjacency = (edges.sum(dim=-1) + edges.transpose(0, 1).sum(dim=-1)) > 0
    return adjacency.nonzero(as_tuple=True)


def fast_step(model, h: torch.Tensor, edges: torch.Tensor, senders: torch.Tensor, receivers: torch.Tensor, anchor: torch.Tensor | None):
    aggregated = torch.zeros_like(h)
    if senders.numel():
        pair = torch.cat([h[senders], h[receivers], edges[senders, receivers], edges[receivers, senders]], dim=-1)
        aggregated.index_add_(0, receivers, model.message(pair))
    context_state = h if anchor is None else (h + anchor) / 2.0
    context = torch.cat([context_state, aggregated], dim=-1)
    gate = model.gate(context)
    delta = model.delta(context)
    return model.norm(h + gate * delta)


def fast_forward(model, example: GraphExample, steps: int, kind: str) -> torch.Tensor:
    h = model.initialize(example)
    edges = example.edges.to(h.device)
    senders, receivers = pair_indices(edges)
    anchor = None if kind == "baseline" else model.make_anchor(h)
    for _ in range(steps):
        h = fast_step(model, h, edges, senders, receivers, anchor)
    a = h[example.query_subject]
    b = h[example.query_object]
    return model.readout(torch.cat([a, b, a - b, a * b], dim=-1))


def state_hash(model) -> str:
    return tensor_state_hash({k: v.detach().cpu().clone() for k, v in model.state_dict().items()})


def verify_fast_equivalence(cases: dict[str, list[dict]]) -> dict:
    checks = []
    for kind in ("baseline", "anchor"):
        model = build_model(kind, 1337)
        model.eval()
        for scenario in ("scale_128", "branching_paths"):
            example = case_to_example(cases[scenario][0])
            with torch.no_grad():
                for steps in (1, 4):
                    ordinary = model(example, steps=steps)
                    optimized = fast_forward(model, example, steps=steps, kind=kind)
                    checks.append({"kind": kind, "scenario": scenario, "steps": steps, "max_abs_error": float((ordinary - optimized).abs().max().item()), "equal": bool(torch.equal(ordinary, optimized))})
    return {"checks": checks, "pass": all(c["equal"] for c in checks)}


def evaluate_model(kind: str, seed: int, cases: dict[str, list[dict]], checkpoint: Path) -> dict:
    model = build_model(kind, seed)
    payload = load_checkpoint(checkpoint)
    model.load_state_dict(payload["model_state"])
    model.eval()
    before = state_hash(model)
    scenario_scores = {}
    case_predictions = {}
    with torch.no_grad():
        for scenario in SCENARIOS:
            scores = []
            predictions = []
            for case in cases[scenario]:
                logits = fast_forward(model, case_to_example(case), SCENARIO_STEPS[scenario], kind)
                pred = int(logits.argmax().item())
                correct = pred == RELATION_TO_INDEX[case["answer"]]
                scores.append(correct)
                predictions.append({"sample_id": case["sample_id"], "prediction": RELATION_NAMES[pred], "answer": case["answer"], "correct": correct})
            scenario_scores[scenario] = sum(scores) / len(scores)
            case_predictions[scenario] = predictions
    after = state_hash(model)
    return {"model": kind, "seed": seed, "checkpoint_sha256": sha256(checkpoint), "scenario_scores": scenario_scores, "case_predictions": case_predictions, "model_state_hash_before": before, "model_state_hash_after": after, "model_immutable": before == after}


def family_scores(report: dict) -> dict[str, float]:
    return {family: statistics.mean(report["scenario_scores"][scenario] for scenario in scenarios) for family, scenarios in FAMILIES.items()}


def stress_primary(report: dict) -> float:
    families = family_scores(report)
    return statistics.mean(families.values())


def aggregate(reports: list[dict]) -> dict:
    grouped = {"baseline": [r for r in reports if r["model"] == "baseline"], "anchor": [r for r in reports if r["model"] == "anchor"]}
    result = {}
    for kind, rows in grouped.items():
        result[kind] = {
            "per_scenario_mean": {scenario: statistics.mean(r["scenario_scores"][scenario] for r in rows) for scenario in SCENARIOS},
            "per_family_mean": {family: statistics.mean(family_scores(r)[family] for r in rows) for family in FAMILIES},
            "per_seed_primary": {str(r["seed"]): stress_primary(r) for r in rows},
            "mean_primary": statistics.mean(stress_primary(r) for r in rows),
            "primary_stdev": statistics.stdev(stress_primary(r) for r in rows),
            "model_immutable_all": all(r["model_immutable"] for r in rows),
        }
    paired = []
    for seed in SEEDS:
        b = next(r for r in grouped["baseline"] if r["seed"] == seed)
        a = next(r for r in grouped["anchor"] if r["seed"] == seed)
        paired.append({"seed": seed, "baseline_primary": stress_primary(b), "anchor_primary": stress_primary(a), "anchor_minus_baseline": stress_primary(a) - stress_primary(b), "baseline_families": family_scores(b), "anchor_families": family_scores(a)})
    result["paired"] = paired
    result["mean_primary_difference"] = statistics.mean(r["anchor_minus_baseline"] for r in paired)
    result["primary_wins"] = sum(r["anchor_minus_baseline"] > 0 for r in paired)
    result["mean_family_differences"] = {family: result["anchor"]["per_family_mean"][family] - result["baseline"]["per_family_mean"][family] for family in FAMILIES}
    return result


def verdict(agg: dict, equivalence: dict) -> dict:
    depth_delta = agg["mean_family_differences"]["depth"]
    non_depth = {family: agg["mean_family_differences"][family] for family in ("scale", "structure", "corruption")}
    gates = {
        "stress_primary_improvement_at_least_0.05": {"observed": agg["mean_primary_difference"], "pass": agg["mean_primary_difference"] >= 0.05},
        "depth_family_improvement_at_least_0.05": {"observed": depth_delta, "pass": depth_delta >= 0.05},
        "paired_primary_wins_at_least_4": {"observed": agg["primary_wins"], "pass": agg["primary_wins"] >= 4},
        "non_depth_families_not_more_than_0.05_below": {"observed": non_depth, "pass": all(value >= -0.05 for value in non_depth.values())},
        "optimized_execution_equivalence": {"observed": equivalence["pass"], "pass": equivalence["pass"]},
    }
    return {"unit": "RRI-03", "gates": gates, "terminal_verdict": "RRI_03_STRESS_ADVANTAGE" if all(g["pass"] for g in gates.values()) else "RRI_03_STRESS_NO_ADVANTAGE", "no_training": True}


def write_scenarios(cases: dict[str, list[dict]]) -> dict:
    scenario_hashes = {}
    for scenario, rows in cases.items():
        path = OUTPUT_DIR / "scenarios" / f"{scenario}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows))
        scenario_hashes[scenario] = {"path": str(path.relative_to(ROOT)), "sha256": sha256(path), "case_count": len(rows), "steps": SCENARIO_STEPS[scenario]}
    return scenario_hashes


def manifest() -> dict[str, str]:
    return {str(path.relative_to(ROOT)): sha256(path) for path in sorted(OUTPUT_DIR.rglob("*")) if path.is_file() and path.name != "SHA256SUMS.json"}


def report(agg: dict, verdict_report: dict, fast_equivalence: dict) -> str:
    rows = ["# RRI-03 — Extrapolation Stress Test", "", "Evaluation-only on frozen RRI-02B checkpoints; no training performed.", "", "## Primary and family results", "", "| Model | Depth | Scale | Structure | Corruption | P_stress |", "|---|---:|---:|---:|---:|---:|"]
    for kind in ("baseline", "anchor"):
        f = agg[kind]["per_family_mean"]
        rows.append(f"| {kind} | {f['depth']:.5f} | {f['scale']:.5f} | {f['structure']:.5f} | {f['corruption']:.5f} | {agg[kind]['mean_primary']:.5f} |")
    rows += ["", "## Paired P_stress", "", "| Seed | Baseline | Anchor | Difference |", "|---:|---:|---:|---:|"]
    for row in agg["paired"]:
        rows.append(f"| {row['seed']} | {row['baseline_primary']:.5f} | {row['anchor_primary']:.5f} | {row['anchor_minus_baseline']:.5f} |")
    rows += ["", "## Scenario means", "", "| Scenario | Baseline | Anchor | Difference |", "|---|---:|---:|---:|"]
    for scenario in SCENARIOS:
        b = agg["baseline"]["per_scenario_mean"][scenario]
        a = agg["anchor"]["per_scenario_mean"][scenario]
        rows.append(f"| {scenario} | {b:.5f} | {a:.5f} | {a-b:.5f} |")
    rows += ["", "## Gates", ""]
    for name, gate in verdict_report["gates"].items():
        rows.append(f"- {name}: **{'PASS' if gate['pass'] else 'FAIL'}** (`{gate['observed']}`)")
    rows += ["", "Fast sparse execution equivalence: **PASS**", "", "Seed 1341 remains included; its paired result is in `aggregate.json`.", "", "## Terminal verdict", "", f"`{verdict_report['terminal_verdict']}`"]
    return "\n".join(rows) + "\n"


def main() -> int:
    torch.set_num_threads(1)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    input_manifest = json.loads((INPUT_DIR / "SHA256SUMS.json").read_text())
    checkpoint_paths = {}
    for kind in ("baseline", "anchor"):
        for seed in SEEDS:
            rel = f"artifacts/rri02b/checkpoints/{kind}_seed{seed}_final.pt"
            path = ROOT / rel
            if sha256(path) != input_manifest[rel]:
                raise RuntimeError(f"RRI-03 input checkpoint hash mismatch: {rel}")
            checkpoint_paths[(kind, seed)] = path
    cases = generate_cases()
    fast_equivalence = verify_fast_equivalence(cases)
    if not fast_equivalence["pass"]:
        raise RuntimeError("RRI_03_FAST_EXECUTION_INVALID")
    scenario_manifest = write_scenarios(cases)
    config = {
        "unit": "RRI-03", "analysis_commit": commit(), "evaluation_only": True, "no_training": True,
        "input_evidence": "artifacts/rri02b", "parameters": PARAMETERS, "seeds": list(SEEDS),
        "scenario_count": len(SCENARIOS), "cases_per_scenario": 8, "scenario_steps": SCENARIO_STEPS,
        "families": FAMILIES, "primary_metric": "mean(equal-weight depth, scale, structure, corruption family means)",
        "gates": {"primary_delta": 0.05, "depth_delta": 0.05, "paired_wins": 4, "non_depth_floor": -0.05},
        "fast_execution_equivalence": fast_equivalence,
    }
    write_json(OUTPUT_DIR / "RRI03_CONFIG.json", config)
    write_json(OUTPUT_DIR / "foundation_identity.json", {"rri02c_terminal": "RRI_02C_ANCHOR_MECHANISM_SUPPORTED", "rri02b_evidence_commit": "2ffcf03", "world0": "GRI_02_WORLD0_PASS", "so4_status": "REJECTED", "anchor_parameters": PARAMETERS, "baseline_parameters": PARAMETERS})
    write_json(OUTPUT_DIR / "input_manifest.json", {"path": str((INPUT_DIR / "SHA256SUMS.json").relative_to(ROOT)), "sha256": sha256(INPUT_DIR / "SHA256SUMS.json"), "checkpoints": {f"{kind}_seed{seed}": sha256(path) for (kind, seed), path in sorted(checkpoint_paths.items())}})
    write_json(OUTPUT_DIR / "scenario_manifest.json", scenario_manifest)

    reports = []
    for kind in ("baseline", "anchor"):
        for seed in SEEDS:
            result = evaluate_model(kind, seed, cases, checkpoint_paths[(kind, seed)])
            reports.append(result)
            write_json(OUTPUT_DIR / f"{kind}_seed{seed}.json", result)
    aggregate_report = aggregate(reports)
    verdict_report = verdict(aggregate_report, fast_equivalence)
    write_json(OUTPUT_DIR / "aggregate.json", aggregate_report)
    write_json(OUTPUT_DIR / "RRI03_VERDICT.json", verdict_report)
    (OUTPUT_DIR / "RRI03_REPORT.md").write_text(report(aggregate_report, verdict_report, fast_equivalence))
    write_json(OUTPUT_DIR / "SHA256SUMS.json", manifest())
    print(verdict_report["terminal_verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
