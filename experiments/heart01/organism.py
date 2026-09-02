"""Organism state, metabolism, prediction, reconstruction, gated mutation.

Need grants compute, not truth. Budget is not a truth selector.
Prior body = lineage regression. World witness = correspondence outside lineage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from experiments.heart01.constitution import ConstitutionError, FrozenConstitution
from experiments.heart01.world import Event, SmallWorld

STATE_KEYS = (
    "constitution",
    "immutable_experience",
    "living_world",
    "beliefs_and_tensions",
    "portable_skills",
    "developmental_history",
    "failed_adaptations",
    "prior_stable_bodies",
    "core_specific_residues",
    "reconstruction_recipe",
)


@dataclass
class Pressures:
    prediction_wound: int = 0
    reconstruction_tax: int = 0
    coherence_strain: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "prediction_wound": self.prediction_wound,
            "reconstruction_tax": self.reconstruction_tax,
            "coherence_strain": self.coherence_strain,
        }


@dataclass
class Organism:
    system: str
    constitution: FrozenConstitution
    initial_locations: dict[tuple[str, str], str] = field(default_factory=dict)
    loc_beliefs: dict[tuple[str, str], str] = field(default_factory=dict)
    loc_integrated: set[tuple[str, str]] = field(default_factory=set)
    rel_beliefs: dict[tuple[str, str, str], str] = field(default_factory=dict)
    rel_flat: dict[tuple[str, str], str] = field(default_factory=dict)
    tensions: list[dict[str, Any]] = field(default_factory=list)
    portable_skills: dict[str, dict[str, Any]] = field(default_factory=dict)
    living_world: dict[str, Any] = field(default_factory=dict)
    immutable_experience: list[dict[str, Any]] = field(default_factory=list)
    developmental_history: list[dict[str, Any]] = field(default_factory=list)
    failed_adaptations: list[dict[str, Any]] = field(default_factory=list)
    prior_stable_bodies: list[dict[str, Any]] = field(default_factory=list)
    core_specific_residues: dict[str, Any] = field(default_factory=dict)
    hidden_contexts: list[str] = field(default_factory=list)
    mutations: int = 0
    queries_paid: int = 0
    compute_units: int = 0
    pred_cost: int = 0
    recon_cost: int = 0
    mara_market_misses: int = 0
    vault_recon_total: int = 0
    clock_recon_total: int = 0
    relation_conflicts: int = 0
    witness_holdout_used: int = 0
    witness_post_query_used: int = 0
    witness_included_hard_evidence: int = 0
    mid_mara_market_pred: str | None = None
    traces_hold_aside: list[dict[str, Any]] = field(default_factory=list)
    write_buffer: list[dict[str, Any]] = field(default_factory=list)
    emitted_traces: int = 0

    def __post_init__(self) -> None:
        if not self.initial_locations:
            self.initial_locations = {
                ("Mara", "Market"): "market",
                ("Mara", "Field"): "mill",
                ("Mara", "Rest"): "home",
                ("Mara", "Craft"): "greenhouse",
            }
        self.living_world = {
            "people": ["Mara", "Tess", "Rowan", "Lark", "Wren", "Nyx"],
            "locations": ["greenhouse", "market", "river", "tower", "vault", "mill", "home"],
        }
        self.core_specific_residues = {}

    def reconstruction_recipe(self) -> dict[str, Any]:
        return {
            "method": "rebuild_beliefs_from_portable_life",
            "steps": [
                "load constitution unchanged",
                "scan immutable_experience (append-only traces)",
                "re-apply portable_skills as compression, not as truth",
                "restore beliefs_and_tensions; keep tensions cheaper than flatten",
                "do not revive failed_adaptations as live beliefs",
                "prior_stable_bodies remain lineage regression detectors",
            ],
        }

    def to_state(self) -> dict[str, Any]:
        self.constitution.verify()
        return {
            "constitution": self.constitution.as_dict(),
            "immutable_experience": list(self.immutable_experience),
            "living_world": dict(self.living_world),
            "beliefs_and_tensions": {
                "believed_locations": {f"{k[0]}|{k[1]}": v for k, v in self.loc_beliefs.items()},
                "integrated_locations": [f"{k[0]}|{k[1]}" for k in sorted(self.loc_integrated)],
                "believed_relations": {
                    f"{k[0]}|{k[1]}|{k[2]}": v for k, v in self.rel_beliefs.items()
                },
                "flattened_relations": {f"{k[0]}|{k[1]}": v for k, v in self.rel_flat.items()},
                "tensions": list(self.tensions),
            },
            "portable_skills": dict(self.portable_skills),
            "developmental_history": list(self.developmental_history),
            "failed_adaptations": list(self.failed_adaptations),
            "prior_stable_bodies": list(self.prior_stable_bodies),
            "core_specific_residues": dict(self.core_specific_residues),
            "reconstruction_recipe": self.reconstruction_recipe(),
        }

    def append_experience(self, trace: dict[str, Any]) -> None:
        self.constitution.verify()
        trace = dict(trace)
        trace["metabolism"] = "Experienced"
        self.immutable_experience.append(trace)

    def _pay_query(self) -> None:
        self.queries_paid += 1
        self.compute_units += 1
        if self.queries_paid > self.constitution.ceiling("queries"):
            raise ConstitutionError("query ceiling exceeded")
        if self.compute_units > self.constitution.ceiling("compute_units"):
            raise ConstitutionError("compute ceiling exceeded")

    def _pay_mutation(self) -> bool:
        if self.mutations >= self.constitution.ceiling("mutations"):
            return False
        self.mutations += 1
        self.compute_units += 2
        if self.compute_units > self.constitution.ceiling("compute_units"):
            self.mutations -= 1
            return False
        return True

    def reject_outward(self, action: dict[str, Any]) -> None:
        kind = str(action.get("kind") or action.get("type") or "")
        if kind in {"outward", "send", "email", "http", "purchase", "post"}:
            raise ConstitutionError("outward actions forbidden")

    def predict(self, event: Event) -> Any:
        name = event.name
        p = event.payload
        if name == "where":
            if p.get("source") == "rumor":
                if self.living_world.get("rumor_mara_market") == "tower":
                    return "tower"
                if self.loc_beliefs.get(("Mara", "Market")) == "tower":
                    return "tower"
            key = (p["person"], p["day_type"])
            if key in self.loc_beliefs:
                return self.loc_beliefs[key]
            return self.initial_locations.get(key, "unknown")
        if name == "who_opens":
            skill = self.portable_skills.get("vault_opener")
            if skill:
                dt = p["day_type"]
                return skill["map"].get(dt, skill.get("default", "unknown"))
            return None
        if name == "clock_maintainer":
            skill = self.portable_skills.get("clock_maintainer")
            if skill:
                return skill.get("who", "unknown")
            return None
        if name == "relation":
            a, b, src = p["a"], p["b"], p["source"]
            if (a, b, src) in self.rel_beliefs:
                return self.rel_beliefs[(a, b, src)]
            if (a, b) in self.rel_flat:
                return self.rel_flat[(a, b)]
            return "unknown"
        return "unknown"

    def reconstruct(self, event: Event) -> tuple[Any, int]:
        name = event.name
        scanned = len(self.immutable_experience)
        if name == "who_opens":
            dt = event.payload["day_type"]
            opener = "Rowan" if dt == "Field" else "Tess"
            return opener, scanned + 5
        if name == "clock_maintainer":
            who = "unknown"
            extra = 0
            for tr in self.immutable_experience:
                if tr.get("name") == "clock_chain":
                    extra = len(tr.get("payload", {}).get("facts") or [])
                    who = "Nyx"
            return who, scanned + max(extra, 7)
        if name == "relation":
            src = event.payload["source"]
            found = "unknown"
            for tr in reversed(self.immutable_experience):
                if tr.get("name") == "relation" and (tr.get("payload") or {}).get("source") == src:
                    found = (tr.get("payload") or {}).get("rel") or found
                    break
            return found, scanned
        if name == "where":
            p = event.payload
            for tr in reversed(self.immutable_experience):
                pay = tr.get("payload") or {}
                if tr.get("name") == "at" and pay.get("person") == p["person"]:
                    if pay.get("day_type") == p["day_type"] and pay.get("source") == p.get("source"):
                        return pay.get("location"), scanned
            return "unknown", scanned
        return "unknown", scanned

    def answer(self, event: Event) -> tuple[Any, bool, int]:
        self._pay_query()
        pred = self.predict(event)
        recon_used = False
        cost_r = 0
        if pred is None:
            pred, cost_r = self.reconstruct(event)
            recon_used = True
            self.recon_cost += cost_r
            if event.name == "who_opens":
                self.vault_recon_total += cost_r
            if event.name == "clock_maintainer":
                self.clock_recon_total += cost_r
        return pred, recon_used, cost_r

    def record_outcome(
        self, event: Event, predicted: Any, truth: Any, recon_used: bool
    ) -> dict[str, Any]:
        miss = predicted != truth
        if miss:
            self.pred_cost += 1
            if (
                event.name == "where"
                and event.payload.get("day_type") == "Market"
                and event.payload.get("person") == "Mara"
                and not event.poison
                and event.payload.get("source") is None
            ):
                self.mara_market_misses += 1
        surprise = {
            "t": event.t,
            "name": event.name,
            "payload": event.payload,
            "predicted": predicted,
            "truth": truth,
            "miss": miss,
            "poison": event.poison,
            "hold_aside": event.hold_aside,
            "recon_used": recon_used,
        }
        if event.hold_aside:
            self.traces_hold_aside.append(surprise)
        else:
            self.write_buffer.append(surprise)
        if event.name == "relation" and not event.poison:
            seen_town = any(
                (tr.get("name") == "relation" and (tr.get("payload") or {}).get("source") == "town")
                for tr in self.immutable_experience
            )
            seen_family = any(
                (tr.get("name") == "relation" and (tr.get("payload") or {}).get("source") == "family")
                for tr in self.immutable_experience
            )
            both_kept = ("Lark", "Wren", "town") in self.rel_beliefs and (
                "Lark",
                "Wren",
                "family",
            ) in self.rel_beliefs
            if seen_town and seen_family and not self.tensions and not both_kept:
                self.relation_conflicts += 1
        return surprise

    def pressures(self) -> Pressures:
        return Pressures(
            self.mara_market_misses,
            self.vault_recon_total + self.clock_recon_total,
            self.relation_conflicts,
        )

    def _snapshot_body(self, label: str) -> dict[str, Any]:
        return {
            "label": label,
            "loc_beliefs": {f"{k[0]}|{k[1]}": v for k, v in self.loc_beliefs.items()},
            "rel_beliefs": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in self.rel_beliefs.items()},
            "skills": list(self.portable_skills.keys()),
        }

    def _prior_body_regresses(self, candidate_loc: dict[tuple[str, str], str]) -> bool:
        if not self.prior_stable_bodies:
            return False
        prior = self.prior_stable_bodies[-1]
        for raw, loc in prior.get("loc_beliefs", {}).items():
            person, dt = raw.split("|", 1)
            key = (person, dt)
            if key in candidate_loc and candidate_loc[key] != loc:
                return True
        return False

    def _witness_location(
        self, world: SmallWorld, person: str, day_type: str, proposed: str, t: int
    ) -> bool:
        """Correspondence outside lineage: holdouts unused in the write, then a post-candidate query."""
        self.witness_holdout_used += 1
        hold = [
            h
            for h in self.traces_hold_aside
            if h["name"] == "where"
            and h["payload"].get("person") == person
            and h["payload"].get("day_type") == day_type
            and not h.get("poison")
        ]
        hold_ok = True
        if hold:
            hold_ok = all(proposed == h["truth"] for h in hold[-3:])
        self.witness_post_query_used += 1
        probe = Event("query", t, "where", {"person": person, "day_type": day_type})
        self._pay_query()
        truth = world.ground_truth(probe)
        self.witness_included_hard_evidence += 1
        return hold_ok and truth == proposed

    def _witness_recurrence(self, name: str, min_n: int) -> bool:
        self.witness_holdout_used += 1
        n = sum(
            1
            for s in self.write_buffer + self.traces_hold_aside
            if s.get("name") == name and not s.get("poison")
        )
        return n >= min_n

    def _witness_relations(self, world: SmallWorld, t: int, flatten: bool) -> bool:
        """Flattening must still face family AND town outcomes. Hiding is not cheaper."""
        self.witness_included_hard_evidence += 1
        self.witness_post_query_used += 1
        town_e = Event("query", t, "relation", {"a": "Lark", "b": "Wren", "source": "town"})
        fam_e = Event("query", t, "relation", {"a": "Lark", "b": "Wren", "source": "family"})
        self._pay_query()
        self._pay_query()
        town_t = world.ground_truth(town_e)
        fam_t = world.ground_truth(fam_e)
        if flatten:
            return town_t == fam_t
        return town_t == "sibling" and fam_t == "cousin"

    def integrate_location(
        self, key: tuple[str, str], value: str, *, integrated: bool, why: str
    ) -> bool:
        if not self._pay_mutation():
            return False
        old = self.loc_beliefs.get(key)
        self.loc_beliefs[key] = value
        if integrated:
            self.loc_integrated.add(key)
        self.developmental_history.append(
            {
                "change": "location",
                "key": list(key),
                "old": old,
                "new": value,
                "why": why,
                "metabolism": "Integrated" if integrated else "Believed",
            }
        )
        return True

    def store_failed(self, adaptation: dict[str, Any]) -> None:
        adaptation = dict(adaptation)
        adaptation.setdefault("retained", True)
        self.failed_adaptations.append(adaptation)

    def maybe_snapshot_stable(self, t: int, label: str) -> None:
        key = ("Mara", "Market")
        if key in self.loc_integrated and self.loc_beliefs.get(key) in {"greenhouse", "river"}:
            snap = self._snapshot_body(f"{label}@t{t}")
            if (
                not self.prior_stable_bodies
                or self.prior_stable_bodies[-1].get("loc_beliefs") != snap["loc_beliefs"]
            ):
                self.prior_stable_bodies.append(snap)
