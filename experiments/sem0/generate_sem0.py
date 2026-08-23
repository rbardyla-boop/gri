from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

LABELS = ["ASSERTED", "ENTAILED", "PRESUPPOSED", "IMPLICATED", "CONTRADICTED", "UNKNOWN"]

def nonce(prefix: str, i: int) -> str:
    return f"{prefix}{i:02d}X"

def opaque_id(cid: str, kind: str, idx: int) -> str:
    return f"{kind}_{hashlib.sha256(f'{cid}:{kind}:{idx}'.encode()).hexdigest()[:8].upper()}"

def add_case(cases, golds, *, cid, family, pair_id, variant, context, props, focus):
    s_map = {f"S{j+1}": opaque_id(cid, "S", j+1) for j in range(len(context))}
    p_map = {f"P{j+1}": opaque_id(cid, "P", j+1) for j in range(len(props))}
    ctx = [{"id": s_map[f"S{j+1}"], "text": t} for j, t in enumerate(context)]
    pitems = []
    gmap = {}
    for j, (text, label, evidence) in enumerate(props):
        oldpid = f"P{j+1}"
        pid = p_map[oldpid]
        pitems.append({"id": pid, "text": text})
        gmap[pid] = {"label": label, "evidence": [s_map[x] for x in evidence]}
    rng = random.Random(int(hashlib.sha256((cid + ":presentation").encode()).hexdigest()[:16], 16))
    rng.shuffle(ctx)
    rng.shuffle(pitems)
    cases.append({
        "id": cid,
        "family": family,
        "pair_id": pair_id,
        "variant": variant,
        "context": ctx,
        "propositions": pitems,
        "focus_proposition": p_map[focus],
    })
    golds.append({
        "id": cid,
        "pair_id": pair_id,
        "variant": variant,
        "family": family,
        "focus_proposition": p_map[focus],
        "gold": gmap,
    })

def build_dataset():
    cases=[]; golds=[]
    # scalar
    for i in range(4):
        n=nonce("KEL",i); person=nonce("RIN",i); action=nonce("VIM",i)
        pair=f"SCALAR-{i:02d}"
        context=[
            f"Some of the four {n} trials passed.",
            f"{person} did not stop performing action {action}.",
        ]
        props=[
            (f"Some of the four {n} trials passed.","ASSERTED",["S1"]),
            (f"At least one {n} trial passed.","ENTAILED",["S1"]),
            (f"Not all four {n} trials passed.","IMPLICATED",["S1"]),
            (f"Exactly two {n} trials passed.","UNKNOWN",[]),
            (f"{person} performed action {action} before now.","PRESUPPOSED",["S2"]),
            (f"No {n} trial passed.","CONTRADICTED",["S1"]),
        ]
        add_case(cases,golds,cid=f"SEM0-SCALAR-{i:02d}-A",family="scalar_implicature",pair_id=pair,variant="base",context=context,props=props,focus="P3")
        context2=context+[f"In fact, all four {n} trials passed."]
        props2=[
            (f"Some of the four {n} trials passed.","ASSERTED",["S1"]),
            (f"At least one {n} trial passed.","ENTAILED",["S1"]),
            (f"Not all four {n} trials passed.","CONTRADICTED",["S3"]),
            (f"Exactly two {n} trials passed.","CONTRADICTED",["S3"]),
            (f"{person} performed action {action} before now.","PRESUPPOSED",["S2"]),
            (f"No {n} trial passed.","CONTRADICTED",["S3"]),
        ]
        add_case(cases,golds,cid=f"SEM0-SCALAR-{i:02d}-B",family="scalar_implicature",pair_id=pair,variant="cancelled",context=context2,props=props2,focus="P3")

    # factive
    for i in range(4):
        beacon=nonce("BEA",i); rack=nonce("RACK",i); person=nonce("MIRA",i); backup=nonce("BACK",i)
        pair=f"FACTIVE-{i:02d}"
        for variant,realize in [("affirmative",f"{person} realized that {beacon} failed."),
                                ("negated",f"{person} did not realize that {beacon} failed.")]:
            context=[
                realize,
                f"{beacon} is in {rack}.",
                f"Every beacon in {rack} is monitored.",
                f"{beacon} did not succeed.",
                f"Some of the four {backup} backup beacons responded.",
            ]
            props=[
                (realize,"ASSERTED",["S1"]),
                (f"{beacon} failed.","PRESUPPOSED",["S1"]),
                (f"{beacon} is monitored.","ENTAILED",["S2","S3"]),
                (f"{beacon} succeeded.","CONTRADICTED",["S4"]),
                (f"{person} caused {beacon} to fail.","UNKNOWN",[]),
                (f"Not all four {backup} backup beacons responded.","IMPLICATED",["S5"]),
            ]
            add_case(cases,golds,cid=f"SEM0-FACTIVE-{i:02d}-{variant[0].upper()}",
                     family="presupposition_projection",pair_id=pair,variant=variant,
                     context=context,props=props,focus="P2")

    # release
    for i in range(4):
        gate=nonce("GATE",i); pair=f"RELEASE-{i:02d}"
        context=[
            "A release is authorized if and only if every mandatory gate passes.",
            f"The {gate} containment gate passed.",
            f"The {gate} containment gate is the only mandatory gate.",
            "Some of the four advisory checks passed.",
            "The operator did not stop monitoring.",
        ]
        props=[
            (f"The {gate} containment gate passed.","ASSERTED",["S2"]),
            ("The release is authorized.","ENTAILED",["S1","S2","S3"]),
            ("Not all four advisory checks passed.","IMPLICATED",["S4"]),
            ("The operator monitored before now.","PRESUPPOSED",["S5"]),
            ("The release is not authorized.","CONTRADICTED",["S1","S2","S3"]),
            ("The release will remain authorized tomorrow.","UNKNOWN",[]),
        ]
        add_case(cases,golds,cid=f"SEM0-RELEASE-{i:02d}-A",family="context_reversal",pair_id=pair,variant="sole_gate_passes",context=context,props=props,focus="P2")
        other=nonce("OTHER",i)
        context2=[
            "A release is authorized if and only if every mandatory gate passes.",
            f"The {gate} containment gate passed.",
            f"The {gate} containment gate is one of four mandatory gates.",
            f"The {other} mandatory gate failed.",
            "Some of the four advisory checks passed.",
            "The operator did not stop monitoring.",
        ]
        props2=[
            (f"The {gate} containment gate passed.","ASSERTED",["S2"]),
            ("The release is authorized.","CONTRADICTED",["S1","S3","S4"]),
            ("Not all four advisory checks passed.","IMPLICATED",["S5"]),
            ("The operator monitored before now.","PRESUPPOSED",["S6"]),
            ("The release is not authorized.","ENTAILED",["S1","S3","S4"]),
            ("Exactly two advisory checks passed.","UNKNOWN",[]),
        ]
        add_case(cases,golds,cid=f"SEM0-RELEASE-{i:02d}-B",family="context_reversal",pair_id=pair,variant="other_gate_fails",context=context2,props=props2,focus="P2")

    # grounding
    for i in range(4):
        typ=nonce("NORV",i); obj=nonce("OBJ",i); person=nonce("TECH",i); pair=f"GROUND-{i:02d}"
        context=[
            f"A {typ} object is blue exactly while it is touching copper.",
            f"{obj} is a {typ} object.",
            f"{obj} is not touching copper now.",
            f"{person} did not stop inspecting {obj}.",
            "Some of the four copper probes are active.",
        ]
        props=[
            (f"{obj} is a {typ} object.","ASSERTED",["S2"]),
            (f"{obj} is not blue now.","ENTAILED",["S1","S2","S3"]),
            (f"{person} inspected {obj} before now.","PRESUPPOSED",["S4"]),
            ("Not all four copper probes are active.","IMPLICATED",["S5"]),
            (f"{obj} is blue now.","CONTRADICTED",["S1","S2","S3"]),
            (f"{obj} touched copper yesterday.","UNKNOWN",[]),
        ]
        add_case(cases,golds,cid=f"SEM0-GROUND-{i:02d}-A",family="nonce_grounding",pair_id=pair,variant="temporary_rule",context=context,props=props,focus="P5")
        context2=[
            f"A {typ} object becomes blue when it touches copper and remains blue permanently afterward.",
            f"{obj} is a {typ} object.",
            f"{obj} touched copper yesterday.",
            f"{person} did not stop inspecting {obj}.",
            "Some of the four copper probes are active.",
        ]
        props2=[
            (f"{obj} touched copper yesterday.","ASSERTED",["S3"]),
            (f"{obj} is blue now.","ENTAILED",["S1","S2","S3"]),
            (f"{person} inspected {obj} before now.","PRESUPPOSED",["S4"]),
            ("Not all four copper probes are active.","IMPLICATED",["S5"]),
            (f"{obj} has never touched copper.","CONTRADICTED",["S3"]),
            (f"{obj} is touching copper now.","UNKNOWN",[]),
        ]
        add_case(cases,golds,cid=f"SEM0-GROUND-{i:02d}-B",family="nonce_grounding",pair_id=pair,variant="permanent_rule",context=context2,props=props2,focus="P2")

    # deixis
    for i in range(4):
        room1=nonce("ROOMQ",i); room2=nonce("ROOMR",i); sensor=nonce("SENS",i); person=nonce("OBS",i)
        pair=f"DEIXIS-{i:02d}"
        context=[
            f"In this message, the word 'here' means {room1}.",
            f"{sensor} is here.",
            f"{sensor} is in exactly one room.",
            f"{person} did not stop watching {sensor}.",
            "Some of the four indicator lamps are lit.",
        ]
        props=[
            (f"{sensor} is here.","ASSERTED",["S2"]),
            (f"{sensor} is in {room1}.","ENTAILED",["S1","S2"]),
            (f"{person} watched {sensor} before now.","PRESUPPOSED",["S4"]),
            ("Not all four indicator lamps are lit.","IMPLICATED",["S5"]),
            (f"{sensor} is in {room2}.","CONTRADICTED",["S1","S2","S3"]),
            (f"{sensor} was in {room1} yesterday.","UNKNOWN",[]),
        ]
        add_case(cases,golds,cid=f"SEM0-DEIXIS-{i:02d}-A",family="deixis_reference",pair_id=pair,variant="here_room_q",context=context,props=props,focus="P2")
        context2=[
            f"In this message, the word 'here' means {room2}.",
            f"{sensor} is here.",
            f"{sensor} is in exactly one room.",
            f"{person} did not stop watching {sensor}.",
            "Some of the four indicator lamps are lit.",
        ]
        props2=[
            (f"{sensor} is here.","ASSERTED",["S2"]),
            (f"{sensor} is in {room1}.","CONTRADICTED",["S1","S2","S3"]),
            (f"{person} watched {sensor} before now.","PRESUPPOSED",["S4"]),
            ("Not all four indicator lamps are lit.","IMPLICATED",["S5"]),
            (f"{sensor} is in {room2}.","ENTAILED",["S1","S2"]),
            (f"{sensor} was in {room2} yesterday.","UNKNOWN",[]),
        ]
        add_case(cases,golds,cid=f"SEM0-DEIXIS-{i:02d}-B",family="deixis_reference",pair_id=pair,variant="here_room_r",context=context2,props=props2,focus="P2")

    # quantifier
    for i in range(4):
        n=nonce("QUANT",i); person=nonce("AUD",i); pair=f"QUANT-{i:02d}"
        context=[
            f"There are exactly four {n} units.",
            f"Not every {n} unit passed.",
            f"{person} did not stop auditing the {n} units.",
            "Some of the four status lamps are lit.",
        ]
        props=[
            (f"Not every {n} unit passed.","ASSERTED",["S2"]),
            (f"At least one {n} unit did not pass.","ENTAILED",["S1","S2"]),
            (f"{person} audited the {n} units before now.","PRESUPPOSED",["S3"]),
            ("Not all four status lamps are lit.","IMPLICATED",["S4"]),
            (f"All four {n} units passed.","CONTRADICTED",["S2"]),
            (f"At least one {n} unit passed.","UNKNOWN",[]),
        ]
        add_case(cases,golds,cid=f"SEM0-QUANT-{i:02d}-A",family="negation_quantifier",pair_id=pair,variant="not_every",context=context,props=props,focus="P6")
        context2=[
            f"There are exactly four {n} units.",
            f"No {n} unit passed.",
            f"{person} did not stop auditing the {n} units.",
            "Some of the four status lamps are lit.",
        ]
        props2=[
            (f"No {n} unit passed.","ASSERTED",["S2"]),
            (f"At least one {n} unit did not pass.","ENTAILED",["S1","S2"]),
            (f"{person} audited the {n} units before now.","PRESUPPOSED",["S3"]),
            ("Not all four status lamps are lit.","IMPLICATED",["S4"]),
            (f"At least one {n} unit passed.","CONTRADICTED",["S2"]),
            (f"Exactly one {n} unit did not pass.","UNKNOWN",[]),
        ]
        add_case(cases,golds,cid=f"SEM0-QUANT-{i:02d}-B",family="negation_quantifier",pair_id=pair,variant="none",context=context2,props=props2,focus="P5")

    # invented lexicon
    for i in range(4):
        action=nonce("ZORP",i); obj=nonce("TOK",i); cont=nonce("CONT",i); person=nonce("LEX",i)
        pair=f"LEX-{i:02d}"
        context=[
            f"In this experiment, action {action} on an object means placing that object inside {cont}.",
            f"{person} performed action {action} on {obj}.",
            f"An object cannot be both inside and beside {cont} at the same time.",
            f"{person} did not stop checking {obj}.",
            "Some of the four marker lights are green.",
        ]
        props=[
            (f"{person} performed action {action} on {obj}.","ASSERTED",["S2"]),
            (f"{obj} is inside {cont}.","ENTAILED",["S1","S2"]),
            (f"{person} checked {obj} before now.","PRESUPPOSED",["S4"]),
            ("Not all four marker lights are green.","IMPLICATED",["S5"]),
            (f"{obj} is beside {cont}.","CONTRADICTED",["S1","S2","S3"]),
            (f"{obj} was inside {cont} yesterday.","UNKNOWN",[]),
        ]
        add_case(cases,golds,cid=f"SEM0-LEX-{i:02d}-A",family="invented_lexicon",pair_id=pair,variant="inside_definition",context=context,props=props,focus="P2")
        context2=[
            f"In this experiment, action {action} on an object means placing that object beside {cont}.",
            f"{person} performed action {action} on {obj}.",
            f"An object cannot be both inside and beside {cont} at the same time.",
            f"{person} did not stop checking {obj}.",
            "Some of the four marker lights are green.",
        ]
        props2=[
            (f"{person} performed action {action} on {obj}.","ASSERTED",["S2"]),
            (f"{obj} is inside {cont}.","CONTRADICTED",["S1","S2","S3"]),
            (f"{person} checked {obj} before now.","PRESUPPOSED",["S4"]),
            ("Not all four marker lights are green.","IMPLICATED",["S5"]),
            (f"{obj} is beside {cont}.","ENTAILED",["S1","S2"]),
            (f"{obj} was beside {cont} yesterday.","UNKNOWN",[]),
        ]
        add_case(cases,golds,cid=f"SEM0-LEX-{i:02d}-B",family="invented_lexicon",pair_id=pair,variant="beside_definition",context=context2,props=props2,focus="P2")
    return cases,golds


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True)
    args = ap.parse_args()
    cases, gold = build_dataset()
    write_jsonl(args.cases, cases)
    write_jsonl(args.gold, gold)
    print(json.dumps({
        "case_count": len(cases),
        "decision_count": sum(len(c["propositions"]) for c in cases),
        "labels": LABELS,
    }, sort_keys=True))

if __name__ == "__main__":
    main()
