from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.forge.forge import Chain, Forge, Registry, canonical_json
from experiments.forge.model_tools import broker_request
from experiments.forge.te0_io import blueprint_from_json, file_sha256
from experiments.forge_e1.collect_te0_e1 import SYSTEM_PROMPT, load_identity, seed_for
from experiments.forge_e1.generate_te0_e1 import make_pool
from experiments.forge_e1.interface_tools import InterfaceRepairToolFactory


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def verify_record(path: Path, expected_status: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("status") != expected_status:
        raise ValueError(f"TE0_E1_RECORD_STATUS_MISMATCH:{path.name}")
    observed = value.get("record_sha256")
    body = {k: v for k, v in value.items() if k != "record_sha256"}
    expected = hashlib.sha256(canonical_bytes(body)).hexdigest()
    if observed != expected:
        raise ValueError(f"TE0_E1_RECORD_DIGEST_MISMATCH:{path.name}")
    return value


def reconstruct_champion(manifest: dict[str, Any]) -> tuple[Forge, Chain]:
    champion = manifest.get("champion")
    if not isinstance(champion, dict):
        raise ValueError("TE0_E1_CHAMPION_MISSING")
    blueprints = manifest.get("tool_blueprints")
    if not isinstance(blueprints, list):
        raise ValueError("TE0_E1_BLUEPRINTS_MISSING")
    registry = Registry()
    factory = InterfaceRepairToolFactory()
    for row in blueprints:
        bp = blueprint_from_json(row)
        registry.register(factory.compile(bp))
    names = tuple(str(x) for x in champion.get("tools", []))
    cost = sum(registry.get(name).cost for name in names)
    chain = Chain(names, str(champion["input_kind"]), str(champion["output_kind"]), cost)
    if chain.chain_id != champion.get("chain_id") or cost != champion.get("cost"):
        raise ValueError("TE0_E1_CHAMPION_BINDING_MISMATCH")
    return Forge(registry), chain


def raw_parse(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def structural_valid(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == {"label", "evidence"} and isinstance(value.get("label"), str) and isinstance(value.get("evidence"), list)


def best_constant_null(targets: list[dict[str, Any]]) -> float:
    if not targets:
        return 0.0
    counts: dict[str, int] = {}
    for target in targets:
        key = canonical_json(target)
        counts[key] = counts.get(key, 0) + 1
    return max(counts.values()) / len(targets)


def burn(path: Path, authorization: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "TE0_E1_VAULT_CONSUMED",
        "authorization_record_sha256": authorization["record_sha256"],
    }
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except FileExistsError as exc:
        raise RuntimeError("TE0_E1_VAULT_ALREADY_CONSUMED") from exc


def main() -> None:
    ap = argparse.ArgumentParser(description="One-shot TE0-E1 hidden Vault Judge.")
    ap.add_argument("--champion", type=Path, required=True)
    ap.add_argument("--model-identity", type=Path, required=True)
    ap.add_argument("--authorization", type=Path, required=True)
    ap.add_argument("--vault-seed-file", type=Path, required=True)
    ap.add_argument("--broker-socket", type=Path, required=True)
    ap.add_argument("--consume-marker", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--raw-output", type=Path, required=True)
    args = ap.parse_args()

    if args.receipt.exists() or args.raw_output.exists():
        raise FileExistsError("TE0_E1_REFUSE_OVERWRITE")
    champion = verify_record(args.champion, "TE0_E1_DEVELOPMENT_CHAMPION_FROZEN")
    identity = load_identity(args.model_identity)
    authorization = verify_record(args.authorization, "TE0_E1_ONE_RUN_AUTHORIZED")

    bindings = authorization["bindings"]
    preburn_checks = {
        "champion_file": file_sha256(args.champion) == bindings["champion_file_sha256"],
        "champion_record": champion["record_sha256"] == bindings["champion_record_sha256"],
        "identity_file": file_sha256(args.model_identity) == bindings["model_identity_file_sha256"],
        "identity_record": identity["record_sha256"] == bindings["model_identity_record_sha256"],
        "vault_seed_file": file_sha256(args.vault_seed_file) == bindings["vault_seed_file_sha256"],
    }
    if not all(preburn_checks.values()):
        raise ValueError(f"TE0_E1_PREBURN_BINDING_FAIL:{preburn_checks}")

    # Irreversible boundary: after this line any crash/error spends the Vault.
    burn(args.consume_marker, authorization)

    raw_rows: list[dict[str, Any]] = []
    try:
        seed_text = args.vault_seed_file.read_text(encoding="utf-8").strip()
        if hashlib.sha256(seed_text.encode("utf-8")).hexdigest() != bindings["vault_seed_text_sha256"]:
            raise ValueError("TE0_E1_VAULT_SEED_TEXT_DIGEST_MISMATCH")
        rows = make_pool(seed_text=seed_text, count=int(bindings["vault_count"]), prefix="V")
        forge, chain = reconstruct_champion(champion)

        raw_exact = 0
        raw_structural = 0
        repaired_exact = 0
        repaired_structural = 0
        already_valid = 0
        preserved_valid = 0
        target_rows: list[dict[str, Any]] = []
        request_attempts = 0

        args.raw_output.parent.mkdir(parents=True, exist_ok=True)
        with args.raw_output.open("x", encoding="utf-8") as raw_handle:
            for ordinal, row in enumerate(rows):
                cid = row["case_id"]
                target = row["target"]
                target_rows.append(target)
                body = {
                    "model": identity["model"],
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": row["prompt"]},
                    ],
                    "options": {"temperature": 0, "seed": seed_for(cid), "num_predict": 256},
                }
                request_attempts += 1
                outer = broker_request(args.broker_socket.resolve(), body)
                content = outer.get("message", {}).get("content")
                if not isinstance(content, str):
                    raise RuntimeError(f"TE0_E1_MISSING_CONTENT:{cid}")
                parsed = raw_parse(content)
                raw_is_structural = structural_valid(parsed)
                raw_is_exact = parsed == target
                raw_structural += int(raw_is_structural)
                raw_exact += int(raw_is_exact)
                already_valid += int(raw_is_exact)

                try:
                    repaired = forge.run_chain(chain, content)
                    repaired_is_structural = structural_valid(repaired)
                    repaired_is_exact = repaired == target
                except Exception as exc:
                    repaired = {"repair_exception": type(exc).__name__}
                    repaired_is_structural = False
                    repaired_is_exact = False
                repaired_structural += int(repaired_is_structural)
                repaired_exact += int(repaired_is_exact)
                if raw_is_exact:
                    preserved_valid += int(repaired_is_exact)

                raw_record = {
                    "ordinal": ordinal,
                    "case_id": cid,
                    "prompt_sha256": hashlib.sha256(row["prompt"].encode("utf-8")).hexdigest(),
                    "target_sha256": hashlib.sha256(canonical_bytes(target)).hexdigest(),
                    "raw_content": content,
                    "raw_content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "raw_exact": raw_is_exact,
                    "repaired_sha256": hashlib.sha256(canonical_bytes(repaired)).hexdigest(),
                    "repaired_exact": repaired_is_exact,
                }
                raw_handle.write(json.dumps(raw_record, sort_keys=True) + "\n")
                raw_rows.append(raw_record)

        n = len(rows)
        raw_exact_rate = raw_exact / n
        repaired_exact_rate = repaired_exact / n
        raw_structural_rate = raw_structural / n
        repaired_structural_rate = repaired_structural / n
        improvement = repaired_exact_rate - raw_exact_rate
        null_score = best_constant_null(target_rows)
        margin = repaired_exact_rate - null_score
        preservation = preserved_valid / already_valid if already_valid else 1.0
        thresholds = authorization["thresholds"]
        gates = {
            "vault_exact": repaired_exact_rate >= float(thresholds["vault_exact_rate"]),
            "vault_structural": repaired_structural_rate >= float(thresholds["vault_structural_validity_rate"]),
            "raw_improvement": improvement >= float(thresholds["improvement_over_raw"]),
            "null_margin": margin >= float(thresholds["margin_over_null"]),
            "preservation": preservation == float(thresholds["preserve_already_valid"]),
            "one_request_per_case": request_attempts == n,
        }
        if raw_exact_rate >= 0.98:
            status = "TE0_E1_REPAIR_NOT_NEEDED"
            # A repair does not get promoted if the producer does not need one.
            verdict = "INCONCLUSIVE"
        elif all(gates.values()):
            status = "TE0_E1_INTERFACE_REPAIR_PASS"
            verdict = "PASS"
        else:
            status = "TE0_E1_INTERFACE_REPAIR_FAIL"
            verdict = "FAIL"
        receipt: dict[str, Any] = {
            "schema_version": 1,
            "unit": "TE0-E1",
            "status": status,
            "verdict": verdict,
            "authorization_consumed": True,
            "request_attempts": request_attempts,
            "vault_count": n,
            "chain_id": chain.chain_id,
            "raw": {
                "exact_rate": raw_exact_rate,
                "structural_validity_rate": raw_structural_rate,
            },
            "repair": {
                "exact_rate": repaired_exact_rate,
                "structural_validity_rate": repaired_structural_rate,
                "improvement_over_raw": improvement,
                "best_constant_null": null_score,
                "margin_over_null": margin,
                "preservation_rate": preservation,
            },
            "gates": gates,
            "bindings": {
                "champion_file_sha256": file_sha256(args.champion),
                "model_identity_file_sha256": file_sha256(args.model_identity),
                "authorization_file_sha256": file_sha256(args.authorization),
                "vault_seed_file_sha256": file_sha256(args.vault_seed_file),
                "raw_output_sha256": file_sha256(args.raw_output),
            },
        }
    except Exception as exc:
        receipt = {
            "schema_version": 1,
            "unit": "TE0-E1",
            "status": "TE0_E1_INTEGRITY_INVALID",
            "verdict": "INCONCLUSIVE",
            "authorization_consumed": True,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "raw_rows_persisted": len(raw_rows),
        }

    receipt["record_sha256"] = hashlib.sha256(canonical_bytes(receipt)).hexdigest()
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if receipt["status"] == "TE0_E1_INTEGRITY_INVALID":
        raise SystemExit(2)
    if receipt["status"] == "TE0_E1_INTERFACE_REPAIR_FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
