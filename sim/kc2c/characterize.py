#!/usr/bin/env python3
"""KC-2C-D cooperative overflow preservation characterization."""
from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import json
import sys
from pathlib import Path
from typing import Any

import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from sim.kc0.kc1a.cell import KC1ACell
from sim.kc0.validate_bank import load_bank, sha256, validate_bank
from sim.runtime import canonical, tensor_digest
from sim.kc2b.export import export_slot
from sim.kc2c.protocol import cooperative_step, resource_manifest

BANK_PATH = ROOT / "sim" / "kc0" / "trial_bank.json"
CONFIG_PATH = HERE / "config.json"
PROTOCOL_PATH = HERE / "protocol.py"
CELL_PATH = ROOT / "sim" / "kc0" / "kc1a" / "cell.py"
EXPORT_PATH = ROOT / "sim" / "kc2b" / "export.py"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def packet_ids(bank: dict[str, Any]) -> dict[str, int]:
    return {packet["packet_id"]: index for index, packet in enumerate(bank["packets"], start=1)}


def fresh_pair() -> tuple[KC1ACell, torch.Tensor, KC1ACell, torch.Tensor]:
    cell_a = KC1ACell()
    cell_b = KC1ACell()
    state_a = cell_a.initial_state(1, dtype=torch.int64, device=torch.device("cpu"))
    state_b = cell_b.initial_state(1, dtype=torch.int64, device=torch.device("cpu"))
    return cell_a, state_a, cell_b, state_b


def state_digest(state: torch.Tensor) -> str:
    return tensor_digest(state)


def occupied_tokens(state: torch.Tensor) -> list[int]:
    return [
        payload
        for slot_id in range(8)
        for payload in [export_slot(state, slot_id)]
        if payload is not None
    ]


def run_stream(tokens: list[int], *, split_at: int | None = None) -> dict[str, Any]:
    cell_a, state_a, cell_b, state_b = fresh_pair()
    trace: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        state_a, state_b = cooperative_step(token, cell_a, state_a, cell_b, state_b)
        trace.append({
            "index": index,
            "incoming": token,
            "a": occupied_tokens(state_a),
            "b": occupied_tokens(state_b),
        })
        if split_at is not None and index + 1 == split_at:
            source_payload = cell_a.serialize_state(state_a)
            target_payload = cell_b.serialize_state(state_b)
            cell_a = KC1ACell()
            cell_b = KC1ACell()
            state_a = cell_a.restore_state(source_payload, dtype=torch.int64, device=torch.device("cpu"))
            state_b = cell_b.restore_state(target_payload, dtype=torch.int64, device=torch.device("cpu"))
    return {
        "trace": trace,
        "state_a": state_a,
        "state_b": state_b,
        "state_a_sha256": state_digest(state_a),
        "state_b_sha256": state_digest(state_b),
        "pair_tokens": sorted(set(occupied_tokens(state_a) + occupied_tokens(state_b))),
    }


def audit_protocol_source(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    classes = 0
    global_statements = 0
    step_parameters: list[str] | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ClassDef):
            classes += 1
        elif isinstance(node, ast.Global):
            global_statements += 1
        elif isinstance(node, ast.FunctionDef) and node.name == "cooperative_step":
            step_parameters = [argument.arg for argument in node.args.args]

    forbidden_names = {
        "packet_history",
        "history",
        "shadow",
        "cache",
        "global_memory",
        "population",
        "replication",
        "knowledge_store",
        "fixture_id",
        "query_id",
        "expected_token",
        "packet_id",
    }
    forbidden = sorted(names & forbidden_names)
    runtime_signature = [parameter.name for parameter in inspect.signature(cooperative_step).parameters.values()]
    expected_signature = ["incoming_token", "cell_a", "state_a", "cell_b", "state_b"]
    signature_ok = runtime_signature == expected_signature and step_parameters == expected_signature
    return {
        "status": "PASS" if not forbidden and classes == 0 and global_statements == 0 and signature_ok else "FAIL",
        "forbidden_names": forbidden,
        "class_count": classes,
        "global_statement_count": global_statements,
        "runtime_signature": runtime_signature,
        "source_signature": step_parameters,
        "signature_ok": signature_ok,
    }


def malformed_state_checks() -> dict[str, bool]:
    malformed_a = torch.zeros(1, 16, dtype=torch.int64)
    malformed_a[0, 0] = 1
    valid_b = KC1ACell().initial_state(1, dtype=torch.int64, device=torch.device("cpu"))
    try:
        cooperative_step(8, KC1ACell(), malformed_a, KC1ACell(), valid_b)
    except ValueError:
        a_failed_closed = True
    else:
        a_failed_closed = False

    valid_a = KC1ACell().initial_state(1, dtype=torch.int64, device=torch.device("cpu"))
    malformed_b = torch.zeros(1, 16, dtype=torch.int64)
    malformed_b[0, 8] = 2
    try:
        cooperative_step(8, KC1ACell(), valid_a, KC1ACell(), malformed_b)
    except ValueError:
        b_failed_closed = True
    else:
        b_failed_closed = False
    return {"malformed_a_failed_closed": a_failed_closed, "malformed_b_failed_closed": b_failed_closed}


def replay_snapshot(first_wave: list[int], second_wave: list[int], seventeenth: int, concentrated: list[int]) -> dict[str, Any]:
    duplicate = run_stream([first_wave[0], second_wave[0], second_wave[0]])
    interrupted = run_stream(first_wave + second_wave, split_at=10)
    loss_a = run_stream(first_wave + second_wave)
    loss_b = run_stream(first_wave + second_wave)
    return {
        "single_overflow_trace": run_stream([first_wave[0], second_wave[0]])["trace"],
        "collision_stream_pair": run_stream(first_wave + second_wave)["pair_tokens"],
        "seventeenth_pair": run_stream(first_wave + second_wave + [seventeenth])["pair_tokens"],
        "concentrated_pair": run_stream(concentrated)["pair_tokens"],
        "duplicate_states": [duplicate["state_a_sha256"], duplicate["state_b_sha256"]],
        "held_by_b_pair": run_stream([first_wave[0], second_wave[0], first_wave[0]])["pair_tokens"],
        "different_slot_pair": run_stream([first_wave[0], first_wave[1]])["pair_tokens"],
        "malformed": malformed_state_checks(),
        "restart_states": [interrupted["state_a_sha256"], interrupted["state_b_sha256"], interrupted["pair_tokens"]],
        "loss_a_b_tokens": sorted(occupied_tokens(loss_a["state_b"])),
        "loss_b_a_tokens": sorted(occupied_tokens(loss_b["state_a"])),
    }


def characterize(bank_path: Path = BANK_PATH, config_path: Path = CONFIG_PATH, receipt_path: Path | None = None) -> dict[str, Any]:
    bank_validation = validate_bank(bank_path)
    bank = load_bank(bank_path)
    config = load_config(config_path)
    ids = packet_ids(bank)
    first_wave = [ids[packet] for packet in config["first_wave_packets"]]
    second_wave = [ids[packet] for packet in config["second_wave_packets"]]
    seventeenth = ids[config["seventeenth_packet"]]
    concentrated = config["concentrated_collision_tokens"]

    anchor_errors = []
    if sha256(CELL_PATH) != config.get("cell_source_sha256"):
        anchor_errors.append("KC-1A source hash mismatch")
    if sha256(EXPORT_PATH) != config.get("export_source_sha256"):
        anchor_errors.append("KC-2B export source hash mismatch")
    if sha256(bank_path) != config.get("fixture_bank_sha256"):
        anchor_errors.append("KC-0 fixture bank hash mismatch")
    if config.get("status") != "DEV_CHARACTERIZATION_ONLY":
        anchor_errors.append("config is not development-only")
    if config.get("scientific_verdict") != "FORBIDDEN":
        anchor_errors.append("scientific verdict is not forbidden")

    single = run_stream([first_wave[0], second_wave[0]])
    single_overflow = {
        "trace": single["trace"],
        "a_has_new": second_wave[0] in occupied_tokens(single["state_a"]),
        "b_has_displaced": first_wave[0] in occupied_tokens(single["state_b"]),
    }

    collision_stream = run_stream(first_wave + second_wave)
    collision_stream_16 = {
        "a_tokens": occupied_tokens(collision_stream["state_a"]),
        "b_tokens": occupied_tokens(collision_stream["state_b"]),
        "pair_tokens": collision_stream["pair_tokens"],
        "pair_current": len(collision_stream["pair_tokens"]),
        "expected_pair_tokens": sorted(first_wave + second_wave),
    }

    saturation = run_stream(first_wave + second_wave + [seventeenth])
    saturation_tokens = saturation["pair_tokens"]
    seventeenth_saturation = {
        "incoming": seventeenth,
        "pair_current": len(saturation_tokens),
        "new_present": seventeenth in saturation_tokens,
        "oldest_same_slot_lost": first_wave[1] not in saturation_tokens,
        "retained_second_wave_same_slot": second_wave[1] in saturation_tokens,
        "pair_tokens": saturation_tokens,
    }

    concentrated_run = run_stream(concentrated)
    concentrated_result = {
        "trace": concentrated_run["trace"],
        "a_tokens": occupied_tokens(concentrated_run["state_a"]),
        "b_tokens": occupied_tokens(concentrated_run["state_b"]),
        "newest_present": concentrated[-1] in concentrated_run["state_a"].flatten().tolist() or concentrated[-1] in concentrated_run["pair_tokens"],
        "expected_a_newest": export_slot(concentrated_run["state_a"], concentrated[-1] % 8) == concentrated[-1],
        "expected_b_previous": export_slot(concentrated_run["state_b"], concentrated[-2] % 8) == concentrated[-2],
        "oldest_lost": concentrated[0] not in concentrated_run["pair_tokens"],
    }

    duplicate = run_stream([first_wave[0], second_wave[0], second_wave[0]])
    duplicate_reference = run_stream([first_wave[0], second_wave[0]])
    duplicate_incoming = {
        "unchanged_a": duplicate["state_a_sha256"] == duplicate_reference["state_a_sha256"],
        "unchanged_b": duplicate["state_b_sha256"] == duplicate_reference["state_b_sha256"],
    }

    held_by_b = run_stream([first_wave[0], second_wave[0], first_wave[0]])
    incoming_already_held_by_b = {
        "both_identities_retained": sorted(held_by_b["pair_tokens"]) == sorted([first_wave[0], second_wave[0]]),
        "incoming_now_in_a": first_wave[0] in occupied_tokens(held_by_b["state_a"]),
        "previous_now_in_b": second_wave[0] in occupied_tokens(held_by_b["state_b"]),
    }

    different_slot = run_stream([first_wave[0], first_wave[1]])
    different_slot_traffic = {
        "a_retains_first": first_wave[0] in occupied_tokens(different_slot["state_a"]),
        "a_receives_second": first_wave[1] in occupied_tokens(different_slot["state_a"]),
        "b_empty": occupied_tokens(different_slot["state_b"]) == [],
    }

    interrupted = run_stream(first_wave + second_wave, split_at=10)
    uninterrupted = run_stream(first_wave + second_wave)
    midstream_restart = {
        "same_a": interrupted["state_a_sha256"] == uninterrupted["state_a_sha256"],
        "same_b": interrupted["state_b_sha256"] == uninterrupted["state_b_sha256"],
        "same_pair": interrupted["pair_tokens"] == uninterrupted["pair_tokens"],
    }

    loss_a = run_stream(first_wave + second_wave)
    b_after_a_loss = sorted(occupied_tokens(loss_a["state_b"]))
    del loss_a["state_a"]
    loss_of_a = {
        "b_retains_displaced_wave": b_after_a_loss == sorted(first_wave),
        "retained_tokens": b_after_a_loss,
    }

    loss_b = run_stream(first_wave + second_wave)
    a_after_b_loss = sorted(occupied_tokens(loss_b["state_a"]))
    del loss_b["state_b"]
    loss_of_b = {
        "a_retains_newest_wave": a_after_b_loss == sorted(second_wave),
        "retained_tokens": a_after_b_loss,
    }

    malformed = malformed_state_checks()
    resource = resource_manifest()
    resource_pass = resource == {
        "coordinator_state_bytes": config["coordinator_state_bytes"],
        "coordinator_persistent_fields": config["coordinator_persistent_fields"],
        "transfer_payload_persistent": config["transfer_payload_persistent"],
        "uses_packet_history": False,
        "uses_shadow_slot_table": False,
        "uses_global_memory": False,
        "uses_population_logic": False,
        "uses_replication": False,
    }
    protocol_audit = audit_protocol_source(PROTOCOL_PATH)
    first = {
        "single_overflow": single_overflow,
        "collision_stream_16": collision_stream_16,
        "seventeenth_packet_saturation": seventeenth_saturation,
        "concentrated_collision_recency": concentrated_result,
        "duplicate_incoming": duplicate_incoming,
        "incoming_already_held_by_b": incoming_already_held_by_b,
        "different_slot_traffic": different_slot_traffic,
        "malformed_state": malformed,
        "midstream_restart": midstream_restart,
        "loss_of_a": loss_of_a,
        "loss_of_b": loss_of_b,
    }
    replay_first = replay_snapshot(first_wave, second_wave, seventeenth, concentrated)
    replay_second = replay_snapshot(first_wave, second_wave, seventeenth, concentrated)
    replay_pass = canonical(replay_first) == canonical(replay_second)
    first["replay_snapshot"] = replay_first
    checks = {
        "anchors": not anchor_errors,
        "bank_validation": bank_validation["status"] == "PASS",
        "coordinator_state_zero": resource_pass,
        "source_signature_audit": protocol_audit["status"] == "PASS",
        "single_overflow": single_overflow["a_has_new"] and single_overflow["b_has_displaced"],
        "collision_stream_16": collision_stream_16["pair_current"] == 16 and collision_stream_16["pair_tokens"] == sorted(first_wave + second_wave),
        "seventeenth_packet_saturation": seventeenth_saturation["new_present"] and seventeenth_saturation["oldest_same_slot_lost"] and seventeenth_saturation["pair_current"] == 16,
        "concentrated_collision_recency": all(concentrated_result.values()),
        "duplicate_incoming": all(duplicate_incoming.values()),
        "incoming_already_held_by_b": all(incoming_already_held_by_b.values()),
        "different_slot_traffic": all(different_slot_traffic.values()),
        "malformed_state_fail_closed": all(malformed.values()),
        "midstream_restart": all(midstream_restart.values()),
        "loss_of_a": loss_of_a["b_retains_displaced_wave"],
        "loss_of_b": loss_of_b["a_retains_newest_wave"],
        "replay": replay_pass,
    }
    passed = all(checks.values())
    receipt = {
        "unit": "KC-2C-D",
        "status": "PASS" if passed else "INVALID",
        "verdict": "KC_2C_DEV_COMPLETE" if passed else "KC_2C_DEV_INVALID",
        "cell_candidate_id": config["cell_candidate_id"],
        "cell_source_sha256": sha256(CELL_PATH),
        "export_source_sha256": sha256(EXPORT_PATH),
        "config_sha256": sha256(config_path),
        "fixture_bank_sha256": sha256(bank_path),
        "protocol_source_sha256": sha256(PROTOCOL_PATH),
        "anchor_errors": anchor_errors,
        "coordinator_resource": resource,
        "protocol_source_audit": protocol_audit,
        "scientific_thresholds": "UNDEFINED_IN_DEVELOPMENT",
        "scientific_verdict": "FORBIDDEN",
        "checks": checks,
        "characterization": first,
        "note": "Development cooperative overflow characterization only; reproduction, population, and scientific conclusions are forbidden.",
    }
    receipt["canonical_receipt_sha256"] = hashlib.sha256(canonical(receipt).encode("utf-8")).hexdigest()
    if receipt_path is not None:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, default=BANK_PATH)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    receipt = characterize(args.bank, args.config, args.receipt)
    print(json.dumps({"status": receipt["status"], "unit": receipt["unit"], "verdict": receipt["verdict"]}, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
