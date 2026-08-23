from __future__ import annotations

import hashlib
import random
from typing import Any

LABELS = ["ASSERTED", "ENTAILED", "PRESUPPOSED", "IMPLICATED", "CONTRADICTED", "UNKNOWN"]
FAMILIES = [
    "scalar_implicature",
    "presupposition_trigger",
    "context_reversal",
    "nonce_temporal",
    "deixis_reference",
    "negation_quantifier",
    "invented_lexicon",
    "abductive_trap",
]

def nonce(prefix: str, i: int) -> str:
    return f"{prefix}{i:02d}X"

def opaque_id(cid: str, kind: str, idx: int) -> str:
    return f"{kind}_{hashlib.sha256(f'{cid}:{kind}:{idx}'.encode()).hexdigest()[:10].upper()}"

def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest()[:16], 16)

def _select_props(cid: str, props: list[tuple[str, str, list[str]]], focus_index: int) -> tuple[list[tuple[str, str, list[str]]], int]:
    """Select 5-8 propositions, always retaining focus, without fixed label cardinality."""
    rng = random.Random(_seed(cid + ":subset"))
    target = 5 + (_seed(cid + ":count") % 4)
    indexes = list(range(len(props)))
    others = [idx for idx in indexes if idx != focus_index]
    rng.shuffle(others)
    keep = [focus_index, *others[: max(0, target - 1)]]
    keep = sorted(set(keep))
    selected = [props[idx] for idx in keep]
    new_focus = keep.index(focus_index)
    return selected, new_focus

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
    props, focus_index = _select_props(cid, props, focus_index)
    s_map = {f"S{j+1}": opaque_id(cid, "S", j + 1) for j in range(len(context))}
    p_map = {f"P{j+1}": opaque_id(cid, "P", j + 1) for j in range(len(props))}
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
    focus_pid = p_map[f"P{focus_index+1}"]
    cases.append(
        {
            "id": cid,
            "family": family,
            "pair_id": pair_id,
            "pair_kind": pair_kind,
            "variant": variant,
            "renderer": renderer,
            "context": ctx,
            "propositions": pitems,
            "focus_proposition": focus_pid,
        }
    )
    golds.append(
        {
            "id": cid,
            "family": family,
            "pair_id": pair_id,
            "pair_kind": pair_kind,
            "variant": variant,
            "renderer": renderer,
            "focus_proposition": focus_pid,
            "gold": gmap,
        }
    )
