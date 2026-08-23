from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from experiments.forge.ecology import DeclarativeToolFactory, Judge, Ledger, promote_skill
from experiments.forge.forge import Chain, Forge, Registry, sha256_json
from experiments.forge.te0_io import blueprint_from_json, file_sha256, load_cases


def verify_authorization(path: Path) -> dict:
    auth = json.loads(path.read_text(encoding="utf-8"))
    if auth.get("status") != "TE0_VAULT_ONE_RUN_AUTHORIZED" or auth.get("executions_authorized") != 1 or auth.get("consumed") is not False:
        raise ValueError("authorization is not an unused one-run TE0 Vault authorization")
    observed = auth.get("authorization_record_sha256")
    body = {k: v for k, v in auth.items() if k != "authorization_record_sha256"}
    if observed != sha256_json(body):
        raise ValueError("authorization digest mismatch")
    return auth


def main() -> None:
    ap = argparse.ArgumentParser(description="TE0 independent Vault judge. No search or mutation is available here.")
    ap.add_argument("--champion", type=Path, required=True)
    ap.add_argument("--vault", type=Path, required=True)
    ap.add_argument("--authorization", type=Path, required=True)
    ap.add_argument("--consume-marker", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--skill-output", type=Path)
    ap.add_argument("--ledger", type=Path)
    args = ap.parse_args()

    auth = verify_authorization(args.authorization)
    manifest = json.loads(args.champion.read_text(encoding="utf-8"))
    bindings = auth["bindings"]
    if file_sha256(args.champion) != bindings["champion_manifest_sha256"]:
        raise ValueError("champion manifest binding mismatch")
    if file_sha256(args.vault) != bindings["vault_sha256"]:
        raise ValueError("Vault binding mismatch")
    if manifest["champion"]["chain_id"] != bindings["champion_chain_id"]:
        raise ValueError("champion chain binding mismatch")

    # Burn the authorization before parsing/scoring Vault contents. A crash still
    # consumes this exact experiment generation.
    args.consume_marker.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.consume_marker.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "status": "TE0_VAULT_CONSUMED",
                "authorization_record_sha256": auth["authorization_record_sha256"],
                "champion_chain_id": bindings["champion_chain_id"],
                "vault_sha256": bindings["vault_sha256"],
            }, indent=2, sort_keys=True) + "\n")
    except FileExistsError as exc:
        raise RuntimeError("TE0_VAULT_ALREADY_CONSUMED") from exc

    registry = Registry()
    factory = DeclarativeToolFactory()
    for row in manifest["tool_blueprints"]:
        bp = blueprint_from_json(row)
        registry.register(factory.compile(bp))

    c = manifest["champion"]
    chain = Chain(tuple(c["tools"]), str(c["input_kind"]), str(c["output_kind"]), int(c["cost"]))
    if chain.chain_id != c["chain_id"]:
        raise ValueError("champion chain digest mismatch")

    vault = load_cases(args.vault)
    judge = Judge(Forge(registry))
    receipt = judge.evaluate_once(
        chain,
        vault,
        threshold=float(auth["threshold"]),
        min_margin_over_null=float(auth["min_margin_over_null"]),
        receipt_path=args.receipt,
    )

    skill = None
    if receipt.verdict.value == "PASS":
        skill = promote_skill(chain, receipt)
        if args.skill_output:
            if args.skill_output.exists():
                raise FileExistsError(f"refusing to overwrite skill packet: {args.skill_output}")
            args.skill_output.parent.mkdir(parents=True, exist_ok=True)
            args.skill_output.write_text(json.dumps({**asdict(skill), "packet_sha256": skill.packet_sha256}, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.ledger:
        Ledger(args.ledger).append({
            "experiment": "TE0-VAULT",
            "authorization_record_sha256": auth["authorization_record_sha256"],
            "champion_chain_id": chain.chain_id,
            "vault_sha256": bindings["vault_sha256"],
            "judge_verdict": receipt.verdict.value,
            "judge_score": receipt.score,
            "judge_receipt_sha256": receipt.receipt_sha256,
            "skill_promoted": skill is not None,
            "authority": skill is not None,
        })

    print(json.dumps({
        "verdict": receipt.verdict.value,
        "score": receipt.score,
        "best_null_score": receipt.best_null_score,
        "receipt_sha256": receipt.receipt_sha256,
        "skill_promoted": skill is not None,
        "skill_packet_sha256": skill.packet_sha256 if skill is not None else None,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
