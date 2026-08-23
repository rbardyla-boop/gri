from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments.forge.ecology import Ablator, Composer, Ledger, ToolSmith, classify_failure
from experiments.forge.forge import Forge, Registry, SearchConfig
from experiments.forge.te0_io import blueprint_to_json, file_sha256, load_cases


def main() -> None:
    ap = argparse.ArgumentParser(description="TE0 development search. This command intentionally has no Vault argument.")
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--dev", type=Path, required=True)
    ap.add_argument("--signals", type=Path, required=True, help="JSON object of failure signals")
    ap.add_argument("--input-kind", required=True)
    ap.add_argument("--output-kind", required=True)
    ap.add_argument("--max-depth", type=int, default=4)
    ap.add_argument("--max-cost", type=int, default=8)
    ap.add_argument("--max-candidates", type=int, default=10000)
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--ledger", type=Path)
    args = ap.parse_args()

    build = load_cases(args.build)
    dev = load_cases(args.dev)
    signals = json.loads(args.signals.read_text(encoding="utf-8"))
    if not isinstance(signals, dict):
        raise ValueError("signals must be a JSON object")

    diagnosis = classify_failure(signals)
    registry = Registry()
    smith = ToolSmith()
    blueprints = smith.propose(diagnosis, build, args.input_kind, args.output_kind)
    smith.register(registry, blueprints)
    if not registry.names():
        raise RuntimeError("TE0_NO_TOOLS_PROPOSED")

    forge = Forge(registry)
    composer = Composer(forge)
    config = SearchConfig(
        args.input_kind,
        args.output_kind,
        max_depth=args.max_depth,
        max_cost=args.max_cost,
        max_candidates=args.max_candidates,
    )
    ranked = composer.search(dev, config)
    if not ranked:
        raise RuntimeError("TE0_NO_VALID_RECIPES")

    champion = ranked[0]
    ablations = Ablator(forge).single_tool_ablations(champion.chain, dev, champion.dev_score)
    manifest = {
        "schema_version": 1,
        "unit": "TE0",
        "phase": "DEVELOPMENT",
        "authority": False,
        "vault_seen": False,
        "failure_diagnosis": {
            "class": diagnosis.failure_class.value,
            "evidence": list(diagnosis.evidence),
            "recommended_action": diagnosis.recommended_action,
        },
        "bindings": {
            "build_sha256": file_sha256(args.build),
            "dev_sha256": file_sha256(args.dev),
            "signals_sha256": file_sha256(args.signals),
        },
        "search_config": {
            "input_kind": config.input_kind,
            "output_kind": config.output_kind,
            "max_depth": config.max_depth,
            "max_cost": config.max_cost,
            "max_candidates": config.max_candidates,
        },
        "tool_blueprints": [blueprint_to_json(x) for x in blueprints],
        "champion": {
            "chain_id": champion.chain.chain_id,
            "tools": list(champion.chain.tools),
            "input_kind": champion.chain.input_kind,
            "output_kind": champion.chain.output_kind,
            "cost": champion.chain.cost,
            "dev_score": champion.dev_score,
            "objective": champion.objective,
            "null_margin": champion.null_margin,
            "failures": list(champion.failures),
        },
        "top_candidates": [
            {
                "chain_id": x.chain.chain_id,
                "tools": list(x.chain.tools),
                "cost": x.chain.cost,
                "dev_score": x.dev_score,
                "objective": x.objective,
                "null_margin": x.null_margin,
            }
            for x in ranked[: max(1, args.top_k)]
        ],
        "ablations": [
            {
                "removed_tool": x.removed_tool,
                "valid": x.valid,
                "score": x.score,
                "delta_from_full": x.delta_from_full,
                "reason": x.reason,
            }
            for x in ablations
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite development manifest: {args.output}")
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.ledger:
        Ledger(args.ledger).append({
            "experiment": "TE0-DEV",
            "manifest_sha256": file_sha256(args.output),
            "champion_chain_id": champion.chain.chain_id,
            "dev_score": champion.dev_score,
            "authority": False,
        })

    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
