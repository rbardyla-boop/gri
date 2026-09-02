"""One small symbolic world: people, relations, locations, query cost.

Four conditions:
1. Recurring prediction failure (Mara on Market days).
2. Repeated expensive reconstruction (who opens the vault).
3. Genuine unresolved contradiction (Lark–Wren town vs family) — must not flatten.
4. One-shot poison dressed as each of the three — ignore.

Mid-run the Market regularity reverses (greenhouse → river).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DAY_TYPES = ("Market", "Field", "Rest", "Craft")
N_EPISODES = 80
CHANGE_AT = 40
POISON_TOWER_T = 6
POISON_CLOCK_T = 9
POISON_GOSSIP_T = 13

EventKind = Literal["observe", "query"]


@dataclass(frozen=True)
class Event:
    kind: EventKind
    t: int
    name: str
    payload: dict[str, Any]
    poison: bool = False
    hold_aside: bool = False


@dataclass
class SmallWorld:
    """Deterministic people / relations / locations. No network, no GPU."""

    n_episodes: int = N_EPISODES
    change_at: int = CHANGE_AT
    phase: int = 1
    emitted_traces: int = 0
    log: list[Event] = field(default_factory=list)

    def day_type(self, t: int) -> str:
        return DAY_TYPES[t % 4]

    def mara_location(self, t: int) -> str:
        dt = self.day_type(t)
        if dt == "Market":
            return "greenhouse" if t < self.change_at else "river"
        if dt == "Field":
            return "mill"
        if dt == "Rest":
            return "home"
        return "greenhouse"

    def vault_opener(self, t: int) -> str:
        return "Rowan" if self.day_type(t) == "Field" else "Tess"

    def ground_truth(self, event: Event) -> Any:
        p = event.payload
        name = event.name
        t = event.t
        if name == "where":
            if p.get("source") == "rumor":
                return "tower"
            return self.mara_location(t) if p["person"] == "Mara" else "unknown"
        if name == "who_opens":
            return self.vault_opener(t)
        if name == "relation":
            src = p["source"]
            if src == "town":
                return "sibling"
            if src == "family":
                return "cousin"
            if src == "gossip":
                return "parent"
            return "unknown"
        if name == "clock_maintainer":
            return "Nyx"
        return "unknown"

    def static_facts(self) -> list[dict[str, Any]]:
        return [
            {"s": "vault", "rel": "located_at", "o": "greenhouse"},
            {"s": "greenhouse", "rel": "keyed_to", "o": "gardener"},
            {"s": "Tess", "rel": "role", "o": "gardener"},
            {"s": "Rowan", "rel": "role", "o": "deputy"},
            {"s": "Tess", "rel": "away_on", "o": "Field"},
            {"s": "Tess", "rel": "at_when_away", "o": "mill"},
        ]

    def clock_chain(self) -> list[dict[str, Any]]:
        return [
            {"s": "clock", "rel": "located_at", "o": "tower"},
            {"s": "tower", "rel": "keyed_to", "o": "horologist"},
            {"s": "horologist", "rel": "guild", "o": "mill-gear"},
            {"s": "mill-gear", "rel": "lead", "o": "Nyx"},
            {"s": "Nyx", "rel": "role", "o": "horologist"},
            {"s": "clock", "rel": "needs", "o": "winding"},
            {"s": "winding", "rel": "done_by_role", "o": "horologist"},
        ]

    def events_at(self, t: int) -> list[Event]:
        dt = self.day_type(t)
        hold = dt == "Market" and (t % 8 == 4)
        out: list[Event] = []

        out.append(
            Event(
                "observe",
                t,
                "at",
                {"person": "Mara", "location": self.mara_location(t), "day_type": dt},
                hold_aside=hold,
            )
        )
        out.append(
            Event(
                "query",
                t,
                "where",
                {"person": "Mara", "day_type": dt},
                hold_aside=hold,
            )
        )

        if dt in ("Market", "Field", "Rest"):
            out.append(Event("query", t, "who_opens", {"thing": "vault", "day_type": dt}))

        if dt == "Craft":
            out.append(
                Event(
                    "query",
                    t,
                    "relation",
                    {"a": "Lark", "b": "Wren", "source": "town"},
                )
            )
        if dt == "Rest":
            out.append(
                Event(
                    "query",
                    t,
                    "relation",
                    {"a": "Lark", "b": "Wren", "source": "family"},
                )
            )

        if t == POISON_TOWER_T:
            out.append(
                Event(
                    "observe",
                    t,
                    "at",
                    {
                        "person": "Mara",
                        "location": "tower",
                        "day_type": "Market",
                        "source": "rumor",
                    },
                    poison=True,
                )
            )
            out.append(
                Event(
                    "query",
                    t,
                    "where",
                    {"person": "Mara", "day_type": "Market", "source": "rumor"},
                    poison=True,
                )
            )
        if t == POISON_CLOCK_T:
            out.append(
                Event("observe", t, "clock_chain", {"facts": self.clock_chain()}, poison=True)
            )
            out.append(
                Event("query", t, "clock_maintainer", {"thing": "clock"}, poison=True)
            )
        if t == POISON_GOSSIP_T:
            out.append(
                Event(
                    "observe",
                    t,
                    "relation",
                    {"a": "Lark", "b": "Wren", "rel": "parent", "source": "gossip"},
                    poison=True,
                )
            )
            out.append(
                Event(
                    "query",
                    t,
                    "relation",
                    {"a": "Lark", "b": "Wren", "source": "gossip"},
                    poison=True,
                )
            )
        self.log.extend(out)
        return out
