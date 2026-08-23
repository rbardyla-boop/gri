from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

LABELS = ["ASSERTED", "ENTAILED", "PRESUPPOSED", "IMPLICATED", "CONTRADICTED", "UNKNOWN"]
NONCE_FAMILIES = {"nonce_grounding", "deixis_reference", "invented_lexicon"}

GATES = {
    "overall_accuracy_min": 0.80,
    "macro_f1_min": 0.78,
    "pair_focus_exact_min": 0.80,
    "revision_pair_exact_min": 0.80,
    "invariance_pair_exact_min": 0.75,
    "unknown_overclaim_max": 0.15,
    "evidence_micro_f1_min": 0.70,
    "nonce_family_accuracy_min": 0.78,
    "scalar_cancellation_exact_min": 0.75,
    "presupposition_projection_exact_min": 0.75,
    "surface_baseline_macro_f1_margin_min": 0.20,
}

def load_jsonl(path: Path) -> list[dict[str, Any]]:
    out = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return out

def normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())

def f1_by_label(gold: list[str], pred: list[str]) -> dict[str, float]:
    out = {}
    for label in LABELS:
        tp = sum(g == label and p == label for g, p in zip(gold, pred))
        fp = sum(g != label and p == label for g, p in zip(gold, pred))
        fn = sum(g == label and p != label for g, p in zip(gold, pred))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        out[label] = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return out

def exact_or_unknown_baseline(cases: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    pred = {}
    for case in cases:
        ctx = {normalize(s["text"]) for s in case["context"]}
        for prop in case["propositions"]:
            pred[(case["id"], prop["id"])] = "ASSERTED" if normalize(prop["text"]) in ctx else "UNKNOWN"
    return pred

def _prediction_map(predictions: list[dict[str, Any]], cases: list[dict[str, Any]]) -> tuple[dict[tuple[str, str], dict[str, Any]], list[str]]:
    expected_case_ids = {c["id"] for c in cases}
    seen_case_ids = [p.get("id") for p in predictions]
    errors = []
    if len(seen_case_ids) != len(set(seen_case_ids)):
        errors.append("duplicate_case_id")
    extra = sorted(set(seen_case_ids) - expected_case_ids)
    missing = sorted(expected_case_ids - set(seen_case_ids))
    if extra:
        errors.append(f"extra_cases:{','.join(extra)}")
    if missing:
        errors.append(f"missing_cases:{','.join(missing)}")
    pmap = {}
    cases_by_id = {c["id"]: c for c in cases}
    for pred in predictions:
        cid = pred.get("id")
        if cid not in cases_by_id:
            continue
        expected_props = {p["id"] for p in cases_by_id[cid]["propositions"]}
        answers = pred.get("answers")
        if not isinstance(answers, list):
            errors.append(f"{cid}:answers_not_list")
            continue
        seen_props = [a.get("id") for a in answers if isinstance(a, dict)]
        if len(seen_props) != len(set(seen_props)):
            errors.append(f"{cid}:duplicate_proposition_id")
        if set(seen_props) != expected_props:
            errors.append(f"{cid}:proposition_set_mismatch")
        for answer in answers:
            if not isinstance(answer, dict):
                continue
            pid = answer.get("id")
            label = answer.get("label")
            evidence = answer.get("evidence", [])
            if label not in LABELS:
                errors.append(f"{cid}/{pid}:invalid_label")
            if not isinstance(evidence, list) or any(not isinstance(x, str) for x in evidence):
                errors.append(f"{cid}/{pid}:invalid_evidence")
                evidence = []
            pmap[(cid, pid)] = {"label": label, "evidence": sorted(set(evidence))}
    return pmap, errors

def replay_semantic_agreement(
    live_predictions: list[dict[str, Any]],
    replay_predictions: list[dict[str, Any]],
    replay_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    live_by_case = {x.get("id"): x for x in live_predictions}
    replay_by_case = {x.get("id"): x for x in replay_predictions}
    expected_ids = {c["id"] for c in replay_cases}
    errors = []
    if set(replay_by_case) != expected_ids:
        errors.append("replay_case_set_mismatch")
    if not expected_ids.issubset(set(live_by_case)):
        errors.append("live_missing_replay_cases")
    agree = 0
    total = 0
    for case in replay_cases:
        cid = case["id"]
        live_answers = {
            a.get("id"): (a.get("label"), tuple(sorted(set(a.get("evidence", [])))))
            for a in live_by_case.get(cid, {}).get("answers", [])
            if isinstance(a, dict)
        }
        replay_answers = {
            a.get("id"): (a.get("label"), tuple(sorted(set(a.get("evidence", [])))))
            for a in replay_by_case.get(cid, {}).get("answers", [])
            if isinstance(a, dict)
        }
        for prop in case["propositions"]:
            pid = prop["id"]
            total += 1
            if live_answers.get(pid) == replay_answers.get(pid) and live_answers.get(pid) is not None:
                agree += 1
    return {"agreement": agree / total if total else 0.0, "agree": agree, "total": total, "errors": errors, "pass": not errors and agree == total}

def score(cases_path: Path, gold_path: Path, predictions_path: Path, replay_cases_path: Path | None = None, replay_predictions_path: Path | None = None) -> dict[str, Any]:
    cases = load_jsonl(cases_path)
    gold_rows = load_jsonl(gold_path)
    predictions = load_jsonl(predictions_path)
    replay_result = None
    if replay_cases_path is not None and replay_predictions_path is not None:
        replay_cases = load_jsonl(replay_cases_path)
        replay_predictions = load_jsonl(replay_predictions_path)
        replay_result = replay_semantic_agreement(predictions, replay_predictions, replay_cases)

    if len(cases) != len(gold_rows):
        raise ValueError("case/gold count mismatch")
    case_by_id = {c["id"]: c for c in cases}
    gold_by_id = {g["id"]: g for g in gold_rows}
    if set(case_by_id) != set(gold_by_id):
        raise ValueError("case/gold ids mismatch")

    pmap, format_errors = _prediction_map(predictions, cases)
    gold_labels = []
    pred_labels = []
    family_correct = Counter()
    family_total = Counter()
    label_correct = Counter()
    label_total = Counter()
    evidence_tp = evidence_fp = evidence_fn = 0
    evidence_exact = evidence_total = 0
    unknown_total = unknown_overclaim = 0
    decision_correct = {}

    for cid in sorted(case_by_id):
        gold_row = gold_by_id[cid]
        family = gold_row["family"]
        for pid, g in gold_row["gold"].items():
            pred = pmap.get((cid, pid), {"label": None, "evidence": []})
            gl = g["label"]
            pl = pred["label"]
            gold_labels.append(gl)
            pred_labels.append(pl if pl in LABELS else "__INVALID__")
            label_total[gl] += 1
            family_total[family] += 1
            ok = pl == gl
            decision_correct[(cid, pid)] = ok
            if ok:
                label_correct[gl] += 1
                family_correct[family] += 1
            if gl == "UNKNOWN":
                unknown_total += 1
                if pl != "UNKNOWN":
                    unknown_overclaim += 1
            ge = set(g.get("evidence", []))
            pe = set(pred.get("evidence", []))
            evidence_tp += len(ge & pe)
            evidence_fp += len(pe - ge)
            evidence_fn += len(ge - pe)
            evidence_exact += int(ge == pe)
            evidence_total += 1

    valid_pred_labels = [p if p in LABELS else "UNKNOWN" for p in pred_labels]
    f1s = f1_by_label(gold_labels, valid_pred_labels)
    accuracy = sum(g == p for g, p in zip(gold_labels, pred_labels)) / len(gold_labels)
    macro_f1 = sum(f1s.values()) / len(LABELS)
    ep = evidence_tp / (evidence_tp + evidence_fp) if evidence_tp + evidence_fp else 0.0
    er = evidence_tp / (evidence_tp + evidence_fn) if evidence_tp + evidence_fn else 0.0
    evidence_micro_f1 = 2 * ep * er / (ep + er) if ep + er else 0.0

    pairs = defaultdict(list)
    for g in gold_rows:
        pairs[g["pair_id"]].append(g)
    pair_focus_exact = []
    revision_exact = []
    invariance_exact = []
    scalar_exact = []
    presup_exact = []
    context_rev_exact = []
    for pair_id, rows in sorted(pairs.items()):
        if len(rows) != 2:
            raise ValueError(f"pair {pair_id} does not have exactly two variants")
        focus_items = []
        for row in rows:
            pid = row["focus_proposition"]
            focus_items.append((row["id"], pid, row["gold"][pid]["label"], row["family"]))
        both = all(decision_correct[(cid, pid)] for cid, pid, _, _ in focus_items)
        pair_focus_exact.append(both)
        labels = [x[2] for x in focus_items]
        family = focus_items[0][3]
        if labels[0] == labels[1]:
            invariance_exact.append(both)
        else:
            revision_exact.append(both)
        if family == "scalar_implicature":
            scalar_exact.append(both)
        if family == "presupposition_projection":
            presup_exact.append(both)
        if family in {"context_reversal", "nonce_grounding", "deixis_reference", "invented_lexicon", "negation_quantifier"}:
            context_rev_exact.append(both)

    nonce_correct = sum(family_correct[f] for f in NONCE_FAMILIES)
    nonce_total = sum(family_total[f] for f in NONCE_FAMILIES)
    nonce_accuracy = nonce_correct / nonce_total if nonce_total else 0.0

    base_map = exact_or_unknown_baseline(cases)
    base_gold = []
    base_pred = []
    for cid in sorted(case_by_id):
        for pid, g in gold_by_id[cid]["gold"].items():
            base_gold.append(g["label"])
            base_pred.append(base_map[(cid, pid)])
    base_f1s = f1_by_label(base_gold, base_pred)
    base_macro_f1 = sum(base_f1s.values()) / len(LABELS)
    base_accuracy = sum(g == p for g, p in zip(base_gold, base_pred)) / len(base_gold)

    metrics = {
        "decision_count": len(gold_labels),
        "case_count": len(cases),
        "format_error_count": len(format_errors),
        "format_errors": format_errors,
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "per_label_f1": f1s,
        "per_label_accuracy": {l: label_correct[l] / label_total[l] for l in LABELS},
        "per_family_accuracy": {f: family_correct[f] / family_total[f] for f in sorted(family_total)},
        "evidence_exact_accuracy": evidence_exact / evidence_total,
        "evidence_micro_f1": evidence_micro_f1,
        "unknown_overclaim_rate": unknown_overclaim / unknown_total if unknown_total else 0.0,
        "pair_focus_exact_rate": sum(pair_focus_exact) / len(pair_focus_exact),
        "revision_pair_exact_rate": sum(revision_exact) / len(revision_exact) if revision_exact else 0.0,
        "invariance_pair_exact_rate": sum(invariance_exact) / len(invariance_exact) if invariance_exact else 0.0,
        "scalar_cancellation_exact_rate": sum(scalar_exact) / len(scalar_exact) if scalar_exact else 0.0,
        "presupposition_projection_exact_rate": sum(presup_exact) / len(presup_exact) if presup_exact else 0.0,
        "context_reversal_exact_rate": sum(context_rev_exact) / len(context_rev_exact) if context_rev_exact else 0.0,
        "nonce_family_accuracy": nonce_accuracy,
        "surface_baseline": {"accuracy": base_accuracy, "macro_f1": base_macro_f1, "per_label_f1": base_f1s},
        "surface_baseline_macro_f1_margin": macro_f1 - base_macro_f1,
        "replay": replay_result,
    }

    gates = {
        "format_integrity": len(format_errors) == 0,
        "overall_accuracy": accuracy >= GATES["overall_accuracy_min"],
        "macro_f1": macro_f1 >= GATES["macro_f1_min"],
        "pair_focus_exact": metrics["pair_focus_exact_rate"] >= GATES["pair_focus_exact_min"],
        "revision_pair_exact": metrics["revision_pair_exact_rate"] >= GATES["revision_pair_exact_min"],
        "invariance_pair_exact": metrics["invariance_pair_exact_rate"] >= GATES["invariance_pair_exact_min"],
        "unknown_restraint": metrics["unknown_overclaim_rate"] <= GATES["unknown_overclaim_max"],
        "evidence_dependency": evidence_micro_f1 >= GATES["evidence_micro_f1_min"],
        "nonce_transfer": nonce_accuracy >= GATES["nonce_family_accuracy_min"],
        "scalar_cancellation": metrics["scalar_cancellation_exact_rate"] >= GATES["scalar_cancellation_exact_min"],
        "presupposition_projection": metrics["presupposition_projection_exact_rate"] >= GATES["presupposition_projection_exact_min"],
        "surface_margin": metrics["surface_baseline_macro_f1_margin"] >= GATES["surface_baseline_macro_f1_margin_min"],
        "semantic_replay": bool(replay_result and replay_result["pass"]),
    }
    all_pass = all(gates.values())
    return {
        "experiment": "SEM-0",
        "claim": "frozen system demonstrates structured meaning-relation competence under adversarial context perturbations",
        "gates": gates,
        "metrics": metrics,
        "thresholds": GATES,
        "verdict": "SEM_0_MEANING_RELATION_COMPETENCE" if all_pass else "SEM_0_NOT_ESTABLISHED",
        "boundary": {
            "consciousness": "NOT_TESTED",
            "phenomenology": "NOT_TESTED",
            "speaker_intent": "NOT_TESTED",
            "sarcasm": "NOT_TESTED",
            "general_language_understanding": "NOT_ESTABLISHED",
            "training_effect": "NOT_TESTED",
        },
    }

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--predictions", type=Path, required=True)
    ap.add_argument("--replay-cases", type=Path)
    ap.add_argument("--replay-predictions", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    if (args.replay_cases is None) != (args.replay_predictions is None):
        raise SystemExit("--replay-cases and --replay-predictions must be supplied together")
    result = score(args.cases, args.gold, args.predictions, args.replay_cases, args.replay_predictions)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")

if __name__ == "__main__":
    main()
