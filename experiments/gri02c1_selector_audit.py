#!/usr/bin/env python3
"""Forensic accounting audit for the GRI-02C transition selector.

This unit does not train, evaluate, or modify GRI-02C.  It checks whether the
frozen candidate source actually receives an external transition class or
computes the WAIT classification itself, then applies the frozen GRI-02B
operation ceilings without changing them.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
RESULTS = ROOT / "artifacts" / "results"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def is_wait_selector(node: ast.AST) -> bool:
    """Match the executable scalar-level selector ids == self.wait_index."""
    if not isinstance(node, ast.Compare):
        return False
    if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq):
        return False
    if len(node.comparators) != 1:
        return False
    left = node.left
    right = node.comparators[0]
    return (
        isinstance(left, ast.Name)
        and left.id == "ids"
        and isinstance(right, ast.Attribute)
        and isinstance(right.value, ast.Name)
        and right.value.id == "self"
        and right.attr == "wait_index"
    )


def descendant_ids(nodes: list[ast.AST]) -> set[int]:
    result: set[int] = set()
    for node in nodes:
        result.update(id(child) for child in ast.walk(node))
    return result


def branch_context(node: ast.AST, parents: dict[int, ast.AST]) -> list[str]:
    context: list[str] = []
    current = node
    while id(current) in parents:
        parent = parents[id(current)]
        if isinstance(parent, ast.If):
            body_ids = descendant_ids(parent.body)
            else_ids = descendant_ids(parent.orelse)
            side = "body" if id(node) in body_ids else "orelse" if id(node) in else_ids else "nested"
            context.append(f"{side}: {ast.unparse(parent.test)}")
        current = parent
    return list(reversed(context))


def selector_occurrences(source_path: Path) -> dict:
    source = source_path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source, filename=str(source_path))
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent

    occurrences = []
    for node in ast.walk(tree):
        if is_wait_selector(node):
            context = branch_context(node, parents)
            occurrences.append(
                {
                    "line": node.lineno,
                    "column": node.col_offset,
                    "source": lines[node.lineno - 1].strip(),
                    "branch_context": context,
                    "candidate_branch": any(item in ("body: behavior == 'candidate'", "body: behavior == \"candidate\"") for item in context),
                    "no_recurrence_branch": any(item in ("body: behavior == 'no_recurrence'", "body: behavior == \"no_recurrence\"") for item in context),
                }
            )

    forward = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "forward"
    )
    forward_args = [arg.arg for arg in forward.args.args]
    return {
        "occurrences": sorted(occurrences, key=lambda item: (item["line"], item["column"])),
        "forward_arguments": forward_args,
        "external_transition_class_argument": "transition_class" in forward_args,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=EXPERIMENTS / "gri02c_config.json")
    parser.add_argument("--receipt", type=Path, default=RESULTS / "gri02c_identity_preserve_receipt.json")
    parser.add_argument("--implementation", type=Path, default=EXPERIMENTS / "gri02c_identity_preserve.py")
    parser.add_argument("--operation-rules", type=Path, default=EXPERIMENTS / "gri02b_operation_rules.json")
    parser.add_argument("--output", type=Path, default=RESULTS / "gri02c1_selector_audit_receipt.json")
    args = parser.parse_args()

    config = load_json(args.config)
    receipt = load_json(args.receipt)
    rules = load_json(args.operation_rules)
    source_evidence = selector_occurrences(args.implementation)
    occurrences = source_evidence["occurrences"]
    candidate_occurrences = [row for row in occurrences if row["candidate_branch"]]

    parent_recurrent = rules["parent_gri01_d8"]["recurrent_step"]["total_counted_operations"]
    parent_combined = rules["parent_gri01_d8"]["recurrent_plus_query_total"]
    query_operations = rules["parent_gri01_d8"]["query_readout"]["total_counted_operations"]
    declared = receipt["operation_counting"]

    # The audit deliberately charges only the disputed selector.  Existing
    # active/padding and query framing is outside this narrow closure; charging
    # those would only increase the observed overrun.
    selector_operations = 1 if len(candidate_occurrences) == 1 else None
    current_transform = declared["transform_state_operations"] + selector_operations if selector_operations is not None else None
    current_combined = declared["transform_plus_query_operations"] + selector_operations if selector_operations is not None else None
    current_preserve = declared["preserve_state_operations"] + selector_operations if selector_operations is not None else None

    external_transform = declared["transform_state_operations"]
    external_combined = declared["transform_plus_query_operations"]
    external_preserve = declared["preserve_state_operations"]
    current_budget_pass = (
        selector_operations is not None
        and current_transform <= parent_recurrent
        and current_combined <= parent_combined
    )
    external_budget_pass = external_transform <= parent_recurrent and external_combined <= parent_combined
    internal_selector = (
        not source_evidence["external_transition_class_argument"]
        and len(candidate_occurrences) == 1
    )

    receipt_out = {
        "unit": "GRI-02C.1-TRANSITION-SELECTOR-ACCOUNTING-AUDIT",
        "status": "CLOSED",
        "scope": {
            "training_performed": False,
            "evaluation_performed": False,
            "architecture_modified": False,
            "ceiling_modified": False,
            "disputed_selector_only": True,
            "excluded_existing_plumbing": [
                "active/padding mask",
                "query framing",
            ],
            "exclusion_reason": "This audit closes only the selector ambiguity; charging additional plumbing cannot restore the budget.",
        },
        "question": "Whether token-semantic transition dispatch is external to GRI-02C or computed by its executable candidate.",
        "source_evidence": source_evidence,
        "selector_determination": {
            "protocol_declares_semantic_source": config["transition_class"]["selection_source"],
            "executable_external_transition_class_argument": source_evidence["external_transition_class_argument"],
            "candidate_computes_wait_classification": internal_selector,
            "finding": "INTERNAL_TO_CANDIDATE" if internal_selector else "EXTERNAL_OR_UNRESOLVED",
            "reason": "The candidate receives token ids and executes ids == self.wait_index; no transition_class argument is supplied before candidate execution." if internal_selector else "The source does not establish exactly one internal candidate selector with an external transition-class interface.",
        },
        "frozen_budget_reference": {
            "operation_rules_sha256": sha256(args.operation_rules),
            "parent_recurrent_operations_max": parent_recurrent,
            "parent_recurrent_plus_query_operations_max": parent_combined,
            "query_readout_operations": query_operations,
            "comparison_definition": rules["counting_convention"]["comparison"],
        },
        "accounting": {
            "selector_charge_per_active_transition": selector_operations,
            "current_candidate": {
                "preserve_path_operations": current_preserve,
                "transform_state_operations": current_transform,
                "transform_plus_query_operations": current_combined,
                "budget_pass": current_budget_pass,
            },
            "external_dispatch_counterfactual": {
                "preserve_path_operations": external_preserve,
                "transform_state_operations": external_transform,
                "transform_plus_query_operations": external_combined,
                "budget_pass": external_budget_pass,
            },
        },
        "verdict": {
            "raw_algorithmic_finding": "SUPPORTED" if receipt.get("candidate_verdict") == "GRI02_ADVANTAGE" else "NOT_ESTABLISHED",
            "raw_candidate_receipt_verdict": receipt.get("candidate_verdict"),
            "formal_budget_verdict": "GRI02_ADVANTAGE" if current_budget_pass else "GRI02_NO_ADVANTAGE",
            "formal_verdict_reason": "The internally executed selector adds one comparison, producing 98 recurrent and 119 recurrent-plus-query operations against frozen ceilings of 97 and 118." if not current_budget_pass else "The charged selector remains within the frozen operation ceilings.",
            "algorithmic_result_preserved": True,
        },
        "artifact_hashes": {
            "config_sha256": sha256(args.config),
            "candidate_receipt_sha256": sha256(args.receipt),
            "implementation_sha256": sha256(args.implementation),
            "operation_rules_sha256": sha256(args.operation_rules),
            "audit_source_sha256": sha256(Path(__file__)),
        },
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt_out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "unit": receipt_out["unit"],
        "selector": receipt_out["selector_determination"]["finding"],
        "current_accounting": receipt_out["accounting"]["current_candidate"],
        "formal_verdict": receipt_out["verdict"]["formal_budget_verdict"],
        "algorithmic_finding": receipt_out["verdict"]["raw_algorithmic_finding"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
