from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from typing import Any, Callable

from experiments.sem1.build_sem1_instrument import LABELS, build_dataset
from experiments.sem1.validate_sem1_instrument import canonical_sha


def norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def toks(text: str) -> list[str]:
    return re.findall(r"[a-z]+|[0-9]+", text.lower())


def _case_gold(meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return meta["gold"]


def macro_f1(gold: list[str], pred: list[str]) -> tuple[float, dict[str, float]]:
    per: dict[str, float] = {}
    for label in LABELS:
        tp = sum(g == label and p == label for g, p in zip(gold, pred))
        fp = sum(g != label and p == label for g, p in zip(gold, pred))
        fn = sum(g == label and p != label for g, p in zip(gold, pred))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        per[label] = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return sum(per.values()) / len(LABELS), per


def summarize(ys: list[str], ps: list[str]) -> dict[str, Any]:
    mf1, per = macro_f1(ys, ps)
    return {
        "n": len(ys),
        "accuracy": sum(a == b for a, b in zip(ys, ps)) / len(ys),
        "macro_f1": mf1,
        "per_label_f1": per,
        "prediction_counts": dict(Counter(ps)),
    }


def evaluate_strategy(strategy: Callable[[dict[str, Any]], dict[str, str]]) -> dict[str, Any]:
    cases, golds = build_dataset()
    gold_by = {g["id"]: g for g in golds}
    ys: list[str] = []
    ps: list[str] = []
    for case in cases:
        pred = strategy(case)
        gold = _case_gold(gold_by[case["id"]])
        if set(pred) != {p["id"] for p in case["propositions"]}:
            raise AssertionError("baseline prediction shape mismatch")
        for prop in case["propositions"]:
            pid = prop["id"]
            ys.append(gold[pid]["label"])
            ps.append(pred[pid])
    return summarize(ys, ps)


def constant(label: str) -> Callable[[dict[str, Any]], dict[str, str]]:
    return lambda case: {p["id"]: label for p in case["propositions"]}


def exact_overlap(case: dict[str, Any]) -> dict[str, str]:
    ctx = {norm(x["text"]) for x in case["context"]}
    return {
        p["id"]: ("ASSERTED" if norm(p["text"]) in ctx else "UNKNOWN")
        for p in case["propositions"]
    }


def opaque_hash(case: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in case["propositions"]:
        idx = int(hashlib.sha256(p["id"].encode()).hexdigest()[:8], 16) % len(LABELS)
        out[p["id"]] = LABELS[idx]
    return out


def presentation_cycle(case: dict[str, Any]) -> dict[str, str]:
    return {p["id"]: LABELS[i % len(LABELS)] for i, p in enumerate(case["propositions"])}


def _ngrams(words: list[str]) -> list[str]:
    out = list(words)
    out.extend(f"{a}_{b}" for a, b in zip(words, words[1:]))
    return out


def features(case: dict[str, Any], prop: dict[str, str], *, with_context: bool) -> Counter[str]:
    feats: Counter[str] = Counter()
    pt = toks(prop["text"])
    for token in _ngrams(pt):
        feats["p:" + token] += 1
    feats[f"p_len:{min(len(pt), 24)}"] += 1
    feats[f"p_neg:{int(any(x in {'not','no','never'} for x in pt))}"] += 1
    feats[f"p_num:{int(any(x.isdigit() or x in {'one','two','three','four','five','six','seven'} for x in pt))}"] += 1

    if with_context:
        ctext = " ".join(x["text"] for x in case["context"])
        ct = toks(ctext)
        for token in _ngrams(ct):
            feats["c:" + token] += 1
        pset, cset = set(pt), set(ct)
        for token in pset & cset:
            feats["both:" + token] += 1
        feats[f"c_len:{min(len(ct) // 4, 32)}"] += 1
        feats[f"overlap:{min(len(pset & cset), 16)}"] += 1
        feats[f"exact_overlap:{int(norm(prop['text']) in {norm(x['text']) for x in case['context']})}"] += 1
    return feats


def held_out_nb(*, with_context: bool) -> dict[str, Any]:
    """Leave one controlled pair out; features use only model-visible text."""
    cases, golds = build_dataset()
    meta_by = {g["id"]: g for g in golds}
    pairs = sorted({g["pair_id"] for g in golds})
    ys: list[str] = []
    ps: list[str] = []

    for held in pairs:
        class_docs = Counter()
        feat_counts: dict[str, Counter[str]] = {label: Counter() for label in LABELS}
        totals = Counter()
        vocab: set[str] = set()

        for case in cases:
            meta = meta_by[case["id"]]
            if meta["pair_id"] == held:
                continue
            gold = meta["gold"]
            for prop in case["propositions"]:
                label = gold[prop["id"]]["label"]
                f = features(case, prop, with_context=with_context)
                class_docs[label] += 1
                feat_counts[label].update(f)
                totals[label] += sum(f.values())
                vocab.update(f)

        n_docs = sum(class_docs.values())
        v = max(len(vocab), 1)
        for case in cases:
            meta = meta_by[case["id"]]
            if meta["pair_id"] != held:
                continue
            gold = meta["gold"]
            for prop in case["propositions"]:
                f = features(case, prop, with_context=with_context)
                scores: dict[str, float] = {}
                for label in LABELS:
                    prior = (class_docs[label] + 1) / (n_docs + len(LABELS))
                    score = math.log(prior)
                    denom = totals[label] + v
                    for feat, count in f.items():
                        score += count * math.log((feat_counts[label][feat] + 1) / denom)
                    scores[label] = score
                pred = max(LABELS, key=lambda label: (scores[label], -LABELS.index(label)))
                ys.append(gold[prop["id"]]["label"])
                ps.append(pred)

    result = summarize(ys, ps)
    result["folds"] = len(pairs)
    result["split"] = "leave_one_pair_out"
    result["features"] = "proposition_only" if not with_context else "model_visible_context_plus_proposition"
    return result


def symbolic_surface(case: dict[str, Any]) -> dict[str, str]:
    """Hostile transparent rules using visible wording only, never hidden metadata."""
    ctx_texts = [x["text"] for x in case["context"]]
    ctx_norm = [norm(x) for x in ctx_texts]
    joined = " || ".join(ctx_norm)
    out: dict[str, str] = {}

    for p in case["propositions"]:
        raw = p["text"]
        pn = norm(raw)
        label = "UNKNOWN"

        if pn in ctx_norm:
            label = "ASSERTED"
        elif "discovered that" in joined and any(pn == x.split("discovered that ", 1)[1] for x in ctx_norm if "discovered that " in x):
            label = "PRESUPPOSED"
        elif "did not discover that" in joined and any(pn == x.split("did not discover that ", 1)[1] for x in ctx_norm if "did not discover that " in x):
            label = "PRESUPPOSED"
        elif pn.startswith("not all") and "some of the six" in joined and "all six" not in joined:
            label = "IMPLICATED"
        elif pn.startswith("not all") and "all six" in joined:
            label = "CONTRADICTED"
        elif pn.startswith("no ") and any(q in joined for q in ("some of", "exactly", "all ", "every ")):
            label = "CONTRADICTED"
        elif pn.startswith("at least one") and any(q in joined for q in ("some of", "exactly", "all ", "every ")):
            label = "ENTAILED"
        elif pn.startswith("at least four") and "exactly four" in joined:
            label = "ENTAILED"
        elif pn.startswith("at least four") and "exactly three" in joined:
            label = "CONTRADICTED"
        elif pn.startswith("not all seven") and ("exactly four" in joined or "exactly three" in joined or "four and only four" in joined):
            label = "ENTAILED"
        elif "occurred before" in pn and "occurred on day" in joined:
            nums = [int(x) for x in re.findall(r"occurred on day ([0-9]+)", joined)]
            if len(nums) >= 2:
                label = "ENTAILED" if min(nums) < max(nums) else "UNKNOWN"
        elif "occurred after" in pn and "occurred on day" in joined:
            nums = [int(x) for x in re.findall(r"occurred on day ([0-9]+)", joined)]
            if len(nums) >= 2:
                label = "ENTAILED" if max(nums) > min(nums) else "UNKNOWN"
        elif "happened on the same day" in pn and len(set(re.findall(r"occurred on day ([0-9]+)", joined))) >= 2:
            label = "CONTRADICTED"
        elif "is copper" in pn and "means both copper and smooth" in joined:
            label = "ENTAILED"
        elif "is smooth" in pn and any(x in joined for x in ("copper and smooth", "glass and smooth", "both smooth and copper")):
            label = "ENTAILED"
        elif "is glass" in pn and "means both glass and smooth" in joined:
            label = "ENTAILED"
        elif "contains cobalt" in pn and "only objects containing cobalt emit a low hum" in joined and "emits a low hum" in joined:
            label = "ENTAILED"
        elif "contains cobalt" in pn and "if an object contains cobalt" in joined and "emits a low hum" in joined:
            label = "UNKNOWN"
        elif "every humming object contains cobalt" in pn and "only objects containing cobalt emit a low hum" in joined:
            label = "ENTAILED"
        elif "is conductive" in pn and "every silver" in joined and "is a silver" in joined and "except" not in joined:
            label = "ENTAILED"
        elif "is not conductive" in pn and "not conductive" in joined:
            label = "ASSERTED"
        elif "is not conductive" in pn and "every silver" in joined and "is a silver" in joined and "except" not in joined:
            label = "CONTRADICTED"
        elif "in the quotation i refers to" in pn and "speaker" in joined:
            target = pn.rsplit(" ", 1)[-1]
            label = "ENTAILED" if target in joined and f"speaker is {target}" in joined else "CONTRADICTED"

        out[p["id"]] = label
    return out


def build_report() -> dict[str, Any]:
    constants = {f"always_{label}": evaluate_strategy(constant(label)) for label in LABELS}
    controls = {
        "exact_overlap": evaluate_strategy(exact_overlap),
        "opaque_id_hash": evaluate_strategy(opaque_hash),
        "presentation_cycle": evaluate_strategy(presentation_cycle),
    }
    learned = {
        "proposition_only_pair_heldout_nb": held_out_nb(with_context=False),
        "context_plus_proposition_pair_heldout_nb": held_out_nb(with_context=True),
    }
    symbolic = {"symbolic_surface_rules": evaluate_strategy(symbolic_surface)}

    margin_eligible = {**constants, **controls, **learned}
    best_name, best_row = max(margin_eligible.items(), key=lambda kv: kv[1]["macro_f1"])
    strongest = float(best_row["macro_f1"])
    effective_floor = max(0.72, strongest + 0.15)

    shortcut_gates = {
        "proposition_only_below_0_50": learned["proposition_only_pair_heldout_nb"]["macro_f1"] < 0.50,
        "context_plus_proposition_below_0_65": learned["context_plus_proposition_pair_heldout_nb"]["macro_f1"] < 0.65,
        "opaque_hash_below_0_35": controls["opaque_id_hash"]["macro_f1"] < 0.35,
        "presentation_cycle_below_0_35": controls["presentation_cycle"]["macro_f1"] < 0.35,
        "symbolic_surface_below_0_80": symbolic["symbolic_surface_rules"]["macro_f1"] < 0.80,
    }

    cases, gold = build_dataset()
    report: dict[str, Any] = {
        "schema_version": 1,
        "unit": "SEM-1",
        "status": "SEM1_SHORTCUT_AUDIT_PASS" if all(shortcut_gates.values()) else "SEM1_SHORTCUT_AUDIT_FAIL",
        "scientific_model_calls": 0,
        "candidate_execution": False,
        "bindings": {
            "cases_record_sha256": canonical_sha(cases),
            "gold_record_sha256": canonical_sha(gold),
        },
        "constant_baselines": constants,
        "controls": controls,
        "learned_pair_heldout": learned,
        "symbolic_red_team": symbolic,
        "shortcut_gates": shortcut_gates,
        "strongest_margin_eligible": {
            "name": best_name,
            "macro_f1": strongest,
        },
        "effective_candidate_macro_f1_floor": effective_floor,
    }
    record = dict(report)
    report["record_sha256"] = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return report


def main() -> None:
    print(json.dumps(build_report(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
