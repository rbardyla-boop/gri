from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from experiments.sem1 import generate_sem1 as base

LABELS = base.LABELS
FAMILIES = base.FAMILIES
write_jsonl = base.write_jsonl

# The auditable family builders use human-readable nonce prefixes so their
# semantics are easy to inspect. Those prefixes must not reach the candidate:
# they identify the family and therefore form an unintended surface shortcut.
_FAMILY_NONCE = re.compile(
    r"\b(?:VEX|RAV|ZEL|NORI|TAL|DAX|EVR|EVS|NER|LUM|TOR|MURK|OBJ|KAV)\d{2}Q\b"
)


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


def _neutralize_family_nonces(cases: list[dict[str, Any]], gold: list[dict[str, Any]]) -> None:
    """Remove family identity encoded in synthetic nonce spelling.

    Replacement is pair-local and consistent across A/B variants. The operation
    changes only visible nonce names; labels, evidence IDs, pair relations and
    all hidden experimental metadata remain unchanged.
    """
    case_by_id = {case["id"]: case for case in cases}
    pair_case_ids: dict[str, list[str]] = defaultdict(list)
    for meta in gold:
        pair_case_ids[meta["pair_id"]].append(meta["id"])

    for pair_id, case_ids in pair_case_ids.items():
        if len(case_ids) != 2:
            raise AssertionError((pair_id, case_ids))
        visible_text: list[str] = []
        for cid in case_ids:
            case = case_by_id[cid]
            visible_text.extend(x["text"] for x in case["context"])
            visible_text.extend(x["text"] for x in case["propositions"])
        raw_tokens = sorted({m.group(0) for text in visible_text for m in _FAMILY_NONCE.finditer(text)})
        mapping = {token: f"QX{idx + 1}" for idx, token in enumerate(raw_tokens)}

        def replace(text: str) -> str:
            return _FAMILY_NONCE.sub(lambda m: mapping[m.group(0)], text)

        for cid in case_ids:
            case = case_by_id[cid]
            for item in case["context"]:
                item["text"] = replace(item["text"])
            for item in case["propositions"]:
                item["text"] = replace(item["text"])

    leftovers = [
        (case["id"], item["text"])
        for case in cases
        for section in ("context", "propositions")
        for item in case[section]
        if _FAMILY_NONCE.search(item["text"])
    ]
    if leftovers:
        raise AssertionError(("family nonce leakage", leftovers[:5]))


def build_dataset() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the final pre-science SEM-1 candidate instrument.

    The base family builders intentionally make the semantic pair logic easy to
    audit. This deterministic finalization pass first changes only non-focus
    distractors in two families to prevent a repeated label-cardinality pattern
    from becoming an instrument-level shortcut. It then removes family-coded
    nonce spellings from all model-visible text. Focus proposition IDs, pair
    kinds, labels, evidence bindings, and family semantics are unchanged by the
    nonce-neutralization step.
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

    _neutralize_family_nonces(cases, gold)
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
    report["family_nonce_prefix_neutralization"] = True
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
