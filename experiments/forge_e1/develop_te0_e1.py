from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.forge.controller import DiscoveryPolicy, DiscoveryStatus
from experiments.forge.ecology import Ablator, Composer, Ledger, NullSmith, classify_failure
from experiments.forge.forge import Case, Forge, Registry, SearchConfig, canonical_json
from experiments.forge.te0_io import file_sha256
from experiments.forge_e1.interface_tools import InterfaceRepairToolSmith


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


def raw_metrics(cases: tuple[Case, ...]) -> dict[str, float | int]:
    exact = 0
    structural = 0
    canonically_valid = 0
    for case in cases:
        raw = case.input
        try:
            value = json.loads(raw)
            is_object = isinstance(value, dict)
        except Exception:
            value = None
            is_object = False
        structural += int(is_object)
        if is_object:
            try:
                if canonical_json(value) == canonical_json(case.expected):
                    exact += 1
                # Valid here means it is already an exact canonical answer; a
                # repair is required to leave those answers unchanged.
                if value == case.expected:
                    canonically_valid += 1
            except Exception:
                pass
    n = len(cases)
    return {
        "n": n,
        "exact": exact,
        "exact_rate": exact / n if n else 0.0,
        "structural_valid": structural,
        "structural_validity_rate": structural / n if n else 0.0,
        "already_valid": canonically_valid,
    }


def preservation_rate(forge: Forge, chain, cases: tuple[Case, ...]) -> float:
    valid = []
    for case in cases:
        try:
            value = json.loads(case.input)
        except Exception:
            continue
        if value == case.expected:
            valid.append(case)
    if not valid:
        return 1.0
    preserved = 0
    for case in valid:
        try:
            observed = forge.run_chain(chain, case.input)
            preserved += int(observed == case.expected)
        except Exception:
            pass
    return preserved / len(valid)


def chain_structural_rate(forge: Forge, chain, cases: tuple[Case, ...]) -> float:
    valid = 0
    for case in cases:
        try:
            observed = forge.run_chain(chain, case.input)
            valid += int(isinstance(observed, dict) and set(observed) == {"label", "evidence"})
        except Exception:
            pass
    return valid / len(cases) if cases else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description="TE0-E1 BUILD/DEV repair discovery. No Vault argument exists by design.")
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
        status = "TE0_E1_REPAIR_NOT_NEEDED"
        report = {
            "schema_version": 1,
            "unit": "TE0-E1",
            "status": status,
            "authority": False,
            "vault_seen": False,
            "bindings": {"build_sha256": file_sha256(args.build), "dev_sha256": file_sha256(args.dev)},
            "raw_dev": raw,
            "reason": "raw producer exact-target rate already >= 0.98",
        }
        report["record_sha256"] = hashlib.sha256(canonical_json(report).encode()).hexdigest()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    diagnosis = classify_failure({"parse_failure": True})
    smith = InterfaceRepairToolSmith()
    blueprints = smith.propose(diagnosis, build, "text", "json")
    registry = Registry()
    smith.register(registry, blueprints)
    forge = Forge(registry)
    policy = DiscoveryPolicy(
        dev_threshold=0.95,
        min_margin_over_null=0.20,
        max_grinder_failures=0,
        min_component_delta=0.0,
        max_depth=5,
        max_cost=5,
        max_candidates=50000,
        complexity_penalty=0.005,
        cost_penalty=0.002,
    )
    ranked = Composer(forge).search(
        dev,
        SearchConfig("text", "json", max_depth=policy.max_depth, max_cost=policy.max_cost, max_candidates=policy.max_candidates),
        complexity_penalty=policy.complexity_penalty,
        cost_penalty=policy.cost_penalty,
    )
    if not ranked:
        status = "TE0_E1_INTERFACE_REPAIR_FAIL"
        champion = None
        reason = "no valid repair recipe"
        best_null = max((n.score for n in list(NullSmith.constant_null(dev)) + [NullSmith.identity_null(dev)]), default=0.0)
        report = {
            "schema_version": 1,
            "unit": "TE0-E1",
            "status": status,
            "authority": False,
            "vault_seen": False,
            "bindings": {"build_sha256": file_sha256(args.build), "dev_sha256": file_sha256(args.dev)},
            "raw_dev": raw,
            "best_null_score": best_null,
            "reason": reason,
        }
    else:
        champion = ranked[0]
        nulls = list(NullSmith.constant_null(dev)) + [NullSmith.identity_null(dev)]
        best_null = max((n.score for n in nulls), default=0.0)
        structural_rate = chain_structural_rate(forge, champion.chain, dev)
        preservation = preservation_rate(forge, champion.chain, dev)
        improvement = champion.dev_score - float(raw["exact_rate"])
        null_margin = champion.dev_score - best_null
        ablations = Ablator(forge).single_tool_ablations(champion.chain, dev, champion.dev_score)
        unnecessary = [a.removed_tool for a in ablations if a.valid and a.delta_from_full is not None and a.delta_from_full <= 0.0]
        gates = {
            "dev_exact": champion.dev_score >= 0.95,
            "structural_validity": structural_rate >= 0.98,
            "raw_improvement": improvement >= 0.10,
            "null_margin": null_margin >= 0.20,
            "preserve_already_valid": preservation == 1.0,
            "all_components_earn_credit": not unnecessary,
        }
        status = "TE0_E1_DEVELOPMENT_CHAMPION_FROZEN" if all(gates.values()) else "TE0_E1_INTERFACE_REPAIR_FAIL"
        report = {
            "schema_version": 1,
            "unit": "TE0-E1",
            "status": status,
            "authority": False,
            "vault_seen": False,
            "bindings": {"build_sha256": file_sha256(args.build), "dev_sha256": file_sha256(args.dev)},
            "raw_dev": raw,
            "repair_dev": {
                "exact_rate": champion.dev_score,
                "structural_validity_rate": structural_rate,
                "improvement_over_raw": improvement,
                "best_null_score": best_null,
                "margin_over_null": null_margin,
                "preservation_rate": preservation,
            },
            "gates": gates,
            "champion": {
                "chain_id": champion.chain.chain_id,
                "tools": list(champion.chain.tools),
                "input_kind": champion.chain.input_kind,
                "output_kind": champion.chain.output_kind,
                "cost": champion.chain.cost,
            },
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
            "ablations": [
                {
                    "removed_tool": a.removed_tool,
                    "valid": a.valid,
                    "score": a.score,
                    "delta_from_full": a.delta_from_full,
                    "reason": a.reason,
                }
                for a in ablations
            ],
            "unnecessary_tools": unnecessary,
        }

    report["record_sha256"] = hashlib.sha256(canonical_json(report).encode()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.ledger:
        Ledger(args.ledger).append({
            "experiment": "TE0-E1-DEV",
            "status": report["status"],
            "manifest_sha256": file_sha256(args.output),
            "authority": False,
        })
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
