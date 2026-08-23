#!/usr/bin/env python3
"""GRI-02B: executable preregistration, fixtures, oracle, and verdict logic.

This file contains no GRI-02 candidate cell, mechanism, training loop, or
optimizer execution.  It freezes and checks the environment in which a later
authorized candidate could be evaluated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = Path(__file__).resolve().parent


def canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_for(delays: list[int], fit_delays: set[int]) -> str:
    return "fit" if all(delay in fit_delays for delay in delays) else "held_out"


def build_fixture_bank(config: dict) -> dict:
    delays = config["delay_set"]
    fit_delays = set(config["decoder_protocol"]["fit_delays"])
    alphabet = config["alphabet"]
    fixtures = []

    def add(family, task, tokens, label, metadata, delays_for_split):
        if any(token not in alphabet for token in tokens):
            raise ValueError(f"fixture token outside frozen alphabet: {tokens}")
        split = split_for(delays_for_split, fit_delays)
        fixtures.append({
            "fixture_id": f"F{len(fixtures):04d}",
            "family": family,
            "task": task,
            "tokens": tokens,
            "label": label,
            "split": split,
            **metadata,
        })

    for delay in delays:
        for bit in (0, 1):
            add(
                "preserve_delayed_bit",
                "delayed_bit",
                [f"BIT_{bit}"] + ["WAIT"] * delay + ["QUERY_DELAY"],
                bit,
                {"N": delay},
                [delay],
            )
        for old in ("A", "B"):
            for new in ("A", "B"):
                add(
                    "preserve_correction",
                    "correction",
                    [old, "CORRECT", new] + ["WAIT"] * delay + ["QUERY_CORRECTION"],
                    int(new == "B"),
                    {"N": delay, "old": old, "new": new},
                    [delay],
                )
        for first, second in (("A", "B"), ("B", "A")):
            add(
                "preserve_order",
                "order",
                [first, second] + ["WAIT"] * delay + ["QUERY_ORDER"],
                int((first, second) == ("B", "A")),
                {"N": delay, "first": first, "second": second},
                [delay],
            )

    for n in delays:
        for m in delays:
            for old in ("A", "B"):
                for new in ("A", "B"):
                    add(
                        "transform_correction",
                        "correction",
                        [old] + ["WAIT"] * n + ["CORRECT", new] + ["WAIT"] * m + ["QUERY_CORRECTION"],
                        int(new == "B"),
                        {"N": n, "M": m, "old": old, "new": new},
                        [n, m],
                    )
            for first, second in (("A", "B"), ("B", "A")):
                add(
                    "transform_order",
                    "order",
                    [first] + ["WAIT"] * n + [second] + ["WAIT"] * m + ["QUERY_ORDER"],
                    int((first, second) == ("B", "A")),
                    {"N": n, "M": m, "first": first, "second": second},
                    [n, m],
                )

    return {
        "schema": "GRI-02B-FIXTURES-1",
        "alphabet": alphabet,
        "delay_set": delays,
        "fit_delays": sorted(fit_delays),
        "held_out_delays": config["decoder_protocol"]["held_out_delays"],
        "transform_fit_rule": config["decoder_protocol"]["fit_transform_pairs"],
        "transform_held_out_rule": config["decoder_protocol"]["held_out_transform_pairs"],
        "fixtures": fixtures,
        "counts": {
            "total": len(fixtures),
            "fit": sum(f["split"] == "fit" for f in fixtures),
            "held_out": sum(f["split"] == "held_out" for f in fixtures),
            "by_family": dict(sorted(Counter(f["family"] for f in fixtures).items())),
        },
    }


def oracle_step(state: dict, token: str) -> None:
    if token in ("BIT_0", "BIT_1"):
        state["memory"] = int(token == "BIT_1")
    elif token in ("A", "B"):
        if state["first"] is None:
            state["first"] = token
        elif state["second"] is None:
            state["second"] = token
        state["memory"] = int(token == "B")
    elif token in ("QUERY_DELAY", "QUERY_CORRECTION"):
        state["last_output"] = state["memory"]
    elif token == "QUERY_ORDER":
        state["last_output"] = int((state["first"], state["second"]) == ("B", "A"))


def oracle_run(tokens: list[str], initial=None) -> tuple[dict, int | None]:
    state = initial or {"memory": None, "first": None, "second": None, "last_output": None}
    for token in tokens:
        oracle_step(state, token)
    return state, state["last_output"]


def oracle_bytes(state: dict) -> bytes:
    return canonical({"schema": "GRI-02B-ORACLE-STATE-1", "state": state})


def oracle_from_bytes(payload: bytes) -> dict:
    value = json.loads(payload.decode("utf-8"))
    if value.get("schema") != "GRI-02B-ORACLE-STATE-1":
        raise ValueError("oracle serialization schema mismatch")
    state = value["state"]
    if set(state) != {"memory", "first", "second", "last_output"}:
        raise ValueError("oracle state fields mismatch")
    return state


def check_oracle(fixtures: list[dict]) -> dict:
    failures = []
    restart_cases = 0
    for fixture in fixtures:
        full_state, full_output = oracle_run(fixture["tokens"])
        if full_output != fixture["label"]:
            failures.append({"fixture_id": fixture["fixture_id"], "kind": "oracle_output", "expected": fixture["label"], "observed": full_output})
        for split in range(len(fixture["tokens"]) + 1):
            left_state, _ = oracle_run(fixture["tokens"][:split])
            resumed_state = oracle_from_bytes(oracle_bytes(left_state))
            resumed_state, resumed_output = oracle_run(fixture["tokens"][split:], resumed_state)
            restart_cases += 1
            if resumed_output != full_output or resumed_state != full_state:
                failures.append({"fixture_id": fixture["fixture_id"], "kind": "serialize_restart", "split": split})
    return {
        "status": "PASS" if not failures else "FAIL",
        "fixture_count": len(fixtures),
        "restart_cases": restart_cases,
        "failures": failures,
    }


def check_operation_rules(rules: dict) -> dict:
    checks = {
        "parent_parameter_total": rules["parent_gri01_d8"]["parameter_count"]["total_trainable_parameters"] == 170,
        "gru_parameter_total": rules["matched_gru_d8"]["parameter_count"]["total_trainable_parameters"] == 506,
        "gru_exceeds_parent_parameters": rules["matched_gru_d8"]["parameter_count"]["total_trainable_parameters"] > rules["parent_gri01_d8"]["parameter_count"]["total_trainable_parameters"],
        "parent_recurrent_total": rules["parent_gri01_d8"]["recurrent_step"]["total_counted_operations"] == 97,
        "parent_query_total": rules["parent_gri01_d8"]["query_readout"]["total_counted_operations"] == 21,
        "parent_combined_total": rules["parent_gri01_d8"]["recurrent_plus_query_total"] == 118,
        "gru_recurrent_total": rules["matched_gru_d8"]["recurrent_step"]["total_counted_operations"] == 505,
        "gru_query_total": rules["matched_gru_d8"]["query_readout"]["total_counted_operations"] == 21,
        "gru_combined_total": rules["matched_gru_d8"]["recurrent_plus_query_total"] == 526,
        "gru_exceeds_parent": rules["matched_gru_d8"]["recurrent_plus_query_total"] > rules["parent_gri01_d8"]["recurrent_plus_query_total"],
        "q8_overhead_reported": rules["q8_state_storage_overhead_reported_separately"]["total_counted_operations"] == 57,
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def evaluate_future_verdict(record: dict, config: dict) -> str:
    required = config["verdict_logic"]["required_true_fields"]
    if not isinstance(record, dict) or any(not isinstance(record.get(field), bool) for field in required):
        return "GRI02_INCONCLUSIVE"
    if all(record[field] for field in required):
        return "GRI02_ADVANTAGE"
    return "GRI02_NO_ADVANTAGE"


def verdict_self_test(config: dict) -> dict:
    fields = config["verdict_logic"]["required_true_fields"]
    base = {field: True for field in fields}
    base["oracle_match"] = True
    oracle_match = evaluate_future_verdict(base, config)
    base["oracle_match"] = False
    oracle_mismatch = evaluate_future_verdict(base, config)
    parent_failure = dict(base)
    parent_failure["parent_opponent_pass"] = False
    missing = dict(base)
    del missing[fields[0]]
    checks = {
        "all_required_passes_advantage": oracle_match == "GRI02_ADVANTAGE",
        "oracle_mismatch_does_not_block": oracle_mismatch == "GRI02_ADVANTAGE",
        "parent_equivalence_no_advantage": evaluate_future_verdict(parent_failure, config) == "GRI02_NO_ADVANTAGE",
        "missing_field_inconclusive": evaluate_future_verdict(missing, config) == "GRI02_INCONCLUSIVE",
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=EXPERIMENTS / "gri02b_config.json")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/results/gri02b_preregistration_receipt.json")
    parser.add_argument("--write-fixtures", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("status") != "FROZEN_BEFORE_RUN":
        raise SystemExit("GRI-02B config is not frozen")
    contract_path = (args.config.parent / config["contract_file"]).resolve()
    if digest(contract_path) != config["contract_sha256"]:
        raise SystemExit("GRI-02A contract hash mismatch")
    rules_path = args.config.with_name(config["operation_rules_file"])
    fixture_path = args.config.with_name(config["fixture_bank_file"])
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    expected_bank = build_fixture_bank(config)
    if args.write_fixtures:
        fixture_path.write_bytes(canonical(expected_bank))
        print(json.dumps({"fixture_file": str(fixture_path), "fixture_sha256": digest(fixture_path), "counts": expected_bank["counts"]}, indent=2))
        return 0
    if not fixture_path.exists():
        raise SystemExit("fixture bank missing; run with --write-fixtures before final validation")
    fixture_bank = json.loads(fixture_path.read_text(encoding="utf-8"))
    if fixture_bank != expected_bank:
        raise SystemExit("literal fixture bank does not match frozen generator")
    expected_rules_hash = config.get("operation_rules_sha256")
    if expected_rules_hash and digest(rules_path) != expected_rules_hash:
        raise SystemExit("operation rules hash mismatch")
    expected_fixture_hash = config.get("fixture_bank_sha256")
    if expected_fixture_hash and digest(fixture_path) != expected_fixture_hash:
        raise SystemExit("fixture bank hash mismatch")
    oracle = check_oracle(fixture_bank["fixtures"])
    operation_rules = check_operation_rules(rules)
    verdict_tests = verdict_self_test(config)
    all_pass = oracle["status"] == "PASS" and operation_rules["status"] == "PASS" and verdict_tests["status"] == "PASS"
    receipt = {
        "unit": config["unit"],
        "status": "GRI02B_PREREGISTRATION_READY" if all_pass else "GRI02B_PREREGISTRATION_BLOCKED",
        "candidate_present": False,
        "candidate_verdict": "NOT_RUN",
        "config_sha256": digest(args.config),
        "contract_sha256": digest(contract_path),
        "operation_rules_sha256": digest(rules_path),
        "fixture_bank_sha256": digest(fixture_path),
        "implementation_sha256": digest(Path(__file__)),
        "fixture_bank": fixture_bank["counts"],
        "decoder_protocol": config["decoder_protocol"],
        "quantization": config["quantization"],
        "serialization": config["serialization"],
        "budgets": config["budgets"],
        "training_protocol": config["training_protocol"],
        "operation_rules": operation_rules,
        "oracle": oracle,
        "verdict_logic_self_test": verdict_tests,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(receipt))
    print(json.dumps({
        "unit": receipt["unit"],
        "status": receipt["status"],
        "candidate_present": receipt["candidate_present"],
        "fixture_bank": receipt["fixture_bank"],
        "oracle": {"status": oracle["status"], "restart_cases": oracle["restart_cases"]},
        "operation_rules": operation_rules["status"],
        "verdict_logic_self_test": verdict_tests["status"],
    }, indent=2))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
