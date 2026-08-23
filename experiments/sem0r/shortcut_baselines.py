from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Callable

from generate_sem0r import build_dataset
from sem0r_contract import LABELS, model_view


def norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def tokens(text: str) -> set[str]:
    return set(norm(text).split())


def all_unknown(case: dict[str, Any]) -> dict[str, str]:
    return {p["id"]: "UNKNOWN" for p in model_view(case)["propositions"]}


def exact_overlap(case: dict[str, Any]) -> dict[str, str]:
    view = model_view(case)
    ctx = [norm(s["text"]) for s in view["context"]]
    out: dict[str, str] = {}
    for p in view["propositions"]:
        pn = norm(p["text"])
        out[p["id"]] = "ASSERTED" if pn in ctx else "UNKNOWN"
    return out


def surface_rules(case: dict[str, Any]) -> dict[str, str]:
    """Transparent hand rules using only the model-visible text; no family/renderer metadata."""
    view = model_view(case)
    statements = [s["text"] for s in view["context"]]
    cn = norm(" || ".join(statements))
    ctx_norm = [norm(s) for s in statements]
    cleaned_ctx = [re.sub(r"^(in fact|the report says|the log says)\s+", "", x) for x in ctx_norm]
    factive_complements: set[str] = set()
    for st in ctx_norm:
        m = re.search(r"(?:did not )?realize(?:d)? that (.+)$", st)
        if m:
            factive_complements.add(m.group(1))
    out: dict[str, str] = {}
    for p in view["propositions"]:
        text = p["text"]
        pn = norm(text)
        label = "UNKNOWN"
        if pn in ctx_norm or pn in cleaned_ctx:
            label = "ASSERTED"
        elif pn in factive_complements:
            label = "PRESUPPOSED"
        elif pn.startswith("not all") and ("some" in cn) and "in fact all" not in cn:
            label = "IMPLICATED"
        elif pn.startswith("not all") and "in fact all" in cn:
            label = "CONTRADICTED"
        elif pn.startswith("no ") and ("some" in cn or "all four" in cn or "every " in cn):
            label = "CONTRADICTED"
        elif pn.startswith("exactly two") and "all four" in cn:
            label = "CONTRADICTED"
        elif pn.startswith("exactly one") and "all four" in cn:
            label = "CONTRADICTED"
        elif pn.startswith("at least three") and "all four" in cn:
            label = "ENTAILED"
        elif pn.startswith("at least one") and ("some" in cn or "all four" in cn or "every " in cn):
            label = "UNKNOWN" if "not every" in cn and "no " not in cn else "ENTAILED"
        elif (" succeeded" in pn and " failed" in cn) or (" failed" in pn and " succeeded" in cn):
            if len(tokens(text) & tokens(" ".join(statements))) >= 1:
                label = "CONTRADICTED"
        elif "did not touch copper" in pn and ("touched copper" in cn or "only way" in cn or "if and only if" in cn):
            label = "CONTRADICTED"
        elif "touched copper" in pn and "touched copper" in cn:
            label = "ASSERTED"
        elif "is blue" in pn and any("is blue" in c for c in ctx_norm):
            label = "ASSERTED"
        elif "copper contact is necessary" in pn and ("if and only if" in cn or "only way" in cn):
            label = "ENTAILED"
        elif "copper contact is necessary" in pn and ("if " in cn or "implies" in cn or "whenever" in cn):
            label = "CONTRADICTED"
        elif "copper contact is sufficient" in pn and ("if " in cn or "implies" in cn or "whenever" in cn or "always makes" in cn):
            label = "ENTAILED"
        elif "blue alone establishes copper contact" in pn and ("if " in cn or "implies" in cn or "whenever" in cn):
            label = "CONTRADICTED"
        elif "release is blocked" in pn and ("blocks release" in cn or "failed aux blocks release" in cn):
            label = "ENTAILED"
        elif "release is forbidden" in pn and ("mandatory" in cn and "failed" in cn):
            label = "ENTAILED"
        elif "release conditions are satisfied" in pn:
            if ("only release gate" in cn or "necessary and sufficient" in cn or "alone controls release" in cn or "exactly when gate passes" in cn) and not ("mandatory" in cn and "failed" in cn and "diagnostic only" not in cn):
                label = "ENTAILED"
            elif "mandatory" in cn and "failed" in cn:
                label = "CONTRADICTED"
        elif "exactly two clockwise rotations" in pn and "exactly twice clockwise" in cn and ("varked" in cn or "performed the action" in cn):
            label = "ENTAILED"
        elif "exactly three clockwise rotations" in pn and "exactly twice clockwise" in cn:
            label = "CONTRADICTED"
        out[p["id"]] = label
    return out


def macro_f1(gold: list[str], pred: list[str]) -> float:
    values=[]
    for label in LABELS:
        tp=sum(g==label and p==label for g,p in zip(gold,pred))
        fp=sum(g!=label and p==label for g,p in zip(gold,pred))
        fn=sum(g==label and p!=label for g,p in zip(gold,pred))
        precision=tp/(tp+fp) if tp+fp else 0.0
        recall=tp/(tp+fn) if tp+fn else 0.0
        values.append(2*precision*recall/(precision+recall) if precision+recall else 0.0)
    return sum(values)/len(values)


def evaluate(strategy: Callable[[dict[str, Any]], dict[str, str]]) -> dict[str, Any]:
    cases,golds=build_dataset(); gold_by={g['id']:g for g in golds}; ys=[]; ps=[]
    for case in cases:
        pred=strategy(case); gold=gold_by[case['id']]['gold']
        for prop in case['propositions']:
            pid=prop['id']; ys.append(gold[pid]['label']); ps.append(pred[pid])
    acc=sum(a==b for a,b in zip(ys,ps))/len(ys)
    return {'accuracy':acc,'macro_f1':macro_f1(ys,ps),'prediction_counts':dict(Counter(ps))}


def _features(case: dict[str, Any], proposition: dict[str, str]) -> Counter[str]:
    view = model_view(case)
    feats: Counter[str] = Counter()
    ptoks = re.findall(r"[a-z]+|[0-9]+", proposition["text"].lower())
    ctoks = re.findall(r"[a-z]+|[0-9]+", " ".join(x["text"] for x in view["context"]).lower())
    for tok in ptoks:
        feats["p:" + tok] += 1
    for tok in ctoks:
        feats["c:" + tok] += 1
    pset, cset = set(ptoks), set(ctoks)
    for tok in pset & cset:
        feats["both:" + tok] += 1
    feats[f"p_len:{min(len(ptoks)//3,8)}"] += 1
    feats[f"c_len:{min(len(ctoks)//5,10)}"] += 1
    feats[f"overlap:{min(len(pset & cset),10)}"] += 1
    return feats


def leave_one_pair_out_nb() -> tuple[list[str], list[str]]:
    """Transparent shallow lexical baseline. Each pair is predicted by a NB model trained on the other 35 pairs."""
    import math
    cases, golds = build_dataset()
    gold_by = {g["id"]: g for g in golds}
    pairs = sorted({c["pair_id"] for c in cases})
    ys: list[str] = []
    ps: list[str] = []
    for held in pairs:
        class_docs = Counter()
        feat_counts: dict[str, Counter[str]] = {label: Counter() for label in LABELS}
        totals = Counter()
        vocab: set[str] = set()
        for case in cases:
            if case["pair_id"] == held:
                continue
            g = gold_by[case["id"]]["gold"]
            for prop in case["propositions"]:
                label = g[prop["id"]]["label"]
                f = _features(case, prop)
                class_docs[label] += 1
                feat_counts[label].update(f)
                totals[label] += sum(f.values())
                vocab.update(f)
        n_docs = sum(class_docs.values())
        v = max(len(vocab), 1)
        for case in cases:
            if case["pair_id"] != held:
                continue
            g = gold_by[case["id"]]["gold"]
            for prop in case["propositions"]:
                f = _features(case, prop)
                scores = {}
                for label in LABELS:
                    prior = (class_docs[label] + 1) / (n_docs + len(LABELS))
                    score = math.log(prior)
                    denom = totals[label] + v
                    for feat, count in f.items():
                        score += count * math.log((feat_counts[label][feat] + 1) / denom)
                    scores[label] = score
                pred = max(LABELS, key=lambda label: (scores[label], -LABELS.index(label)))
                ys.append(g[prop["id"]]["label"])
                ps.append(pred)
    return ys, ps


def evaluate_nb() -> dict[str, Any]:
    ys, ps = leave_one_pair_out_nb()
    return {
        "accuracy": sum(a == b for a, b in zip(ys, ps)) / len(ys),
        "macro_f1": macro_f1(ys, ps),
        "prediction_counts": dict(Counter(ps)),
    }


def build_report() -> dict[str, Any]:
    shortcut={name:evaluate(fn) for name,fn in {
        'all_unknown':all_unknown,
        'exact_overlap':exact_overlap,
    }.items()}
    shortcut['leave_one_pair_out_nb'] = evaluate_nb()
    best=max(v['macro_f1'] for v in shortcut.values())
    symbolic={'surface_rules': evaluate(surface_rules)}
    best_transparent=max(best, max(v['macro_f1'] for v in symbolic.values()))
    return {'shortcut_strategies':shortcut,'best_shortcut_macro_f1':best,'symbolic_red_team':symbolic,'best_transparent_baseline_macro_f1':best_transparent}


def main() -> None:
    print(json.dumps(build_report(),indent=2,sort_keys=True))

if __name__=='__main__': main()
