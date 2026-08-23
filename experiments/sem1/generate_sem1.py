from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

LABELS = ("ASSERTED", "ENTAILED", "PRESUPPOSED", "IMPLICATED", "CONTRADICTED", "UNKNOWN")
FAMILIES = (
    "scalar_scope",
    "factive_presupposition",
    "exception_scope",
    "nonce_temporal",
    "deixis_reference",
    "negation_quantifier",
    "invented_lexicon",
    "abductive_restraint",
)


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest()[:16], 16)


def _opaque(cid: str, kind: str, idx: int) -> str:
    return f"{kind}_{hashlib.sha256(f'SEM1:{cid}:{kind}:{idx}'.encode()).hexdigest()[:12].upper()}"


def _nonce(prefix: str, i: int) -> str:
    return f"{prefix}{i:02d}Q"


def _prop(text: str, label: str, evidence: list[str]) -> tuple[str, str, list[str]]:
    if label not in LABELS:
        raise ValueError(label)
    return text, label, evidence


def add_case(
    cases: list[dict[str, Any]],
    golds: list[dict[str, Any]],
    *,
    cid: str,
    family: str,
    pair_id: str,
    pair_kind: str,
    variant: str,
    renderer: str,
    context: list[str],
    props: list[tuple[str, str, list[str]]],
    focus_index: int,
) -> None:
    if len(props) != 6:
        raise AssertionError(f"{cid}: expected 6 propositions, got {len(props)}")
    s_map = {f"S{j+1}": _opaque(cid, "S", j + 1) for j in range(len(context))}
    p_map = {f"P{j+1}": _opaque(cid, "P", j + 1) for j in range(len(props))}
    ctx = [{"id": s_map[f"S{j+1}"], "text": text} for j, text in enumerate(context)]
    pitems: list[dict[str, str]] = []
    gmap: dict[str, dict[str, Any]] = {}
    for j, (text, label, evidence) in enumerate(props):
        pid = p_map[f"P{j+1}"]
        pitems.append({"id": pid, "text": text})
        gmap[pid] = {"label": label, "evidence": [s_map[x] for x in evidence]}

    rng = random.Random(_seed(cid + ":presentation"))
    rng.shuffle(ctx)
    rng.shuffle(pitems)
    cases.append({"id": cid, "context": ctx, "propositions": pitems})
    golds.append(
        {
            "id": cid,
            "family": family,
            "pair_id": pair_id,
            "pair_kind": pair_kind,
            "variant": variant,
            "renderer": renderer,
            "focus_proposition": p_map[f"P{focus_index+1}"],
            "gold": gmap,
        }
    )


def scalar_pair(i: int, invariant: bool):
    noun = _nonce("VEX", i)
    pair = f"S1-SCALAR-{i:02d}"
    focus = f"Not all six {noun} trials stabilized."
    if not invariant:
        ca = [f"Some of the six {noun} trials stabilized."]
        cb = [f"Some of the six {noun} trials stabilized.", f"In fact, all six {noun} trials stabilized."]
        pa = [
            _prop(focus, "IMPLICATED", ["S1"]),
            _prop(f"At least one {noun} trial stabilized.", "ENTAILED", ["S1"]),
            _prop(f"Some of the six {noun} trials stabilized.", "ASSERTED", ["S1"]),
            _prop(f"No {noun} trial stabilized.", "CONTRADICTED", ["S1"]),
            _prop(f"Exactly two {noun} trials stabilized.", "UNKNOWN", []),
            _prop(f"All six {noun} trials stabilized.", "UNKNOWN", []),
        ]
        pb = [
            _prop(focus, "CONTRADICTED", ["S2"]),
            _prop(f"At least one {noun} trial stabilized.", "ENTAILED", ["S2"]),
            _prop(f"Some of the six {noun} trials stabilized.", "ASSERTED", ["S1"]),
            _prop(f"No {noun} trial stabilized.", "CONTRADICTED", ["S2"]),
            _prop(f"All six {noun} trials stabilized.", "ASSERTED", ["S2"]),
            _prop(f"Exactly six {noun} trials stabilized.", "ENTAILED", ["S2"]),
        ]
        return pair, "REVISION", (ca, pa, 0, "some_then_all"), (cb, pb, 0, "explicit_cancellation")
    ca = [f"Some of the six {noun} trials stabilized.", "The record does not state an exact total."]
    cb = [f"There were some {noun} trials among the six that stabilized.", "No exact total is stated in the record."]
    pa = [
        _prop(focus, "IMPLICATED", ["S1"]),
        _prop(f"At least one {noun} trial stabilized.", "ENTAILED", ["S1"]),
        _prop(f"Some of the six {noun} trials stabilized.", "ASSERTED", ["S1"]),
        _prop(f"The record states the exact number of stabilized {noun} trials.", "CONTRADICTED", ["S2"]),
        _prop(f"Exactly three {noun} trials stabilized.", "UNKNOWN", []),
        _prop(f"No {noun} trial stabilized.", "CONTRADICTED", ["S1"]),
    ]
    pb = [
        _prop(focus, "IMPLICATED", ["S1"]),
        _prop(f"At least one {noun} trial stabilized.", "ENTAILED", ["S1"]),
        _prop(f"There were some {noun} trials among the six that stabilized.", "ASSERTED", ["S1"]),
        _prop(f"The record states the exact number of stabilized {noun} trials.", "CONTRADICTED", ["S2"]),
        _prop(f"Exactly four {noun} trials stabilized.", "UNKNOWN", []),
        _prop(f"All six {noun} trials stabilized.", "UNKNOWN", []),
    ]
    return pair, "INVARIANCE", (ca, pa, 0, "some_standard"), (cb, pb, 0, "some_paraphrase")


def presupp_pair(i: int, invariant: bool):
    person, beacon = _nonce("RAV", i), _nonce("ZEL", i)
    pair, focus = f"S1-PRESUP-{i:02d}", f"{beacon} cracked."
    if not invariant:
        ca = [f"{person} discovered that {beacon} cracked."]
        cb = [f"{person} suspected that {beacon} cracked."]
        pa = [
            _prop(focus, "PRESUPPOSED", ["S1"]),
            _prop(f"{person} discovered that {beacon} cracked.", "ASSERTED", ["S1"]),
            _prop(f"{beacon} remained uncracked.", "CONTRADICTED", ["S1"]),
            _prop(f"{person} had a mental attitude about {beacon}.", "ENTAILED", ["S1"]),
            _prop(f"{person} caused {beacon} to crack.", "UNKNOWN", []),
            _prop(f"{beacon} cracked yesterday.", "UNKNOWN", []),
        ]
        pb = [
            _prop(focus, "UNKNOWN", []),
            _prop(f"{person} suspected that {beacon} cracked.", "ASSERTED", ["S1"]),
            _prop(f"{person} had a mental attitude about {beacon}.", "ENTAILED", ["S1"]),
            _prop(f"{beacon} remained uncracked.", "UNKNOWN", []),
            _prop(f"{person} caused {beacon} to crack.", "UNKNOWN", []),
            _prop(f"{person}'s suspicion was correct.", "UNKNOWN", []),
        ]
        return pair, "REVISION", (ca, pa, 0, "factive_discover"), (cb, pb, 0, "nonfactive_suspect")
    ca = [f"{person} discovered that {beacon} cracked."]
    cb = [f"{person} did not discover that {beacon} cracked."]
    pa = [
        _prop(focus, "PRESUPPOSED", ["S1"]),
        _prop(f"{person} discovered that {beacon} cracked.", "ASSERTED", ["S1"]),
        _prop(f"{beacon} remained uncracked.", "CONTRADICTED", ["S1"]),
        _prop(f"{person} caused the crack.", "UNKNOWN", []),
        _prop(f"{beacon} cracked permanently.", "UNKNOWN", []),
        _prop(f"{person} encountered information about {beacon}.", "ENTAILED", ["S1"]),
    ]
    pb = [
        _prop(focus, "PRESUPPOSED", ["S1"]),
        _prop(f"{person} discovered that {beacon} cracked.", "CONTRADICTED", ["S1"]),
        _prop(f"{person} did not discover that {beacon} cracked.", "ASSERTED", ["S1"]),
        _prop(f"{beacon} remained uncracked.", "CONTRADICTED", ["S1"]),
        _prop(f"{person} caused the crack.", "UNKNOWN", []),
        _prop(f"{beacon} cracked permanently.", "UNKNOWN", []),
    ]
    return pair, "INVARIANCE", (ca, pa, 0, "factive_positive"), (cb, pb, 0, "factive_under_negation")


def exception_pair(i: int, invariant: bool):
    klass, item = _nonce("NORI", i), _nonce("TAL", i)
    pair, focus = f"S1-EXCEPT-{i:02d}", f"{item} is conductive."
    if not invariant:
        ca = [f"Every silver {klass} tile is conductive.", f"{item} is a silver {klass} tile."]
        cb = [f"Every silver {klass} tile is conductive except {item}.", f"{item} is a silver {klass} tile.", f"{item} is not conductive."]
        pa = [
            _prop(focus, "ENTAILED", ["S1", "S2"]),
            _prop(f"{item} is silver.", "ENTAILED", ["S2"]),
            _prop(f"{item} is a {klass} tile.", "ENTAILED", ["S2"]),
            _prop(f"{item} is not conductive.", "CONTRADICTED", ["S1", "S2"]),
            _prop(f"{item} is heavy.", "UNKNOWN", []),
            _prop(f"Every {klass} tile is conductive.", "UNKNOWN", []),
        ]
        pb = [
            _prop(focus, "CONTRADICTED", ["S3"]),
            _prop(f"{item} is a silver {klass} tile.", "ASSERTED", ["S2"]),
            _prop(f"{item} is not conductive.", "ASSERTED", ["S3"]),
            _prop(f"Every silver {klass} tile other than {item} is conductive.", "ENTAILED", ["S1"]),
            _prop(f"{item} is heavy.", "UNKNOWN", []),
            _prop(f"No silver {klass} tile is conductive.", "UNKNOWN", []),
        ]
        return pair, "REVISION", (ca, pa, 0, "universal_rule"), (cb, pb, 0, "explicit_exception")
    ca = [f"All silver {klass} tiles are conductive.", f"{item} is silver and is a {klass} tile."]
    cb = [f"Any tile that is both silver and {klass} is conductive.", f"{item} is a {klass} tile and is silver."]
    common = [
        _prop(focus, "ENTAILED", ["S1", "S2"]),
        _prop(f"{item} is silver.", "ENTAILED", ["S2"]),
        _prop(f"{item} is a {klass} tile.", "ENTAILED", ["S2"]),
        _prop(f"{item} is not conductive.", "CONTRADICTED", ["S1", "S2"]),
        _prop(f"{item} is heavy.", "UNKNOWN", []),
        _prop(f"Some non-silver {klass} tile is conductive.", "UNKNOWN", []),
    ]
    return pair, "INVARIANCE", (ca, common, 0, "universal_all"), (cb, common, 0, "universal_any")


def temporal_pair(i: int, invariant: bool):
    rel, a, b = _nonce("DAX", i), _nonce("EVR", i), _nonce("EVS", i)
    pair, focus, day = f"S1-TEMP-{i:02d}", f"{a} {rel}-precedes {b}.", 20 + i
    if not invariant:
        ca = [f"In this world, '{rel}-precedes' means occurs exactly two days before.", f"{a} occurred on day {day}.", f"{b} occurred on day {day+2}."]
        cb = [f"In this world, '{rel}-precedes' means occurs exactly one day before.", f"{a} occurred on day {day}.", f"{b} occurred on day {day+2}."]
        pa = [
            _prop(focus, "ENTAILED", ["S1", "S2", "S3"]),
            _prop(f"{a} occurred before {b}.", "ENTAILED", ["S2", "S3"]),
            _prop(f"{b} occurred two days after {a}.", "ENTAILED", ["S2", "S3"]),
            _prop(f"{a} occurred on day {day}.", "ASSERTED", ["S2"]),
            _prop(f"{a} occurred after {b}.", "CONTRADICTED", ["S2", "S3"]),
            _prop(f"A third event occurred between {a} and {b}.", "UNKNOWN", []),
        ]
        pb = [
            _prop(focus, "CONTRADICTED", ["S1", "S2", "S3"]),
            _prop(f"{a} occurred before {b}.", "ENTAILED", ["S2", "S3"]),
            _prop(f"{b} occurred two days after {a}.", "ENTAILED", ["S2", "S3"]),
            _prop(f"{b} occurred on day {day+2}.", "ASSERTED", ["S3"]),
            _prop(f"{a} occurred after {b}.", "CONTRADICTED", ["S2", "S3"]),
            _prop(f"{a} {rel}-precedes some event other than {b}.", "UNKNOWN", []),
        ]
        return pair, "REVISION", (ca, pa, 0, "two_day_relation"), (cb, pb, 0, "one_day_relation")
    ca = [f"In this world, '{rel}-precedes' means that the first event is exactly two days earlier than the second.", f"{a} occurred on day {day}.", f"{b} occurred on day {day+2}."]
    cb = [f"In this world, '{rel}-precedes' holds exactly when the second event occurs two days after the first.", f"{b} occurred on day {day+2}.", f"{a} occurred on day {day}."]
    pa = [
        _prop(focus, "ENTAILED", ["S1", "S2", "S3"]),
        _prop(f"{b} occurred after {a}.", "ENTAILED", ["S2", "S3"]),
        _prop(f"{a} occurred on day {day}.", "ASSERTED", ["S2"]),
        _prop(f"{b} occurred before {a}.", "CONTRADICTED", ["S2", "S3"]),
        _prop(f"{a} and {b} happened on the same day.", "CONTRADICTED", ["S2", "S3"]),
        _prop(f"{b} was caused by {a}.", "UNKNOWN", []),
    ]
    pb = [
        _prop(focus, "ENTAILED", ["S1", "S2", "S3"]),
        _prop(f"{b} occurred after {a}.", "ENTAILED", ["S2", "S3"]),
        _prop(f"{a} occurred on day {day}.", "ASSERTED", ["S3"]),
        _prop(f"{b} occurred before {a}.", "CONTRADICTED", ["S2", "S3"]),
        _prop(f"{a} and {b} happened on the same day.", "CONTRADICTED", ["S2", "S3"]),
        _prop(f"{b} was caused by {a}.", "UNKNOWN", []),
    ]
    return pair, "INVARIANCE", (ca, pa, 0, "temporal_definition_a"), (cb, pb, 0, "temporal_definition_b")


def deixis_pair(i: int, invariant: bool):
    p1, p2, place = _nonce("NER", i), _nonce("LUM", i), f"Bay-{30+i}"
    pair, focus, quote = f"S1-DEIXIS-{i:02d}", f"In the quotation, 'I' refers to {p1}.", '"I left the marker here."'
    if not invariant:
        ca = [f"For this record, the speaker is {p1} and 'here' means {place}.", f"The recorded speaker said {quote}"]
        cb = [f"For this record, the speaker is {p2}, not {p1}, and 'here' means {place}.", f"The recorded speaker said {quote}"]
        pa = [
            _prop(focus, "ENTAILED", ["S1", "S2"]),
            _prop(f"In the quotation, 'here' refers to {place}.", "ENTAILED", ["S1", "S2"]),
            _prop(f"{p1} said {quote}", "ENTAILED", ["S1", "S2"]),
            _prop(f"{p2} is the speaker.", "UNKNOWN", []),
            _prop("The marker is blue.", "UNKNOWN", []),
            _prop(f"In the quotation, 'I' refers to {p2}.", "CONTRADICTED", ["S1", "S2"]),
        ]
        pb = [
            _prop(focus, "CONTRADICTED", ["S1", "S2"]),
            _prop(f"In the quotation, 'here' refers to {place}.", "ENTAILED", ["S1", "S2"]),
            _prop(f"{p2} said {quote}", "ENTAILED", ["S1", "S2"]),
            _prop(f"{p1} is the speaker.", "CONTRADICTED", ["S1"]),
            _prop("The marker is blue.", "UNKNOWN", []),
            _prop(f"For this record, the speaker is {p2}, not {p1}, and 'here' means {place}.", "ASSERTED", ["S1"]),
        ]
        return pair, "REVISION", (ca, pa, 0, "speaker_one"), (cb, pb, 0, "speaker_two")
    ca = [f"For this record, {p1} is the speaker and the current location is {place}.", f"The speaker said {quote}"]
    cb = [f"The speaker for this record is {p1}; {place} is the location meant by 'here'.", f"{quote} was said by the speaker."]
    pa = [
        _prop(focus, "ENTAILED", ["S1", "S2"]),
        _prop(f"In the quotation, 'here' refers to {place}.", "ENTAILED", ["S1", "S2"]),
        _prop(f"{p1} is the speaker.", "ASSERTED", ["S1"]),
        _prop(f"{p1} left a marker at {place}.", "ENTAILED", ["S1", "S2"]),
        _prop("The marker is blue.", "UNKNOWN", []),
        _prop(f"No marker was left at {place}.", "CONTRADICTED", ["S1", "S2"]),
    ]
    pb = [
        _prop(focus, "ENTAILED", ["S1", "S2"]),
        _prop(f"In the quotation, 'here' refers to {place}.", "ENTAILED", ["S1", "S2"]),
        _prop(f"{p1} is the speaker.", "ENTAILED", ["S1"]),
        _prop(f"{p1} left a marker at {place}.", "ENTAILED", ["S1", "S2"]),
        _prop("The marker is blue.", "UNKNOWN", []),
        _prop(f"No marker was left at {place}.", "CONTRADICTED", ["S1", "S2"]),
    ]
    return pair, "INVARIANCE", (ca, pa, 0, "speaker_frame_a"), (cb, pb, 0, "speaker_frame_b")


def quant_pair(i: int, invariant: bool):
    noun = _nonce("TOR", i)
    pair, focus = f"S1-QUANT-{i:02d}", f"At least four of the seven {noun} lamps are lit."
    if not invariant:
        ca = [f"Exactly four of the seven {noun} lamps are lit."]
        cb = [f"Exactly three of the seven {noun} lamps are lit."]
        pa = [
            _prop(focus, "ENTAILED", ["S1"]),
            _prop(f"Exactly four of the seven {noun} lamps are lit.", "ASSERTED", ["S1"]),
            _prop(f"Not all seven {noun} lamps are lit.", "ENTAILED", ["S1"]),
            _prop(f"No {noun} lamp is lit.", "CONTRADICTED", ["S1"]),
            _prop(f"All seven {noun} lamps are lit.", "CONTRADICTED", ["S1"]),
            _prop(f"The first {noun} lamp is lit.", "UNKNOWN", []),
        ]
        pb = [
            _prop(focus, "CONTRADICTED", ["S1"]),
            _prop(f"Exactly three of the seven {noun} lamps are lit.", "ASSERTED", ["S1"]),
            _prop(f"At least one {noun} lamp is lit.", "ENTAILED", ["S1"]),
            _prop(f"Not all seven {noun} lamps are lit.", "ENTAILED", ["S1"]),
            _prop(f"Exactly four {noun} lamps are lit.", "CONTRADICTED", ["S1"]),
            _prop(f"The first {noun} lamp is lit.", "UNKNOWN", []),
        ]
        return pair, "REVISION", (ca, pa, 0, "exact_four"), (cb, pb, 0, "exact_three")
    ca = [f"Exactly four of the seven {noun} lamps are lit."]
    cb = [f"Four, and only four, of the seven {noun} lamps are lit."]
    pa = [
        _prop(focus, "ENTAILED", ["S1"]),
        _prop(f"Exactly four of the seven {noun} lamps are lit.", "ASSERTED", ["S1"]),
        _prop(f"At least one {noun} lamp is lit.", "ENTAILED", ["S1"]),
        _prop(f"Not all seven {noun} lamps are lit.", "ENTAILED", ["S1"]),
        _prop(f"All seven {noun} lamps are lit.", "CONTRADICTED", ["S1"]),
        _prop(f"The seventh {noun} lamp is lit.", "UNKNOWN", []),
    ]
    pb = [
        _prop(focus, "ENTAILED", ["S1"]),
        _prop(f"Four, and only four, of the seven {noun} lamps are lit.", "ASSERTED", ["S1"]),
        _prop(f"At least one {noun} lamp is lit.", "ENTAILED", ["S1"]),
        _prop(f"Not all seven {noun} lamps are lit.", "ENTAILED", ["S1"]),
        _prop(f"No {noun} lamp is lit.", "CONTRADICTED", ["S1"]),
        _prop(f"The seventh {noun} lamp is lit.", "UNKNOWN", []),
    ]
    return pair, "INVARIANCE", (ca, pa, 0, "exactly_four"), (cb, pb, 0, "four_only")


def lexicon_pair(i: int, invariant: bool):
    word, item = _nonce("MURK", i), _nonce("OBJ", i)
    pair, focus = f"S1-LEX-{i:02d}", f"{item} is copper."
    if not invariant:
        ca = [f"In this lexicon, '{word}' means both copper and smooth.", f"{item} is {word}."]
        cb = [f"In this lexicon, '{word}' means both glass and smooth.", f"{item} is {word}."]
        pa = [
            _prop(focus, "ENTAILED", ["S1", "S2"]),
            _prop(f"{item} is smooth.", "ENTAILED", ["S1", "S2"]),
            _prop(f"{item} is {word}.", "ASSERTED", ["S2"]),
            _prop(f"{item} is not copper.", "CONTRADICTED", ["S1", "S2"]),
            _prop(f"{item} is glass.", "UNKNOWN", []),
            _prop(f"{item} is heavy.", "UNKNOWN", []),
        ]
        pb = [
            _prop(focus, "UNKNOWN", []),
            _prop(f"{item} is glass.", "ENTAILED", ["S1", "S2"]),
            _prop(f"{item} is smooth.", "ENTAILED", ["S1", "S2"]),
            _prop(f"{item} is {word}.", "ASSERTED", ["S2"]),
            _prop(f"{item} is not glass.", "CONTRADICTED", ["S1", "S2"]),
            _prop(f"{item} is heavy.", "UNKNOWN", []),
        ]
        return pair, "REVISION", (ca, pa, 0, "copper_definition"), (cb, pb, 0, "glass_definition")
    ca = [f"In this lexicon, '{word}' means an object that is copper and smooth.", f"{item} is {word}."]
    cb = [f"By definition here, something counts as '{word}' exactly when it is both smooth and copper.", f"{item} is {word}."]
    pa = [
        _prop(focus, "ENTAILED", ["S1", "S2"]),
        _prop(f"{item} is smooth.", "ENTAILED", ["S1", "S2"]),
        _prop(f"{item} is {word}.", "ASSERTED", ["S2"]),
        _prop(f"{item} is not copper.", "CONTRADICTED", ["S1", "S2"]),
        _prop(f"{item} is glass.", "UNKNOWN", []),
        _prop(f"Every copper object is {word}.", "UNKNOWN", []),
    ]
    pb = [
        _prop(focus, "ENTAILED", ["S1", "S2"]),
        _prop(f"{item} is smooth.", "ENTAILED", ["S1", "S2"]),
        _prop(f"{item} is {word}.", "ASSERTED", ["S2"]),
        _prop(f"{item} is not copper.", "CONTRADICTED", ["S1", "S2"]),
        _prop(f"{item} is glass.", "UNKNOWN", []),
        _prop(f"Every smooth object is {word}.", "UNKNOWN", []),
    ]
    return pair, "INVARIANCE", (ca, pa, 0, "definition_conjunction"), (cb, pb, 0, "definition_biconditional")


def abductive_pair(i: int, invariant: bool):
    item = _nonce("KAV", i)
    pair, focus = f"S1-ABD-{i:02d}", f"{item} contains cobalt."
    if not invariant:
        ca = [f"If an object contains cobalt, then it emits a low hum.", f"{item} emits a low hum."]
        cb = [f"If an object contains cobalt, then it emits a low hum.", f"{item} emits a low hum.", "Only objects containing cobalt emit a low hum."]
        pa = [
            _prop(focus, "UNKNOWN", []),
            _prop(f"{item} emits a low hum.", "ASSERTED", ["S2"]),
            _prop(f"If {item} contains cobalt, then {item} emits a low hum.", "ENTAILED", ["S1"]),
            _prop(f"{item} does not emit a low hum.", "CONTRADICTED", ["S2"]),
            _prop(f"{item} contains iron.", "UNKNOWN", []),
            _prop("Every humming object contains cobalt.", "UNKNOWN", []),
        ]
        pb = [
            _prop(focus, "ENTAILED", ["S2", "S3"]),
            _prop(f"{item} emits a low hum.", "ASSERTED", ["S2"]),
            _prop(f"{item} does not emit a low hum.", "CONTRADICTED", ["S2"]),
            _prop("Every humming object contains cobalt.", "ENTAILED", ["S3"]),
            _prop(f"{item} contains iron.", "UNKNOWN", []),
            _prop("No cobalt object emits a low hum.", "CONTRADICTED", ["S1"]),
        ]
        return pair, "REVISION", (ca, pa, 0, "sufficiency_only"), (cb, pb, 0, "necessity_added")
    ca = ["Whenever an object contains cobalt, it emits a low hum.", f"{item} emits a low hum."]
    cb = ["Containing cobalt is sufficient for an object to emit a low hum.", f"{item} emits a low hum."]
    common = [
        _prop(focus, "UNKNOWN", []),
        _prop(f"{item} emits a low hum.", "ASSERTED", ["S2"]),
        _prop(f"{item} does not emit a low hum.", "CONTRADICTED", ["S2"]),
        _prop(f"{item} contains iron.", "UNKNOWN", []),
        _prop("A cobalt object would emit a low hum.", "ENTAILED", ["S1"]),
        _prop("Every humming object contains cobalt.", "UNKNOWN", []),
    ]
    return pair, "INVARIANCE", (ca, common, 0, "if_rule"), (cb, common, 0, "sufficient_rule")


BUILDERS = (scalar_pair, presupp_pair, exception_pair, temporal_pair, deixis_pair, quant_pair, lexicon_pair, abductive_pair)


def build_dataset() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases: list[dict[str, Any]] = []
    gold: list[dict[str, Any]] = []
    for family, builder in zip(FAMILIES, BUILDERS):
        for i in range(6):
            invariant = i >= 3
            pair_id, pair_kind, left, right = builder(i, invariant)
            for side, item in zip(("A", "B"), (left, right)):
                context, props, focus_index, renderer = item
                cid = f"SEM1-{family.upper().replace('_', '-')}-{i:02d}-{side}"
                add_case(
                    cases,
                    gold,
                    cid=cid,
                    family=family,
                    pair_id=pair_id,
                    pair_kind=pair_kind,
                    variant=side,
                    renderer=renderer,
                    context=context,
                    props=props,
                    focus_index=focus_index,
                )
    if len(cases) != 96 or len(gold) != 96:
        raise AssertionError((len(cases), len(gold)))
    return cases, gold


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def dataset_summary(gold: list[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    patterns: Counter[tuple[int, ...]] = Counter()
    families: Counter[str] = Counter()
    pair_kinds: Counter[str] = Counter()
    for row in gold:
        local = Counter(item["label"] for item in row["gold"].values())
        counts.update(local)
        patterns[tuple(local[label] for label in LABELS)] += 1
        families[row["family"]] += 1
        pair_kinds[row["pair_kind"]] += 1
    return {
        "case_count": len(gold),
        "decision_count": sum(len(row["gold"]) for row in gold),
        "pair_count": len({row["pair_id"] for row in gold}),
        "families": dict(families),
        "pair_kind_case_counts": dict(pair_kinds),
        "global_label_counts": dict(counts),
        "unique_label_patterns": len(patterns),
        "max_label_pattern_frequency": max(patterns.values()),
        "one_each_label_cases": patterns.get((1, 1, 1, 1, 1, 1), 0),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the fresh SEM-1 semantic-control instrument.")
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True)
    args = ap.parse_args()
    cases, gold = build_dataset()
    write_jsonl(args.cases, cases)
    write_jsonl(args.gold, gold)
    print(json.dumps(dataset_summary(gold), sort_keys=True))


if __name__ == "__main__":
    main()
