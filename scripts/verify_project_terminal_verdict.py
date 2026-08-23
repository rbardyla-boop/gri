#!/usr/bin/env python3
"""Verify the project terminal verdict against canonical experiment artifacts."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def main() -> int:
    project = load("artifacts/PROJECT_TERMINAL_VERDICT.json")
    dmc04b = load("artifacts/dmc04b/DMC04B_VERDICT.json")
    dmc05a = load("artifacts/dmc05a/DMC05A_VERDICT.json")
    dmc05r = load("artifacts/dmc05r/DMC05R_VERDICT.json")
    mco01 = load("artifacts/mco01/MCO01_VERDICT.json")
    mco02 = load("artifacts/mco02/MCO02_VERDICT.json")
    mco03 = load("artifacts/mco03/MCO03_VERDICT.json")
    mco04 = load("artifacts/mco04/scientific/MCO04_VERDICT.json")
    mco05 = load("artifacts/mco05/scientific/MCO05_VERDICT.json")

    expected_results = {
        "DMC-04B": dmc04b["terminal_state"],
        "DMC-05A": dmc05a["terminal_state"],
        "DMC-05R": dmc05r["terminal_state"],
        "MCO-01": mco01["verdict"],
        "MCO-02": mco02["verdict"],
        "MCO-03": mco03["verdict"],
        "MCO-04": mco04["verdict"],
        "MCO-05": mco05["verdict"],
    }
    observed_results = {
        row["experiment"]: row["result"] for row in project["gates"]
    }
    project_metrics = project["mco05_decisive_metrics"]
    mco05_gates = mco05["gates"]
    mco05_reasoning = mco05["reasoning_metrics"]

    checks = {
        "answer_is_bounded": project["answer"]
        == "NO_CURRENT_EVIDENCE_OF_WORLD_CHANGE",
        "dmc_training_label": project["training_accounting"][
            "dmc_historical_training_cost"
        ]
        == dmc05r["training_cost_status"]
        == "TRAINING_COST_UNKNOWN",
        "dmc_training_steps": project["training_accounting"][
            "dmc_historical_optimizer_steps_reconstructed"
        ]
        == dmc05r["training_optimizer_steps_reconstructed"]
        == 10880,
        "gate_population": set(observed_results) == set(expected_results),
        "gate_results": observed_results == expected_results,
        "mco04_integrity": mco04["overall_verification"] == "PASS",
        "mco04_narrow_advance": mco04["gates"]["compiler_top1"] == 1.0
        and mco04["packet_fault_exact"] == 0.0,
        "mco05_candidate_recall": project_metrics["candidate_recall"]["correct"]
        == mco05_gates["candidate_recall_count"]
        and project_metrics["candidate_recall"]["n"]
        == mco05_gates["candidate_recall_n"]
        and project_metrics["candidate_recall"]["rate"]
        == mco05_gates["candidate_recall"],
        "mco05_control_accuracy": project_metrics["hybrid_rag_accuracy"]
        == mco05_reasoning["hybrid_rag_16"]["accuracy"]
        and project_metrics["maximum_context_accuracy"]
        == mco05_reasoning["max_context"]["accuracy"],
        "mco05_integrity": mco05["overall_integrity"] == "PASS"
        and mco05["verification"]["pass"],
        "mco05_packet_accuracy": project_metrics["packet_accuracy"]
        == mco05_gates["packet_accuracy"],
        "mco05_packet_strata": project_metrics["packet_adversarial_accuracy"]
        == mco05_gates["packet_adversarial_accuracy"]
        and project_metrics["packet_no_code_accuracy"]
        == mco05_gates["packet_no_code_accuracy"],
        "mco05_stability": project_metrics["semantic_stability"]
        == mco05["stability_semantic_agreement"],
        "mco05_terminal_failure": mco05["claim_verification"] == "FAIL"
        and not mco05_gates["bounded_inference_advance"],
        "mco05_wilson_interval": project_metrics["packet_wilson95"]
        == mco05_gates["packet_wilson95"],
        "stop_decision": project["stop_decision"]
        == "STOP_TESTED_ARCHITECTURE_BRANCH",
        "world_impact": project["world_impact"]
        == mco05["world_impact_disposition"]
        == "NOT_ESTABLISHED",
    }
    failures = sorted(name for name, passed in checks.items() if not passed)
    result = {"checks": checks, "failures": failures, "pass": not failures}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
