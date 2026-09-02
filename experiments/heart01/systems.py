"""Six systems: A–E ablations, F complete (need + prior body + world witness)."""

from __future__ import annotations

from typing import Any

from experiments.heart01.constitution import FrozenConstitution
from experiments.heart01.organism import Organism
from experiments.heart01.world import CHANGE_AT, Event, SmallWorld

WOUND_THRESH = 3
VAULT_TAX_THRESH = 40
CLOCK_TAX_THRESH = 6
STRAIN_THRESH = 2
SCHEDULE_EVERY = 10
WITNESS_RECURRENCE = 3


def _mara_market_from_write_buffer(org: Organism) -> list[str]:
    vals = []
    for s in org.write_buffer:
        if (
            s["name"] == "where"
            and s["payload"].get("day_type") == "Market"
            and not s.get("poison")
            and s["payload"].get("person") == "Mara"
            and s["payload"].get("source") is None
        ):
            vals.append(s["truth"])
    return vals


def _latest_candidate_mara_market(org: Organism) -> str | None:
    truths = _mara_market_from_write_buffer(org)
    return truths[-1] if truths else None


def _write_vault_skill(org: Organism, why: str) -> None:
    if "vault_opener" in org.portable_skills:
        return
    if not org._pay_mutation():
        return
    org.portable_skills["vault_opener"] = {
        "map": {"Market": "Tess", "Field": "Rowan", "Rest": "Tess", "Craft": "Tess"},
        "default": "Tess",
        "metabolism": "Integrated",
    }
    org.developmental_history.append(
        {"change": "skill", "name": "vault_opener", "why": why, "metabolism": "Integrated"}
    )


def _write_clock_skill(org: Organism, why: str) -> None:
    if "clock_maintainer" in org.portable_skills:
        return
    if not org._pay_mutation():
        return
    org.portable_skills["clock_maintainer"] = {"who": "Nyx", "metabolism": "Integrated"}
    org.developmental_history.append(
        {"change": "skill", "name": "clock_maintainer", "why": why, "metabolism": "Integrated"}
    )


def _write_relation(org: Organism, source: str, rel: str, why: str, *, flat: bool = False) -> None:
    if not org._pay_mutation():
        return
    if flat:
        org.rel_flat[("Lark", "Wren")] = rel
        org.rel_beliefs.pop(("Lark", "Wren", "town"), None)
        org.rel_beliefs.pop(("Lark", "Wren", "family"), None)
        org.hidden_contexts.append("family" if rel == "sibling" else "town")
        org.developmental_history.append(
            {"change": "flatten_relation", "rel": rel, "why": why, "metabolism": "Believed"}
        )
    else:
        org.rel_beliefs[("Lark", "Wren", source)] = rel
        org.developmental_history.append(
            {
                "change": "relation",
                "source": source,
                "rel": rel,
                "why": why,
                "metabolism": "Believed",
            }
        )


def _apply_immediate(org: Organism, surprise: dict[str, Any]) -> None:
    name = surprise["name"]
    p = surprise["payload"]
    truth = surprise.get("truth")
    if name == "where" and p.get("person") == "Mara":
        if p.get("source") == "rumor":
            org.living_world["rumor_mara_market"] = truth
            org.integrate_location(("Mara", "Market"), truth, integrated=False, why="immediate-rumor")
            return
        org.integrate_location(("Mara", p["day_type"]), truth, integrated=True, why="immediate")
        return
    if name == "who_opens":
        _write_vault_skill(org, "immediate")
        return
    if name == "clock_maintainer":
        _write_clock_skill(org, "immediate")
        return
    if name == "relation":
        src = p["source"]
        _write_relation(org, src, truth, "immediate", flat=True)
        _write_relation(org, src, truth, "immediate-source", flat=False)


def adapt_A(org: Organism, world: SmallWorld, surprise: dict[str, Any] | None, t: int) -> None:
    return


def adapt_B(org: Organism, world: SmallWorld, surprise: dict[str, Any] | None, t: int) -> None:
    if surprise is None:
        return
    if surprise.get("miss") or surprise.get("recon_used"):
        _apply_immediate(org, surprise)


def adapt_C(org: Organism, world: SmallWorld, surprise: dict[str, Any] | None, t: int) -> None:
    if surprise is not None:
        return
    if t == 0 or (t + 1) % SCHEDULE_EVERY != 0:
        return
    batch = list(org.write_buffer[-SCHEDULE_EVERY * 4 :])
    for s in batch:
        if s.get("miss") or s.get("recon_used"):
            _apply_immediate(org, s)


def _need_fires(org: Organism) -> dict[str, bool]:
    p = org.pressures()
    return {
        "wound": p.prediction_wound >= WOUND_THRESH,
        "vault": org.vault_recon_total >= VAULT_TAX_THRESH,
        "clock": org.clock_recon_total >= CLOCK_TAX_THRESH,
        "strain": p.coherence_strain >= STRAIN_THRESH,
    }


def _need_location_write(
    org: Organism, world: SmallWorld, t: int, *, use_prior: bool, use_witness: bool
) -> None:
    proposed = _latest_candidate_mara_market(org)
    if proposed is None:
        return
    key = ("Mara", "Market")
    current = org.loc_beliefs.get(key, org.initial_locations.get(key))
    if proposed == current:
        return
    candidate = {**org.loc_beliefs, key: proposed}
    regresses = org._prior_body_regresses(candidate) if use_prior else False
    if use_witness:
        persist = sum(1 for loc in _mara_market_from_write_buffer(org) if loc == proposed)
        if persist < WITNESS_RECURRENCE:
            org.store_failed({"kind": "location", "proposed": proposed, "why": "not persistent"})
            return
        ok = org._witness_location(world, "Mara", "Market", proposed, t)
        if ok and regresses:
            org.developmental_history.append(
                {
                    "change": "reversal_allowed_by_witness",
                    "from": current,
                    "to": proposed,
                    "metabolism": "Integrated",
                }
            )
            if current:
                org.store_failed(
                    {"kind": "superseded_body", "location": current, "by": proposed}
                )
        elif not ok:
            org.store_failed({"kind": "location", "proposed": proposed, "why": "witness rejected"})
            return
        elif regresses:
            org.store_failed(
                {"kind": "location", "proposed": proposed, "why": "prior body regression"}
            )
            return
        org.integrate_location(key, proposed, integrated=True, why="need+witness")
        org.maybe_snapshot_stable(t, org.system)
        org.mara_market_misses = 0
        return
    if use_prior and regresses:
        org.store_failed({"kind": "location", "proposed": proposed, "why": "prior body regression"})
        return
    org.integrate_location(key, proposed, integrated=True, why="need")
    org.maybe_snapshot_stable(t, org.system)
    org.mara_market_misses = 0


def _need_skills(org: Organism, *, use_witness: bool) -> None:
    fires = _need_fires(org)
    if fires["vault"]:
        if use_witness:
            if org._witness_recurrence("who_opens", WITNESS_RECURRENCE):
                _write_vault_skill(org, "need+witness")
            else:
                org.store_failed({"kind": "skill", "name": "vault_opener", "why": "witness recurrence"})
        else:
            _write_vault_skill(org, "need")
    if fires["clock"]:
        if use_witness:
            if org._witness_recurrence("clock_maintainer", WITNESS_RECURRENCE):
                _write_clock_skill(org, "need+witness")
            else:
                org.store_failed({"kind": "skill", "name": "clock_maintainer", "why": "one-shot poison"})
        else:
            _write_clock_skill(org, "need")


def _need_relations(org: Organism, world: SmallWorld, t: int, *, use_witness: bool) -> None:
    if not _need_fires(org)["strain"]:
        return
    if use_witness:
        flatten_ok = org._witness_relations(world, t, flatten=True)
        keep_ok = org._witness_relations(world, t, flatten=False)
        rumor_n = sum(
            1
            for s in org.write_buffer
            if s["name"] == "relation" and s["payload"].get("source") == "gossip"
        )
        if rumor_n and rumor_n < WITNESS_RECURRENCE:
            org.store_failed({"kind": "relation", "source": "gossip", "why": "one-shot poison"})
        if keep_ok and not flatten_ok:
            if ("Lark", "Wren", "town") not in org.rel_beliefs:
                _write_relation(org, "town", "sibling", "need+witness", flat=False)
            if ("Lark", "Wren", "family") not in org.rel_beliefs:
                _write_relation(org, "family", "cousin", "need+witness", flat=False)
            if not any(tn.get("id") == "lark-wren" for tn in org.tensions):
                if not org._pay_mutation():
                    return
                org.tensions.append(
                    {
                        "id": "lark-wren",
                        "keep": ["town:sibling", "family:cousin"],
                        "cheaper_than_flatten": True,
                        "metabolism": "Believed",
                    }
                )
            org.relation_conflicts = 0
            return
        org.store_failed({"kind": "flatten", "why": "witness"})
        return
    _write_relation(org, "town", "sibling", "need-flatten", flat=True)
    org.relation_conflicts = 0


def adapt_D(org: Organism, world: SmallWorld, surprise: dict[str, Any] | None, t: int) -> None:
    if surprise is not None:
        return
    fires = _need_fires(org)
    if fires["wound"]:
        _need_location_write(org, world, t, use_prior=False, use_witness=False)
    if fires["vault"] or fires["clock"]:
        _need_skills(org, use_witness=False)
    if fires["strain"]:
        _need_relations(org, world, t, use_witness=False)


def adapt_E(org: Organism, world: SmallWorld, surprise: dict[str, Any] | None, t: int) -> None:
    if surprise is not None:
        return
    fires = _need_fires(org)
    if fires["wound"]:
        _need_location_write(org, world, t, use_prior=True, use_witness=False)
    if fires["vault"] or fires["clock"]:
        _need_skills(org, use_witness=False)
    if fires["strain"]:
        _need_relations(org, world, t, use_witness=False)
    org.maybe_snapshot_stable(t, "E")


def adapt_F(org: Organism, world: SmallWorld, surprise: dict[str, Any] | None, t: int) -> None:
    if surprise is not None:
        return
    fires = _need_fires(org)
    if fires["wound"]:
        _need_location_write(org, world, t, use_prior=True, use_witness=True)
    if fires["vault"] or fires["clock"]:
        _need_skills(org, use_witness=True)
    if fires["strain"]:
        _need_relations(org, world, t, use_witness=True)
    org.maybe_snapshot_stable(t, "F")


ADAPTERS = {
    "A": adapt_A,
    "B": adapt_B,
    "C": adapt_C,
    "D": adapt_D,
    "E": adapt_E,
    "F": adapt_F,
}


def seed_static(org: Organism, world: SmallWorld) -> None:
    for fact in world.static_facts():
        org.append_experience({"t": -1, "name": "static", "payload": fact, "poison": False})
        world.emitted_traces += 1


def ingest_event(org: Organism, world: SmallWorld, event: Event) -> dict[str, Any] | None:
    if event.kind == "observe":
        org.append_experience(
            {
                "t": event.t,
                "name": event.name,
                "payload": event.payload,
                "poison": event.poison,
                "hold_aside": event.hold_aside,
            }
        )
        world.emitted_traces += 1
        return None
    predicted, recon_used, _cost = org.answer(event)
    truth = world.ground_truth(event)
    org.append_experience(
        {
            "t": event.t,
            "name": event.name,
            "kind": "query",
            "payload": dict(event.payload),
            "truth": truth,
            "poison": event.poison,
            "hold_aside": event.hold_aside,
        }
    )
    world.emitted_traces += 1
    return org.record_outcome(event, predicted, truth, recon_used)


def run_system(name: str) -> Organism:
    world = SmallWorld()
    org = Organism(system=name, constitution=FrozenConstitution())
    seed_static(org, world)
    adapt = ADAPTERS[name]
    for t in range(world.n_episodes):
        world.phase = 1 if t < CHANGE_AT else 2
        for event in world.events_at(t):
            surprise = ingest_event(org, world, event)
            adapt(org, world, surprise, t)
        adapt(org, world, None, t)
        if t == CHANGE_AT - 1:
            probe = Event("query", t, "where", {"person": "Mara", "day_type": "Market"})
            org.mid_mara_market_pred = org.predict(probe)
            if name in {"D", "E", "F"}:
                org.maybe_snapshot_stable(t, f"{name}-prechange")
    org.constitution.verify()
    org.emitted_traces = world.emitted_traces
    return org
