from __future__ import annotations

import argparse
import hashlib
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


def _find_prop(case: dict[str, Any], text: str) -> dict[str, str]:
    hits = [p for p in case["propositions"] if p["text"] == text]
    if len(hits) != 1:
        raise AssertionError((case["id"], text, len(hits)))
    return hits[0]


def _new_statement_id(case_id: str, tag: str) -> str:
    return "S_" + hashlib.sha256(f"SEM1-CB:{case_id}:{tag}".encode()).hexdigest()[:12].upper()


def _append_counterfact(
    case: dict[str, Any],
    meta: dict[str, Any],
    *,
    proposition_text: str,
    context_text: str,
    label: str,
    tag: str,
) -> None:
    if label not in {"ASSERTED", "CONTRADICTED"}:
        raise ValueError(label)
    prop = _find_prop(case, proposition_text)
    sid = _new_statement_id(case["id"], tag)
    existing_ids = {x["id"] for x in case["context"]}
    if sid in existing_ids:
        raise AssertionError((case["id"], sid))
    case["context"].append({"id": sid, "text": context_text})
    meta["gold"][prop["id"]] = {"label": label, "evidence": [sid]}


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


def _counterbalance_scalar_invariance(case: dict[str, Any], meta: dict[str, Any], pair_index: int) -> None:
    if pair_index not in {4, 5}:
        return
    total_context = [
        s for s in case["context"]
        if "exact total" in s["text"].lower() or "exact total is stated" in s["text"].lower()
    ]
    if len(total_context) != 1:
        raise AssertionError((case["id"], "scalar total context", [x["text"] for x in case["context"]]))
    sid = total_context[0]["id"]
    if pair_index == 4:
        total_context[0]["text"] = "Exactly three of the six QX1 trials stabilized."
        focus_label = "ENTAILED"
    else:
        total_context[0]["text"] = "All six QX1 trials stabilized."
        focus_label = "CONTRADICTED"

    focus = _find_prop(case, "Not all six QX1 trials stabilized.")
    meta["gold"][focus["id"]] = {"label": focus_label, "evidence": [sid]}

    for prop in case["propositions"]:
        text = prop["text"]
        if "record states the exact number" in text.lower():
            meta["gold"][prop["id"]] = {"label": "ENTAILED", "evidence": [sid]}
        elif text == "Exactly three of the six QX1 trials stabilized.":
            meta["gold"][prop["id"]] = {
                "label": "ASSERTED" if pair_index == 4 else "CONTRADICTED",
                "evidence": [sid],
            }
        elif text == "Exactly four of the six QX1 trials stabilized.":
            meta["gold"][prop["id"]] = {"label": "CONTRADICTED", "evidence": [sid]}
        elif text == "All six QX1 trials stabilized.":
            meta["gold"][prop["id"]] = {
                "label": "ASSERTED" if pair_index == 5 else "CONTRADICTED",
                "evidence": [sid],
            }
        elif text == "No QX1 trial stabilized.":
            meta["gold"][prop["id"]] = {"label": "CONTRADICTED", "evidence": [sid]}


def _counterbalance_invariance_distractors(cases: list[dict[str, Any]], gold: list[dict[str, Any]]) -> None:
    """Make repeated distractor form context-dependent by construction.

    In each family, invariant pair index 3 retains an UNKNOWN distractor. Pair 4
    adds a positive fact making the same proposition ASSERTED. Pair 5 adds an
    explicit negative fact making it CONTRADICTED. This is a semantic
    counterbalance: proposition wording alone no longer determines its label.
    The added fact is identical in role across A/B, preserving invariance.
    """
    case_by_id = {case["id"]: case for case in cases}
    specs = {
        "factive_presupposition": (
            "QX2 cracked permanently.",
            "QX2 cracked permanently.",
            "QX2 did not crack permanently.",
        ),
        "exception_scope": (
            "QX2 is heavy.",
            "QX2 is heavy.",
            "QX2 is not heavy.",
        ),
        "nonce_temporal": (
            "QX3 was caused by QX2.",
            "QX3 was caused by QX2.",
            "QX3 was not caused by QX2.",
        ),
        "deixis_reference": (
            "The marker is blue.",
            "The marker is blue.",
            "The marker is not blue.",
        ),
        "negation_quantifier": (
            "The seventh QX1 lamp is lit.",
            "The seventh QX1 lamp is lit.",
            "The seventh QX1 lamp is not lit.",
        ),
        "invented_lexicon": (
            "QX2 is glass.",
            "QX2 is glass.",
            "QX2 is not glass.",
        ),
        "abductive_restraint": (
            "QX1 contains iron.",
            "QX1 contains iron.",
            "QX1 does not contain iron.",
        ),
    }

    for meta in gold:
        if meta["pair_kind"] != "INVARIANCE":
            continue
        pair_index = int(meta["pair_id"].rsplit("-", 1)[1])
        case = case_by_id[meta["id"]]
        if meta["family"] == "scalar_scope":
            _counterbalance_scalar_invariance(case, meta, pair_index)
            continue
        if meta["family"] not in specs or pair_index not in {4, 5}:
            continue
        proposition, positive, negative = specs[meta["family"]]
        if pair_index == 4:
            _append_counterfact(
                case,
                meta,
                proposition_text=proposition,
                context_text=positive,
                label="ASSERTED",
                tag="positive-counterbalance",
            )
        else:
            _append_counterfact(
                case,
                meta,
                proposition_text=proposition,
                context_text=negative,
                label="CONTRADICTED",
                tag="negative-counterbalance",
            )


def build_dataset() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the current pre-science SEM-1 candidate instrument.

    The base family builders intentionally make the pair logic easy to audit.
    This deterministic finalization layer removes known construction shortcuts:
    label-cardinality repetition, family-coded nonce spelling, and fixed-label
    invariant distractors. The latter are counterbalanced through added context,
    not through arbitrary relabeling: the same proposition becomes UNKNOWN,
    ASSERTED, or CONTRADICTED according to what its paired world actually says.
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
    _counterbalance_invariance_distractors(cases, gold)
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
    report["invariance_distractor_counterbalancing"] = True
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
