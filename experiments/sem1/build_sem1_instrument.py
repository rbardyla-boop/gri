from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from experiments.sem1 import generate_sem1 as base

LABELS = base.LABELS
FAMILIES = base.FAMILIES
write_jsonl = base.write_jsonl


def _replace_proposition(
    case: dict[str, Any],
    meta: dict[str, Any],
    *,
    match_text: str,
    replacement_text: str,
    label: str,
    evidence: list[str],
) -> None:
    hits = [p for p in case["propositions"] if match_text in p["text"]]
    if len(hits) != 1:
        raise AssertionError((case["id"], match_text, len(hits)))
    pid = hits[0]["id"]
    hits[0]["text"] = replacement_text
    meta["gold"][pid] = {"label": label, "evidence": evidence}


def build_dataset() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the final pre-science SEM-1 candidate instrument.

    The base family builders intentionally make the semantic pair logic easy to
    audit. This deterministic finalization pass changes only non-focus
    distractors in two families to prevent a repeated label-cardinality pattern
    from becoming an instrument-level shortcut. Focus propositions, pair kinds,
    and family semantics are unchanged.
    """
    raw_cases, raw_gold = base.build_dataset()
    cases = deepcopy(raw_cases)
    gold = deepcopy(raw_gold)

    for case, meta in zip(cases, gold):
        if meta["family"] == "nonce_temporal" and meta["pair_kind"] == "INVARIANCE":
            asserted_texts = {
                p["text"]
                for p in case["propositions"]
                if meta["gold"][p["id"]]["label"] == "ASSERTED"
            }
            date_contexts = [s for s in case["context"] if " occurred on day " in s["text"]]
            unused = [s for s in date_contexts if s["text"] not in asserted_texts]
            if len(unused) != 1:
                raise AssertionError((case["id"], "temporal unused asserted date", len(unused)))
            chosen = unused[0]
            _replace_proposition(
                case,
                meta,
                match_text=" happened on the same day.",
                replacement_text=chosen["text"],
                label="ASSERTED",
                evidence=[chosen["id"]],
            )

        if (
            meta["family"] == "abductive_restraint"
            and meta["pair_kind"] == "REVISION"
            and meta["variant"] == "B"
        ):
            source = [s for s in case["context"] if s["text"] == "Only objects containing cobalt emit a low hum."]
            if len(source) != 1:
                raise AssertionError((case["id"], "abductive necessity statement", len(source)))
            _replace_proposition(
                case,
                meta,
                match_text="No cobalt object emits a low hum.",
                replacement_text=source[0]["text"],
                label="ASSERTED",
                evidence=[source[0]["id"]],
            )

    return cases, gold


def dataset_summary(gold: list[dict[str, Any]]) -> dict[str, Any]:
    return base.dataset_summary(gold)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the final fresh SEM-1 pre-science instrument candidate.")
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True)
    args = ap.parse_args()
    cases, gold = build_dataset()
    write_jsonl(args.cases, cases)
    write_jsonl(args.gold, gold)
    report = dataset_summary(gold)
    report["status"] = "SEM1_INSTRUMENT_CANDIDATE_BUILT"
    report["base_family_generator"] = "generate_sem1.py"
    report["pattern_diversity_finalization"] = True
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
