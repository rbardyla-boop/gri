from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from experiments.forge.ecology import Ablator, Ledger, NullSmith, classify_failure
from experiments.forge.forge import Case, Chain, Forge, Grinder, Mutation, Registry, SearchConfig, canonical_json
from experiments.forge.te0_io import file_sha256
from experiments.forge_e2.interface_tools import GateAwareInterfaceToolSmith


def load_cases(path: Path) -> tuple[Case, ...]:
    out: list[Case] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cid = str(row["case_id"])
        if cid in seen:
            raise ValueError(f"duplicate case: {cid}")
        seen.add(cid)
        out.append(Case(cid, row["input"], row["expected"]))
    if not out:
        raise ValueError("empty case file")
    return tuple(out)


def is_contract_object(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"label", "evidence"}
        and isinstance(value.get("label"), str)
        and isinstance(value.get("evidence"), list)
        and all(isinstance(x, str) for x in value["evidence"])
    )


def raw_metrics(cases: tuple[Case, ...]) -> dict[str, float | int]:
    exact = structural = 0
    for case in cases:
        try:
            value = json.loads(case.input)
        except Exception:
            continue
        structural += int(is_contract_object(value))
        exact += int(value == case.expected)
    n = len(cases)
    return {
        "n": n,
        "exact": exact,
        "exact_rate": exact / n if n else 0.0,
        "structural_valid": structural,
        "structural_validity_rate": structural / n if n else 0.0,
        "already_valid": exact,
    }


def preservation_rate(forge: Forge, chain: Chain, cases: tuple[Case, ...]) -> float:
    valid: list[Case] = []
    for case in cases:
        try:
            value = json.loads(case.input)
        except Exception:
            continue
        if value == case.expected:
            valid.append(case)
    if not valid:
        return 1.0
    kept = 0
    for case in valid:
        try:
            kept += int(forge.run_chain(chain, case.input) == case.expected)
        except Exception:
            pass
    return kept / len(valid)


def structural_rate(forge: Forge, chain: Chain, cases: tuple[Case, ...]) -> float:
    valid = 0
    for case in cases:
        try:
            valid += int(is_contract_object(forge.run_chain(chain, case.input)))
        except Exception:
            pass
    return valid / len(cases) if cases else 0.0


def mutation_canonical(case: Case) -> Iterable[Case]:
    yield Case(case.case_id + "-canonical", json.dumps(case.expected, separators=(",", ":")), case.expected)


def mutation_wrapper(case: Case) -> Iterable[Case]:
    payload = json.dumps(case.expected, separators=(",", ":"))
    yield Case(case.case_id + "-wrapped", f"Result follows: {payload} End.", case.expected)


def mutation_case_duplicates(case: Case) -> Iterable[Case]:
    label = case.expected.get("label") if isinstance(case.expected, dict) else None
    evidence = case.expected.get("evidence") if isinstance(case.expected, dict) else None
    if not isinstance(label, str) or not isinstance(evidence, list):
        return
    noisy = list(reversed(evidence))
    if evidence:
        noisy.append(evidence[0])
    yield Case(
        case.case_id + "-case-dupes",
        json.dumps({"label": f" {label.lower()} ", "evidence": noisy}),
        case.expected,
    )


def mutation_nested_schema(case: Case) -> Iterable[Case]:
    label = case.expected.get("label") if isinstance(case.expected, dict) else None
    evidence = case.expected.get("evidence") if isinstance(case.expected, dict) else None
    if not isinstance(label, str) or not isinstance(evidence, list):
        return
    multiset = list(reversed(evidence))
    if evidence:
        multiset.append(evidence[0])
    payload = {label: {"evidenceMultiset": multiset, "evidenceArray": list(evidence)}}
    yield Case(case.case_id + "-nested", json.dumps(payload), case.expected)


def registered_mutations() -> tuple[Mutation, ...]:
    return (
        Mutation("canonical_preservation", mutation_canonical),
        Mutation("prose_wrapper", mutation_wrapper),
        Mutation("case_and_duplicate_normalization", mutation_case_duplicates),
        Mutation("nested_label_schema", mutation_nested_schema),
    )


def attack_cases(cases: tuple[Case, ...]) -> tuple[Case, ...]:
    out: list[Case] = []
    for mutation in registered_mutations():
        for case in cases:
            out.extend(mutation.fn(case))
    return tuple(out)


def candidate_metrics(
    forge: Forge,
    chain: Chain,
    dev: tuple[Case, ...],
    attacks: tuple[Case, ...],
    *,
    raw_exact: float,
    best_null: float,
) -> dict[str, Any]:
    dev_score = forge.score_chain(chain, dev).score
    structural = structural_rate(forge, chain, dev)
    preservation = preservation_rate(forge, chain, dev)
    attack = forge.score_chain(chain, attacks).score if attacks else 0.0
    improvement = dev_score - raw_exact
    null_margin = dev_score - best_null
    gates = {
        "dev_exact": dev_score >= 0.95,
        "structural_validity": structural >= 0.98,
        "raw_improvement": improvement >= 0.10 or raw_exact >= 0.98,
        "null_margin": null_margin >= 0.20,
        "preserve_already_valid": preservation == 1.0,
        "attack_set_exact": attack == 1.0,
    }
    return {
        "chain": chain,
        "dev_exact_rate": dev_score,
        "structural_validity_rate": structural,
        "preservation_rate": preservation,
        "attack_set_exact_rate": attack,
        "improvement_over_raw": improvement,
        "margin_over_null": null_margin,
        "pre_gates": gates,
        "pre_gate_count": sum(int(v) for v in gates.values()),
        "robust_floor": min(dev_score, structural, preservation, attack),
    }


def rank_key(m: dict[str, Any]) -> tuple[Any, ...]:
    c: Chain = m["chain"]
    return (
        -m["pre_gate_count"],
        -m["robust_floor"],
        -m["dev_exact_rate"],
        -m["attack_set_exact_rate"],
        -m["structural_validity_rate"],
        -m["preservation_rate"],
        -m["improvement_over_raw"],
        -m["margin_over_null"],
        len(c.tools),
        c.cost,
        c.tools,
    )


def ablation_summary(forge: Forge, chain: Chain, attacks: tuple[Case, ...]) -> tuple[list[dict[str, Any]], list[str]]:
    full = forge.score_chain(chain, attacks).score if attacks else 0.0
    rows = Ablator(forge).single_tool_ablations(chain, attacks, full)
    serialized: list[dict[str, Any]] = []
    unnecessary: list[str] = []
    for a in rows:
        serialized.append({
            "removed_tool": a.removed_tool,
            "valid": a.valid,
            "score": a.score,
            "delta_from_full": a.delta_from_full,
            "reason": a.reason,
        })
        if a.valid and a.delta_from_full is not None and a.delta_from_full <= 0.0:
            unnecessary.append(a.removed_tool)
    return serialized, unnecessary


def serialize_metrics(m: dict[str, Any]) -> dict[str, Any]:
    chain: Chain = m["chain"]
    return {
        "chain_id": chain.chain_id,
        "tools": list(chain.tools),
        "cost": chain.cost,
        "dev_exact_rate": m["dev_exact_rate"],
        "structural_validity_rate": m["structural_validity_rate"],
        "preservation_rate": m["preservation_rate"],
        "attack_set_exact_rate": m["attack_set_exact_rate"],
        "improvement_over_raw": m["improvement_over_raw"],
        "margin_over_null": m["margin_over_null"],
        "pre_gate_count": m["pre_gate_count"],
        "robust_floor": m["robust_floor"],
        "pre_gates": m["pre_gates"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="TE0-E2 gate-aware BUILD/DEV discovery. No Vault argument exists by design.")
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--dev", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--ledger", type=Path)
    args = ap.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)

    build = load_cases(args.build)
    dev = load_cases(args.dev)
    raw = raw_metrics(dev)
    if float(raw["exact_rate"]) >= 0.98:
        report = {
            "schema_version": 1,
            "unit": "TE0-E2",
            "status": "TE0_E2_REPAIR_NOT_NEEDED",
            "authority": False,
            "vault_seen": False,
            "bindings": {"build_sha256": file_sha256(args.build), "dev_sha256": file_sha256(args.dev)},
            "raw_dev": raw,
            "reason": "raw producer exact-target rate already >= 0.98",
        }
    else:
        diagnosis = classify_failure({"parse_failure": True})
        smith = GateAwareInterfaceToolSmith()
        blueprints = smith.propose(diagnosis, build, "text", "json")
        registry = Registry()
        smith.register(registry, blueprints)
        forge = Forge(registry)
        config = SearchConfig("text", "json", max_depth=5, max_cost=5, max_candidates=50000)
        chains = forge.toolsmith.enumerate(config)
        nulls = list(NullSmith.constant_null(dev)) + [NullSmith.identity_null(dev)]
        best_null = max((n.score for n in nulls), default=0.0)
        attacks = attack_cases(dev)
        metrics = [
            candidate_metrics(forge, chain, dev, attacks, raw_exact=float(raw["exact_rate"]), best_null=best_null)
            for chain in chains
        ]
        ranked = sorted(metrics, key=rank_key)
        if not ranked:
            report = {
                "schema_version": 1,
                "unit": "TE0-E2",
                "status": "TE0_E2_INTERFACE_REPAIR_FAIL",
                "authority": False,
                "vault_seen": False,
                "reason": "no typed repair candidate",
                "raw_dev": raw,
            }
        else:
            # Only candidates that already pass every non-ablation gate can freeze.
            prepass = [m for m in ranked if all(m["pre_gates"].values())]
            chosen = ranked[0]
            chosen_ablations: list[dict[str, Any]] = []
            chosen_unnecessary: list[str] = []
            if prepass:
                credited: list[tuple[dict[str, Any], list[dict[str, Any]], list[str]]] = []
                for m in prepass:
                    ablations, unnecessary = ablation_summary(forge, m["chain"], attacks)
                    credited.append((m, ablations, unnecessary))
                credit_ok = [row for row in credited if not row[2]]
                if credit_ok:
                    chosen, chosen_ablations, chosen_unnecessary = sorted(credit_ok, key=lambda row: rank_key(row[0]))[0]
                else:
                    chosen, chosen_ablations, chosen_unnecessary = sorted(credited, key=lambda row: rank_key(row[0]))[0]
            else:
                chosen_ablations, chosen_unnecessary = ablation_summary(forge, chosen["chain"], attacks)

            grinder = Grinder(forge, registered_mutations()).grind(chosen["chain"], dev, max_failures=100)
            all_gates = {
                **chosen["pre_gates"],
                "grinder_zero_failures": len(grinder) == 0,
                "all_components_earn_credit": not chosen_unnecessary,
            }
            status = "TE0_E2_DEVELOPMENT_CHAMPION_FROZEN" if all(all_gates.values()) else "TE0_E2_INTERFACE_REPAIR_FAIL"
            report = {
                "schema_version": 1,
                "unit": "TE0-E2",
                "status": status,
                "authority": False,
                "vault_seen": False,
                "bindings": {"build_sha256": file_sha256(args.build), "dev_sha256": file_sha256(args.dev)},
                "raw_dev": raw,
                "candidate_count": len(ranked),
                "selection_rule": "gate_count_then_robust_floor_then_exact_attack_structural_preservation_improvement_null_simplicity",
                "champion": serialize_metrics(chosen),
                "gates": all_gates,
                "grinder_failure_count": len(grinder),
                "grinder_failures": [
                    {
                        "mutation": f.mutation,
                        "source_case": f.source_case,
                        "mutated_case": f.mutated_case,
                        "observed": f.observed,
                        "expected": f.expected,
                    }
                    for f in grinder[:20]
                ],
                "ablations": chosen_ablations,
                "unnecessary_tools": chosen_unnecessary,
                "top_candidates": [serialize_metrics(m) for m in ranked[:10]],
                "tool_blueprints": [
                    {
                        "name": bp.name,
                        "op": bp.op,
                        "input_kind": bp.input_kind,
                        "output_kind": bp.output_kind,
                        "cost": bp.cost,
                        "params": bp.params,
                        "source_failure": bp.source_failure.value,
                        "blueprint_id": bp.blueprint_id,
                    }
                    for bp in blueprints
                ],
                "registered_mutations": [m.name for m in registered_mutations()],
            }

    report["record_sha256"] = hashlib.sha256(canonical_json(report).encode()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.ledger:
        Ledger(args.ledger).append({
            "experiment": "TE0-E2-DEV",
            "status": report["status"],
            "manifest_sha256": file_sha256(args.output),
            "authority": False,
        })
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
