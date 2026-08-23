from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .core import audit_result, create_freeze, replay_run, run_frozen, verify_freeze, verdict_frozen


def _emit(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gauntlet",
        description="Evaluation-integrity firewall: freeze, run, replay, and mechanically audit AI evaluations.",
    )
    parser.add_argument("--version", action="version", version=f"gauntlet {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    freeze = sub.add_parser("freeze", help="freeze a TOML/JSON experiment spec and declared inputs")
    freeze.add_argument("spec")
    freeze.add_argument("--output")

    verify = sub.add_parser("verify", help="verify a frozen manifest against current files and repository state")
    verify.add_argument("manifest")

    run = sub.add_parser("run", help="execute exactly the run bound by a freeze manifest")
    run.add_argument("manifest")
    run.add_argument("--run-id")

    replay = sub.add_parser("replay", help="rerun a frozen evaluation and compare its declared outputs")
    replay.add_argument("manifest")
    replay.add_argument("receipt")
    replay.add_argument("--run-id")

    audit = sub.add_parser(
        "audit-result",
        help="mechanically apply gates to an existing result; explicitly retrospective, not preregistered",
    )
    audit.add_argument("spec")
    audit.add_argument("result")

    verdict = sub.add_parser("verdict", help="bind freeze, run receipt, optional replay, and result gates")
    verdict.add_argument("manifest")
    verdict.add_argument("receipt")
    verdict.add_argument("--replay")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "freeze":
            value = create_freeze(args.spec, args.output)
            _emit(value)
            return 0
        if args.command == "verify":
            value = verify_freeze(args.manifest)
            _emit(value)
            return 0 if value["pass"] else 1
        if args.command == "run":
            value = run_frozen(args.manifest, args.run_id)
            _emit(value)
            return 0 if value["run_status"] == "PASS" else 1
        if args.command == "replay":
            value = replay_run(args.manifest, args.receipt, args.run_id)
            _emit(value)
            return 0 if value["pass"] else 1
        if args.command == "audit-result":
            value = audit_result(Path(args.spec), Path(args.result))
            _emit(value)
            return 0
        if args.command == "verdict":
            value = verdict_frozen(args.manifest, args.receipt, args.replay)
            _emit(value)
            return 1 if value["state"] == "INTEGRITY_FAIL" else 0
    except Exception as exc:  # CLI fail-closed boundary
        _emit({"error": type(exc).__name__, "message": str(exc), "pass": False})
        return 2
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
