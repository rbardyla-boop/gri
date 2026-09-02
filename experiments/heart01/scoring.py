"""Score A–F on the six HEART criteria. Tests are the execution of the preregistered claim."""

from __future__ import annotations

from typing import Any

from experiments.heart01.systems import run_system
from experiments.heart01.world import Event

CRITERIA = (
    "moves_on_persistent_wounds",
    "ignores_isolated_poison",
    "lowers_lifetime_cost_vs_A",
    "keeps_real_contradiction",
    "reverses_after_world_change",
    "does_not_avoid_hard_evidence",
)


def _end_mara(org) -> str:
    probe = Event("query", 79, "where", {"person": "Mara", "day_type": "Market"})
    return str(org.predict(probe))


def _rel(org, source: str) -> str:
    probe = Event("query", 79, "relation", {"a": "Lark", "b": "Wren", "source": source})
    return str(org.predict(probe))


def summarize(org) -> dict[str, Any]:
    town_traces = sum(
        1
        for tr in org.immutable_experience
        if tr.get("name") == "relation" and (tr.get("payload") or {}).get("source") == "town"
    )
    family_traces = sum(
        1
        for tr in org.immutable_experience
        if tr.get("name") == "relation" and (tr.get("payload") or {}).get("source") == "family"
    )
    return {
        "system": org.system,
        "pred_cost": org.pred_cost,
        "recon_cost": org.recon_cost,
        "lifetime_cost": org.pred_cost + org.recon_cost,
        "mid_mara_market": org.mid_mara_market_pred,
        "end_mara_market": _end_mara(org),
        "town_rel": _rel(org, "town"),
        "family_rel": _rel(org, "family"),
        "gossip_rel": _rel(org, "gossip"),
        "flat_rel": org.rel_flat.get(("Lark", "Wren")),
        "has_clock_skill": "clock_maintainer" in org.portable_skills,
        "has_vault_skill": "vault_opener" in org.portable_skills,
        "mara_tower_live": org.loc_beliefs.get(("Mara", "Market")) == "tower",
        "tensions": list(org.tensions),
        "hidden_contexts": list(org.hidden_contexts),
        "experience_len": len(org.immutable_experience),
        "emitted_traces": org.emitted_traces,
        "town_traces": town_traces,
        "family_traces": family_traces,
        "failed_adaptations": len(org.failed_adaptations),
        "prior_bodies": len(org.prior_stable_bodies),
        "mutations": org.mutations,
        "constitution_digest": org.constitution.digest,
        "witness_holdout": org.witness_holdout_used,
        "witness_post": org.witness_post_query_used,
        "witness_hard": org.witness_included_hard_evidence,
        "state": org.to_state(),
    }


def score_one(s: dict[str, Any], a_cost: int) -> dict[str, bool]:
    poison_ignored = (not s["has_clock_skill"]) and s["gossip_rel"] != "parent" and not s["mara_tower_live"]
    keeps = s["town_rel"] == "sibling" and s["family_rel"] == "cousin" and not s["flat_rel"]
    evidence = (
        s["experience_len"] == s["emitted_traces"]
        and s["town_traces"] >= 3
        and s["family_traces"] >= 3
        and "family" not in s["hidden_contexts"]
        and "town" not in s["hidden_contexts"]
    )
    if s["system"] == "F":
        evidence = evidence and s["witness_hard"] >= 1 and s["witness_post"] >= 1 and s["witness_holdout"] >= 1
    return {
        "moves_on_persistent_wounds": s["mid_mara_market"] == "greenhouse",
        "ignores_isolated_poison": poison_ignored,
        "lowers_lifetime_cost_vs_A": s["lifetime_cost"] < a_cost,
        "keeps_real_contradiction": keeps,
        "reverses_after_world_change": s["end_mara_market"] == "river",
        "does_not_avoid_hard_evidence": evidence,
    }


def run_heart() -> dict[str, Any]:
    orgs = {name: run_system(name) for name in "ABCDEF"}
    summaries = {name: summarize(org) for name, org in orgs.items()}
    a_cost = summaries["A"]["lifetime_cost"]
    board = {name: score_one(summaries[name], a_cost) for name in summaries}
    return {"board": board, "summaries": summaries, "criteria": CRITERIA, "orgs": orgs}


def format_scoreboard(result: dict[str, Any]) -> str:
    lines = ["Wildflower HEART01", "=================="]
    for name in "ABCDEF":
        row = result["board"][name]
        bits = " ".join(f"{k}:{('PASS' if v else 'FAIL')}" for k, v in row.items())
        n = sum(row.values())
        mark = "PASS" if all(row.values()) else "FAIL"
        lines.append(f"{name}  {n}/6 {mark}")
        lines.append(f"    {bits}")
    f_ok = all(result["board"]["F"].values())
    lines.append("")
    lines.append("HEART F: " + ("PASS" if f_ok else "FAIL"))
    s = result["summaries"]
    lines.append("costs  " + " ".join(f"{n}={s[n]['lifetime_cost']}" for n in "ABCDEF"))
    return "\n".join(lines)
