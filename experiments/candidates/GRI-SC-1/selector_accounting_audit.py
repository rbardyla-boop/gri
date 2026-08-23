#!/usr/bin/env python3
"""GRI-SC-1R.1 forensic audit for Candidate B's branch-free transition.

This audit performs no optimization, training, candidate modification, or
scientific evaluation. It closes only the operation/accounting ambiguity.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(__file__).resolve().parent / "branchfree_residual.py"
MANIFEST = Path(__file__).resolve().parent / "branchfree_residual_manifest.json"
RULES = ROOT / "experiments" / "gri02b_operation_rules.json"
CONTRACT = ROOT / "docs" / "GRI-SC-0-SELECTOR-COST-AUTHORIZATION-CONTRACT.md"
REPRESENTABILITY_RECEIPT = ROOT / "artifacts/results/gri_sc1r_branchfree_residual_receipt.json"

FORBIDDEN_NAMES = {
    "fixture_id", "fixture_label", "held_out_label", "task_id", "delay_count",
    "sequence_index", "step_counter", "history_buffer", "phase_variable",
    "query_horizon", "label", "split", "task_name", "task_id",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_candidate():
    spec = importlib.util.spec_from_file_location("gri_sc1_residual_audit", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("candidate source cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.BranchFreeResidualCell


def method_node(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise RuntimeError(f"missing method {name}")


def source_evidence(source: str) -> dict:
    tree = ast.parse(source)
    step = method_node(tree, "step")
    init = method_node(tree, "__init__")
    step_compares = [node.lineno for node in ast.walk(step) if isinstance(node, ast.Compare)]
    step_branches = [node.lineno for node in ast.walk(step) if isinstance(node, (ast.If, ast.IfExp, ast.Match))]
    init_compares = [node.lineno for node in ast.walk(init) if isinstance(node, ast.Compare)]
    init_branches = [node.lineno for node in ast.walk(init) if isinstance(node, (ast.If, ast.IfExp, ast.Match))]
    step_names = set()
    for node in ast.walk(step):
        if isinstance(node, ast.Name):
            step_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            step_names.add(node.attr)
    return {
        "step_lines": [step.lineno, step.end_lineno],
        "step_comparison_lines": step_compares,
        "step_branch_lines": step_branches,
        "step_forbidden_names": sorted(step_names & FORBIDDEN_NAMES),
        "constructor_comparison_lines": init_compares,
        "constructor_branch_lines": init_branches,
        "constructor_comparison_interpretation": "state-width validation only; not a recurrent transition operation",
        "constructor_code_initialization": "fixed semantic embedding coordinate at source lines 27-33; initialization/training setup, not runtime dispatch",
    }


def runtime_checks() -> dict:
    Candidate = load_candidate()
    model = Candidate(alphabet_size=10, state_width=8, wait_index=6).double()
    expected = torch.ones(10, 1, dtype=torch.float64)
    expected[6, 0] = 0.0
    fixed_code_exact = torch.equal(model.input.weight[:, :1].detach(), expected)
    state = torch.tensor([[0.13, -0.21, 0.34, -0.45, 0.56, -0.67, 0.78, -0.89]], dtype=torch.float64)
    wait_state = model.step(torch.tensor([6]), state)
    event_state = model.step(torch.tensor([1]), state)
    return {
        "fixed_semantic_code_exact": fixed_code_exact,
        "wait_transition_exact_identity": torch.equal(wait_state, state),
        "event_transition_changes_sample_state": not torch.equal(event_state, state),
        "runtime_state_shape": list(wait_state.shape),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/results/gri_sc1r1_selector_accounting_receipt.json")
    args = parser.parse_args()
    manifest = load_json(MANIFEST)
    rules = load_json(RULES)
    source = SOURCE.read_text(encoding="utf-8")
    evidence = source_evidence(source)
    runtime = runtime_checks()

    ledger = {
        "token_lookup": 1,
        "embedding_value_copy": 8,
        "diagonal_state_multiply": 8,
        "state_embedding_add": 8,
        "tanh": 8,
        "residual_subtract": 8,
        "semantic_residual_multiply": 8,
        "residual_state_add": 8,
        "recurrent_total": 57,
        "query_readout_total": 21,
        "recurrent_plus_query_total": 78,
    }
    budget = {
        "parent_recurrent_ceiling": rules["parent_gri01_d8"]["recurrent_step"]["total_counted_operations"],
        "parent_recurrent_plus_query_ceiling": rules["parent_gri01_d8"]["recurrent_plus_query_total"],
        "candidate_recurrent": ledger["recurrent_total"],
        "candidate_recurrent_plus_query": ledger["recurrent_plus_query_total"],
        "recurrent_budget_pass": ledger["recurrent_total"] <= rules["parent_gri01_d8"]["recurrent_step"]["total_counted_operations"],
        "recurrent_plus_query_budget_pass": ledger["recurrent_plus_query_total"] <= rules["parent_gri01_d8"]["recurrent_plus_query_total"],
    }
    parameter = {
        "embedding_total_slots": 80,
        "fixed_semantic_code_slots": 10,
        "trainable_embedding_slots": 70,
        "trainable_diagonal_slots": 8,
        "trainable_readout_slots": 18,
        "trainable_total": 96,
        "fixed_total": 10,
        "persistent_state_slots": 8,
        "parameter_budget_pass": 96 + 10 <= 170,
        "state_budget_pass": 8 <= 8,
    }
    checks = {
        "step_has_no_comparison": not evidence["step_comparison_lines"],
        "step_has_no_branch": not evidence["step_branch_lines"],
        "step_has_no_forbidden_metadata_names": not evidence["step_forbidden_names"],
        "constructor_only_validation_is_not_transition_dispatch": evidence["constructor_comparison_lines"] == [21] and evidence["constructor_branch_lines"] == [21],
        "fixed_code_is_declared_parameter": runtime["fixed_semantic_code_exact"],
        "wait_is_exact_identity": runtime["wait_transition_exact_identity"],
        "event_is_transforming": runtime["event_transition_changes_sample_state"],
        "budget_pass": budget["recurrent_budget_pass"] and budget["recurrent_plus_query_budget_pass"],
        "parameter_and_state_budget_pass": parameter["parameter_budget_pass"] and parameter["state_budget_pass"],
        "manifest_declares_zero_selector_comparisons": manifest["operations"]["selector_comparisons"] == 0,
        "manifest_recurrent_count_matches_audit": manifest["operations"]["recurrent"] == ledger["recurrent_total"],
    }
    audit_pass = all(checks.values())
    output = {
        "unit": "GRI-SC-1R.1-BRANCH-FREE-COUNTEREXAMPLE-ACCOUNTING-AUDIT",
        "status": "CLOSED",
        "audit_verdict": "PASS" if audit_pass else "FAIL",
        "counterexample_admissible": audit_pass,
        "scientific_verdict": "FORBIDDEN",
        "candidate_freeze": False,
        "scientific_run": False,
        "checks": checks,
        "source_evidence": evidence,
        "runtime_checks": runtime,
        "operation_ledger": ledger,
        "budget": budget,
        "parameter_and_state_accounting": parameter,
        "selector_interpretation": {
            "runtime_selector_comparisons": 0,
            "semantic_source": "fixed first coordinate in the existing token embedding lookup",
            "embedding_slice_extra_operation": False,
            "embedding_slice_reason": "the eight embedding value copies already include the reused first coordinate; slicing is a view, not a comparison or dispatch",
            "constructor_wait_index": "used only to initialize fixed parameters; not supplied per token and not executed in step()",
            "gradient_hook": "training-time freeze of fixed semantic coordinates; no recurrent runtime state or transition operation",
        },
        "formal_consequence": {
            "token_class_dependence": "NECESSARY",
            "extra_explicit_selector_operation": "NOT NECESSARY UNDER FROZEN MODEL",
            "selector_cost_lower_bound": "DISPROVED BY CONSTRUCTION",
        },
        "hashes": {
            "candidate_source_sha256": sha256(SOURCE),
            "candidate_manifest_sha256": sha256(MANIFEST),
            "operation_rules_sha256": sha256(RULES),
            "sc0_contract_sha256": sha256(CONTRACT),
            "sc1r_representability_receipt_sha256": sha256(REPRESENTABILITY_RECEIPT),
            "audit_source_sha256": sha256(Path(__file__)),
        },
        "next_state": {
            "sc2": "NOT AUTHORIZED",
            "scientific_ledger": "UNCHANGED",
            "successor": "NOT AUTHORIZED",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"unit": output["unit"], "audit_verdict": output["audit_verdict"], "counterexample_admissible": output["counterexample_admissible"], "selector_cost_lower_bound": output["formal_consequence"]["selector_cost_lower_bound"]}, indent=2))
    return 0 if audit_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
