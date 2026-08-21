#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import platform
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dmc00.benchmark import VALUES  # noqa: E402
from dmc01.memory import TRAIN_DEPTH, encode_event  # noqa: E402
from dmc02p.controller import (  # noqa: E402
    CAPACITY,
    RANDOM_CONTROL_SEED,
    ExactRetention16Controller,
    FIFO16Controller,
    MemoryRecord,
    Random16Controller,
    load_dmc01_checkpoint,
)


EVIDENCE_SEEDS = (1337, 1338, 1339, 1340, 1341)
WORLD0_COMMIT = "1200050d1bbe99a7158e8482dacc534feb48d4c1"
DMC00_COMMIT = "0e5359d"
DMC01_COMMIT = "48ae98f"
DMC02A_COMMIT = "f10394d"
DMC02P_COMMIT = "c8705cb"
ARTIFACT_DIR = ROOT / "artifacts/dmc02"
DMC02A_DIR = ROOT / "artifacts/dmc02a"
DMC01_DIR = ROOT / "artifacts/dmc01"
FUTURE_PRIMARY = "mean(M256,M1024,SAL256,SAL1024,SUP_current_1024,SUP_history_1024,SHIFT,FLOOD512,FLOOD1024)"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def verify_manifest(root: Path) -> dict[str, Any]:
    manifest_path = root / "SHA256SUMS.json"
    if not manifest_path.exists():
        return {"root": str(root.relative_to(ROOT)), "entries": 0, "manifest_available": False, "pass": True, "errors": [], "verification_basis": "frozen_git_commit_boundary"}
    manifest = json.loads(manifest_path.read_text())
    errors = []
    for relative, expected in manifest.items():
        path = root / relative
        if not path.exists():
            errors.append({"path": relative, "error": "missing"})
        elif sha256(path) != expected:
            errors.append({"path": relative, "error": "sha256_mismatch"})
    return {"root": str(root.relative_to(ROOT)), "entries": len(manifest), "manifest_available": True, "pass": not errors, "errors": errors, "verification_basis": "recorded_SHA256SUMS"}


def read_dataset() -> dict[str, list[dict[str, Any]]]:
    manifest = json.loads((DMC02A_DIR / "dataset_manifest.json").read_text())
    return {split: [json.loads(line) for line in (ROOT / row["path"]).read_text().splitlines() if line] for split, row in manifest.items()}


def model_state_hash(processor: torch.nn.Module) -> str:
    digest = hashlib.sha256()
    for name, tensor in processor.state_dict().items():
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(tensor.dtype).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(tuple(tensor.shape)).encode("ascii"))
        digest.update(b"\0")
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def query_logits(processor: torch.nn.Module, query: dict[str, Any], hidden: torch.Tensor) -> torch.Tensor:
    graph = encode_event(query)
    h0 = processor.initialize(graph)
    anchor = processor.make_anchor(h0)
    h = h0.clone()
    h[graph.query_object] = h[graph.query_object] + hidden.to(h.device)
    for _ in range(TRAIN_DEPTH):
        h = processor.recurrent_step(h, graph.edges.to(h.device), anchor)
    return processor.readout_hidden(h, graph.query_subject, graph.query_object)


def retrieve_unbounded(records: list[MemoryRecord], query: dict[str, Any]) -> MemoryRecord | None:
    matches = [record for record in records if record.entity == query["entity"] and record.field == query["field"]]
    if query["mode"] == "history":
        matches = [record for record in matches if record.creation_episode <= query["as_of_episode"]]
    return max(matches, key=lambda record: record.creation_episode) if matches else None


def hidden_cache(controller: ExactRetention16Controller) -> dict[str, torch.Tensor]:
    result = {}
    with torch.no_grad():
        for index, value in enumerate(VALUES):
            event = {"kind": "write", "memory_id": f"hidden-cache-{index}", "entity": "hidden-cache", "field": "value", "value": value, "salience": None, "supersedes": None}
            result[value] = controller.encode_hidden(event).detach().cpu().clone()
    return result


def instrument_firewall(controller: ExactRetention16Controller) -> list[dict[str, Any]]:
    observed: list[dict[str, Any]] = []
    original = controller.ledger.policy.admits

    def audited(metadata):
        observed.append({"fields": sorted(metadata.__dict__), "values_recorded": False})
        return original(metadata)

    controller.ledger.policy.admits = audited
    return observed


def evaluate_seed(seed: int, dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    checkpoint = DMC01_DIR / "checkpoints" / f"exact_seed{seed}_final.pt"
    exact, payload = load_dmc01_checkpoint(checkpoint, family="mission_set", mode="exact16", case_id=f"seed-{seed}-exact")
    processor = exact.processor
    fifo = FIFO16Controller(processor, family="mission_set", case_id=f"seed-{seed}-fifo")
    random_controller = Random16Controller(processor, family="mission_set", case_id=f"seed-{seed}-random", seed=RANDOM_CONTROL_SEED)
    controllers = {"exact": exact, "fifo": fifo, "random": random_controller}
    # The family is changed per case before any event is processed. The same
    # processor object is shared; no checkpoint is rebuilt or retrained.
    before_hash = model_state_hash(processor)
    exact_decisions = instrument_firewall(exact)
    cache = hidden_cache(exact)
    condition_hits = {mode: defaultdict(list) for mode in controllers}
    capacity_rows = []
    continuity_rows = []
    hidden_total = 0
    hidden_mismatches = 0

    processor.eval()
    with torch.no_grad():
        for split, cases in dataset.items():
            for case in cases:
                for controller in controllers.values():
                    controller.reset_case()
                    controller.family = case["family"]
                    if controller.mode == "exact16":
                        controller.ledger.policy.family = case["family"]
                # Replace the exact policy with a fresh family-specific one;
                # this prevents state from the previous case from surviving.
                exact.ledger.policy.family = case["family"]
                exact.ledger.policy.active_entities = None
                unbounded: list[MemoryRecord] = []
                peaks = {mode: 0 for mode in controllers}
                violations = {mode: 0 for mode in controllers}
                for episode in case["episodes"]:
                    event = episode["events"][0]
                    if event["kind"] in {"mission_set", "mission_update"}:
                        for mode, controller in controllers.items():
                            controller.process_scope_event(event)
                    elif event["kind"] == "write":
                        hidden = cache[event["value"]]
                        records = {}
                        for mode, controller in controllers.items():
                            record = controller.make_record(event, episode["index"], hidden_value=hidden.clone())
                            records[mode] = record
                            controller.retain_record(record)
                            hidden_total += 1
                            if not torch.equal(record.hidden_value, hidden):
                                hidden_mismatches += 1
                        # This is a diagnostic unbounded reference only; it is
                        # never accessible to a retention decision or query
                        # controller and is not counted as physical memory.
                        unbounded.append(records["exact"])
                    elif event["kind"] == "query":
                        query = event
                        retrieved = {mode: None for mode in controllers}
                        for mode, controller in controllers.items():
                            try:
                                retrieved[mode] = controller.retrieve(query)
                            except LookupError:
                                retrieved[mode] = None
                            record = retrieved[mode]
                            if record is None:
                                hit = False
                            else:
                                logits = query_logits(processor, query, record.hidden_value)
                                hit = int(logits.argmax().item()) == VALUES.index(case["answer"])
                            condition_hits[mode][(split, case["family"], case["condition"])].append(hit)
                        exact_record = retrieved["exact"]
                        unbounded_record = retrieve_unbounded(unbounded, query)
                        if exact_record is None or unbounded_record is None:
                            continuity_rows.append({"case_id": case["case_id"], "identity": exact_record is None and unbounded_record is None})
                        else:
                            exact_prediction = int(query_logits(processor, query, exact_record.hidden_value).argmax().item())
                            unbounded_prediction = int(query_logits(processor, query, unbounded_record.hidden_value).argmax().item())
                            continuity_rows.append({"case_id": case["case_id"], "identity": exact_prediction == unbounded_prediction})
                    else:
                        raise ValueError(f"unsupported DMC-02A event: {event['kind']}")
                    for mode, controller in controllers.items():
                        peaks[mode] = max(peaks[mode], len(controller.ledger))
                        if len(controller.ledger) > CAPACITY:
                            violations[mode] += 1
                capacity_rows.append({"split": split, "family": case["family"], "condition": case["condition"], "case_id": case["case_id"], "peak": peaks, "violations": violations})

    after_hash = model_state_hash(processor)
    metrics = {}
    for mode, grouped in condition_hits.items():
        conditions = {f"{split}:{family}:{condition}": sum(hits) / len(hits) for (split, family, condition), hits in sorted(grouped.items())}
        def cond(family: str, condition: str) -> float:
            return conditions[f"extrapolation:{family}:{condition}"]
        components = {
            "M256": cond("mission_set", "load_256"),
            "M1024": cond("mission_set", "load_1024"),
            "SAL256": cond("salience", "load_256"),
            "SAL1024": cond("salience", "load_1024"),
            "SUP_current_1024": cond("supersession", "load_1024_current"),
            "SUP_history_1024": cond("supersession", "load_1024_history"),
            "SHIFT": statistics.mean(cond("utility_change", f"load_1024_overlap_{overlap}") for overlap in (0, 25, 50, 75, 100)),
            "FLOOD512": cond("distractor_flood", "distractors_512"),
            "FLOOD1024": cond("distractor_flood", "distractors_1024"),
        }
        components["P_bounded"] = statistics.mean(components.values())
        metrics[mode] = {"conditions": conditions, "components": components, "P_bounded": components["P_bounded"], "train_accuracy": statistics.mean(value for key, value in conditions.items() if key.startswith("train:")), "iid_accuracy": statistics.mean(value for key, value in conditions.items() if key.startswith("iid:")), "extrapolation_accuracy": statistics.mean(value for key, value in conditions.items() if key.startswith("extrapolation:"))}

    firewall_fields = sorted({tuple(row["fields"]) for row in exact_decisions})
    forbidden = {"answer", "answer_index", "final_query_target", "future_events", "oracle_result", "case_id", "future_query_choice"}
    observed_forbidden = sorted(forbidden.intersection({field for fields in firewall_fields for field in fields}))
    capacity_summary = {mode: {"maximum_peak": max(row["peak"][mode] for row in capacity_rows), "mean_peak": statistics.mean(row["peak"][mode] for row in capacity_rows), "violations": sum(row["violations"][mode] for row in capacity_rows)} for mode in controllers}
    return {"seed": seed, "checkpoint": str(checkpoint.relative_to(ROOT)), "checkpoint_sha256": sha256(checkpoint), "payload_model_type": payload.get("model_type"), "parameter_count": payload.get("parameter_count"), "memory_controller_parameters": 0, "model_state_hash_before": before_hash, "model_state_hash_after": after_hash, "model_immutable": before_hash == after_hash, "metrics": metrics, "capacity": capacity_summary, "hidden_vector_integrity": {"stored_records_checked": hidden_total, "mismatches": hidden_mismatches, "pass": hidden_mismatches == 0}, "metadata_firewall": {"decision_count": len(exact_decisions), "observed_field_sets": [list(fields) for fields in firewall_fields], "forbidden_fields_observed": observed_forbidden, "pass": not observed_forbidden and all(set(fields) == {"family", "entity", "field", "creation_episode", "salience", "supersedes"} for fields in firewall_fields)}, "continuity": {"cases_compared": len(continuity_rows), "identity_count": sum(row["identity"] for row in continuity_rows), "mismatches": sum(not row["identity"] for row in continuity_rows), "pass": all(row["identity"] for row in continuity_rows)}, "capacity_rows": capacity_rows}


def summarize(results: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    modes = ("exact", "fifo", "random")
    summary = {}
    for mode in modes:
        values = [result["metrics"][mode]["P_bounded"] for result in results[mode]]
        summary[mode] = {"mean": statistics.mean(values), "stdev": statistics.stdev(values), "per_seed": values}
    exact = summary["exact"]["mean"]
    fifo = summary["fifo"]["mean"]
    random = summary["random"]["mean"]
    component_means = {}
    for name in ("M256", "M1024", "SAL256", "SAL1024", "SUP_current_1024", "SUP_history_1024", "SHIFT", "FLOOD512", "FLOOD1024"):
        component_means[name] = {mode: statistics.mean(result["metrics"][mode]["components"][name] for result in results[mode]) for mode in modes}
    gates = {
        "A_primary": {"observed": exact, "threshold": 0.95, "pass": exact >= 0.95},
        "B_M1024": {"observed": component_means["M1024"]["exact"], "threshold": 0.95, "pass": component_means["M1024"]["exact"] >= 0.95},
        "C_SAL1024": {"observed": component_means["SAL1024"]["exact"], "threshold": 0.95, "pass": component_means["SAL1024"]["exact"] >= 0.95},
        "D_SUP_current_1024": {"observed": component_means["SUP_current_1024"]["exact"], "threshold": 0.95, "pass": component_means["SUP_current_1024"]["exact"] >= 0.95},
        "E_SUP_history_1024": {"observed": component_means["SUP_history_1024"]["exact"], "threshold": 0.95, "pass": component_means["SUP_history_1024"]["exact"] >= 0.95},
        "F_SHIFT": {"observed": component_means["SHIFT"]["exact"], "threshold": 0.95, "pass": component_means["SHIFT"]["exact"] >= 0.95},
        "G_FLOOD1024": {"observed": component_means["FLOOD1024"]["exact"], "threshold": 0.95, "pass": component_means["FLOOD1024"]["exact"] >= 0.95},
        "H_seed_consistency": {"observed": sum(value >= 0.90 for value in summary["exact"]["per_seed"]), "threshold": "5/5", "pass": all(value >= 0.90 for value in summary["exact"]["per_seed"])},
    }
    return {"per_mode": summary, "component_means": component_means, "differences": {"exact_minus_fifo": exact - fifo, "exact_minus_random": exact - random}, "control_separation": {"fifo": {"observed": exact - fifo, "threshold": 0.40, "pass": exact - fifo >= 0.40}, "random": {"observed": exact - random, "threshold": 0.40, "pass": exact - random >= 0.40}}, "gates": gates}


def identities() -> dict[str, Any]:
    entries = []
    specs = [("WORLD-0", WORLD0_COMMIT, ROOT / "artifacts/frozen/world0_v0_1"), ("DMC-00", DMC00_COMMIT, ROOT / "artifacts/dmc00"), ("DMC-01", DMC01_COMMIT, DMC01_DIR), ("DMC-02A", DMC02A_COMMIT, DMC02A_DIR), ("DMC-02P", DMC02P_COMMIT, ROOT / "artifacts/dmc02p")]
    for name, commit, path in specs:
        diff = subprocess.run(["git", "diff", "--exit-code", commit, "--", str(path.relative_to(ROOT))], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        manifest = verify_manifest(path)
        entries.append({"name": name, "expected_commit": commit, "path": str(path.relative_to(ROOT)), "unchanged": diff.returncode == 0, "manifest": manifest})
    world = subprocess.run([sys.executable, "scripts/validate_world0.py", "artifacts/frozen/world0_v0_1"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    terminal = world.stdout.strip().splitlines()[-1] if world.stdout.strip() else ""
    return {"pass": all(row["unchanged"] and row["manifest"]["pass"] for row in entries) and terminal == "GRI_02_WORLD0_PASS", "world0_validator": terminal, "predecessors": entries}


def run() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = read_dataset()
    identity = identities()
    if not identity["pass"]:
        write_json(ARTIFACT_DIR / "benchmark_identity.json", identity)
        write_json(ARTIFACT_DIR / "DMC02_VERDICT.json", {"terminal_state": "DMC_02_INVALID", "reason": "predecessor identity failure"})
        return 1
    all_results = {"exact": [], "fifo": [], "random": []}
    seed_results = {}
    capacity_rows = []
    firewall_rows = []
    hidden_rows = []
    continuity_rows = []
    for seed in EVIDENCE_SEEDS:
        result = evaluate_seed(seed, dataset)
        seed_results[seed] = result
        for mode in all_results:
            all_results[mode].append(result)
        capacity_rows.extend(result["capacity_rows"])
        firewall_rows.append({"seed": seed, **result["metadata_firewall"]})
        hidden_rows.append({"seed": seed, **result["hidden_vector_integrity"]})
        continuity_rows.append({"seed": seed, **result["continuity"]})
        for mode in ("exact", "fifo", "random"):
            payload = {key: value for key, value in result.items() if key not in {"capacity_rows"}}
            payload["mode"] = mode
            write_json(ARTIFACT_DIR / f"{mode}_seed{seed}.json", {"seed": seed, "mode": mode, "checkpoint": result["checkpoint"], "checkpoint_sha256": result["checkpoint_sha256"], "model_state_hash_before": result["model_state_hash_before"], "model_state_hash_after": result["model_state_hash_after"], "model_immutable": result["model_immutable"], "parameter_count": result["parameter_count"], "memory_controller_parameters": result["memory_controller_parameters"], "metrics": result["metrics"][mode], "capacity": result["capacity"][mode], "hidden_vector_integrity": result["hidden_vector_integrity"], "metadata_firewall": result["metadata_firewall"], "continuity": result["continuity"]})

    aggregate = summarize(all_results)
    integrity = {"model_immutable": all(result["model_immutable"] for result in seed_results.values()), "capacity_violations": sum(row["violations"][mode] for row in capacity_rows for mode in ("exact", "fifo", "random")), "hidden_vector_integrity": all(row["pass"] for row in hidden_rows), "metadata_firewall": all(row["pass"] for row in firewall_rows), "continuity": all(row["pass"] for row in continuity_rows)}
    mode_capacity = {mode: {"maximum_peak": max(row["peak"][mode] for row in capacity_rows), "mean_peak": statistics.mean(row["peak"][mode] for row in capacity_rows), "violations": sum(row["violations"][mode] for row in capacity_rows)} for mode in ("exact", "fifo", "random")}
    replay_first = evaluate_seed(1337, dataset)
    replay_second = evaluate_seed(1337, dataset)
    replay_payload_first = {"seed": 1337, "metrics": replay_first["metrics"], "capacity": replay_first["capacity"], "hidden": replay_first["hidden_vector_integrity"], "firewall": replay_first["metadata_firewall"], "continuity": replay_first["continuity"]}
    replay_payload_second = {"seed": 1337, "metrics": replay_second["metrics"], "capacity": replay_second["capacity"], "hidden": replay_second["hidden_vector_integrity"], "firewall": replay_second["metadata_firewall"], "continuity": replay_second["continuity"]}
    replay = {"seed": 1337, "complete_evaluation_repeated": True, "numeric_equal": replay_payload_first == replay_payload_second, "canonical_sha256_first": hashlib.sha256(json.dumps(replay_payload_first, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "canonical_sha256_second": hashlib.sha256(json.dumps(replay_payload_second, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
    checks = {"predecessors": identity["pass"], "model_immutable": integrity["model_immutable"], "capacity": integrity["capacity_violations"] == 0, "metadata_firewall": integrity["metadata_firewall"], "hidden_vector_integrity": integrity["hidden_vector_integrity"], "replay": replay["numeric_equal"], "checkpoint_hashes": all(row["checkpoint_sha256"] == json.loads((DMC01_DIR / "SHA256SUMS.json").read_text())[str(Path(row["checkpoint"]).relative_to(DMC01_DIR))] for row in seed_results.values())}
    gates_pass = all(gate["pass"] for gate in aggregate["gates"].values()) and all(gate["pass"] for gate in aggregate["control_separation"].values())
    if not checks["predecessors"] or not checks["model_immutable"] or not checks["replay"] or not checks["checkpoint_hashes"]:
        terminal = "DMC_02_INVALID"
    elif not checks["capacity"]:
        terminal = "DMC_02_CAPACITY_INVALID"
    elif not checks["metadata_firewall"]:
        terminal = "DMC_02_RETENTION_LEAK"
    elif gates_pass and all(checks.values()):
        terminal = "DMC_02_BOUNDED_EXACT_RETENTION_ADVANCES"
    elif all(checks.values()):
        terminal = "DMC_02_BOUNDED_EXACT_RETENTION_NO_ADVANTAGE"
    else:
        terminal = "DMC_02_REPAIR_REQUIRED"
    config = {"unit": "DMC-02", "source_commit": git_commit(), "dmc01_commit": DMC01_COMMIT, "dmc02a_commit": DMC02A_COMMIT, "dmc02p_commit": DMC02P_COMMIT, "world0_commit": WORLD0_COMMIT, "seeds": list(EVIDENCE_SEEDS), "modes": ["EXACT_RETENTION_16", "FIFO_16", "RANDOM_16"], "random_control_seed": RANDOM_CONTROL_SEED, "capacity": CAPACITY, "primary_metric": FUTURE_PRIMARY, "evaluation_only": True, "training": False, "optimizer": None, "backward_passes": 0}
    write_json(ARTIFACT_DIR / "DMC02_CONFIG.json", config)
    write_json(ARTIFACT_DIR / "checkpoint_manifest.json", {"dmc01_manifest": verify_manifest(DMC01_DIR), "rows": [{"seed": seed, "checkpoint": result["checkpoint"], "sha256": result["checkpoint_sha256"]} for seed, result in seed_results.items()]})
    write_json(ARTIFACT_DIR / "benchmark_identity.json", identity)
    write_json(ARTIFACT_DIR / "capacity_audit.json", {"capacity": CAPACITY, "cases": capacity_rows, "aggregate": mode_capacity, "violations": sum(row["violations"][mode] for row in capacity_rows for mode in ("exact", "fifo", "random")), "pass": checks["capacity"]})
    write_json(ARTIFACT_DIR / "metadata_firewall.json", {"per_seed": firewall_rows, "forbidden_inputs": ["answer", "answer_index", "final_query_target", "future_events", "oracle_result", "case_id", "future_query_choice"], "pass": checks["metadata_firewall"]})
    write_json(ARTIFACT_DIR / "hidden_vector_integrity.json", {"per_seed": hidden_rows, "pass": checks["hidden_vector_integrity"]})
    write_json(ARTIFACT_DIR / "continuity.json", {"per_seed": continuity_rows, "bounded_vs_unbounded_prediction_identity": all(row["pass"] for row in continuity_rows), "diagnostic_only": True})
    write_json(ARTIFACT_DIR / "replay.json", replay)
    write_json(ARTIFACT_DIR / "aggregate.json", aggregate)
    report = ["# DMC-02 — 16-Slot Bounded Exact-Retention Evidence", "", f"Terminal state: `{terminal}`", "", "| Seed | Exact P_bounded | FIFO P_bounded | Random P_bounded | Exact−FIFO | Exact−Random |", "|---:|---:|---:|---:|---:|---:|"]
    for seed in EVIDENCE_SEEDS:
        exact = seed_results[seed]["metrics"]["exact"]["P_bounded"]
        fifo = seed_results[seed]["metrics"]["fifo"]["P_bounded"]
        random = seed_results[seed]["metrics"]["random"]["P_bounded"]
        report.append(f"| {seed} | {exact:.8f} | {fifo:.8f} | {random:.8f} | {exact - fifo:.8f} | {exact - random:.8f} |")
    report.extend(["", "## Aggregate", "", f"- Exact mean/stdev: `{aggregate['per_mode']['exact']['mean']:.8f}` / `{aggregate['per_mode']['exact']['stdev']:.8f}`", f"- FIFO mean/stdev: `{aggregate['per_mode']['fifo']['mean']:.8f}` / `{aggregate['per_mode']['fifo']['stdev']:.8f}`", f"- Random mean/stdev: `{aggregate['per_mode']['random']['mean']:.8f}` / `{aggregate['per_mode']['random']['stdev']:.8f}`", "", "## Gates", ""])
    report.extend(f"- {name}: **{'PASS' if gate['pass'] else 'FAIL'}** (observed `{gate['observed']}`, threshold `{gate['threshold']}`)" for name, gate in aggregate["gates"].items())
    report.extend(f"- control {name}: **{'PASS' if gate['pass'] else 'FAIL'}** (observed `{gate['observed']}`, threshold `{gate['threshold']}`)" for name, gate in aggregate["control_separation"].items())
    write_json(ARTIFACT_DIR / "DMC02_VERDICT.json", {"unit": "DMC-02", "terminal_state": terminal, "checks": checks, "gates": aggregate["gates"], "control_separation": aggregate["control_separation"], "exact_minus_fifo": aggregate["differences"]["exact_minus_fifo"], "exact_minus_random": aggregate["differences"]["exact_minus_random"]})
    (ARTIFACT_DIR / "DMC02_REPORT.md").write_text("\n".join(report) + "\n")
    hashes = {}
    for path in sorted(ARTIFACT_DIR.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.json":
            hashes[str(path.relative_to(ARTIFACT_DIR))] = sha256(path)
    write_json(ARTIFACT_DIR / "SHA256SUMS.json", hashes)
    print(terminal)
    return 0 if terminal in {"DMC_02_BOUNDED_EXACT_RETENTION_ADVANCES", "DMC_02_BOUNDED_EXACT_RETENTION_NO_ADVANTAGE"} else 1


if __name__ == "__main__":
    raise SystemExit(run())
