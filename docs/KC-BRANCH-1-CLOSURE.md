# KC-BRANCH-1-CLOSURE — Direct-Mapped Broadcast Knowledge Cells

## Status

```text
KC-1A → KC-4B DEVELOPMENT CHAIN: COMPLETE
KC-BRANCH-1: ARCHIVED / CLOSED
NEXT KC UNIT: NONE AUTHORIZED
SCIENTIFIC VERDICT: NONE / FORBIDDEN
```

This record closes the first KC mechanics branch. It does not authorize
`KC-4C`, a routing redesign, a population extension, or an AI-utility claim.

## What the branch established

The development chain made the following bounded capabilities executable and
replayable around the unchanged KC-1A cell:

```text
bounded local cell state
exact serialization and restart
oracle-free state export
two-cell transfer and cooperative overflow
bounded child inheritance
bounded population lifecycle
local multi-hop knowledge propagation
bounded whole-population ticks
deterministic finite-horizon trajectories
scheduler/contact-order counterfactuals
```

These are engineering/development results. They establish neither learning,
semantic knowledge, better AI answers, nor scientific utility.

## What failed

KC-4A first compared eight KC-1A cells × eight slots with a simple centralized
64-slot baseline under the same declared 64 logical positions and 1024 state
bytes. At 64 packet pressure, KC retained 8/64 identities while the baseline
retained 64/64.

KC-4B then froze the full capacity/redundancy frontier and compared unchanged
KC-3D propagation with an equally redundant static 64-address baseline. The
KC no-failure trajectory was:

| intended copies per identity | unique identities at t0 | unique identities after four ticks |
| ---: | ---: | ---: |
| 1 | 64 | 8 |
| 2 | 32 | 8 |
| 4 | 16 | 8 |
| 8 | 8 | 8 |

The KC-4B runner covered 68 cases: four no-failure profiles and every one of
the eight cell losses both before and after the four-tick horizon. Anchors,
resource equality, runtime bounds, restart, replay, and non-scientific
fail-closed checks passed. The negative utility observation remains bounded to
these exact fixtures, scheduler, propagation rule, population, and horizon.

Therefore, within the tested scope, this implementation is:

```text
capacity-efficient:       NO
redundancy-controllable:   NO
general-memory advantage:  NOT ESTABLISHED
scientific verdict:        NONE / FORBIDDEN
```

## Mechanistic interpretation

The observed failure is consistent with the interaction of:

```text
eight direct-mapped logical slot classes
+ broadcast/local parent-child propagation
+ same-slot last-write-wins collisions
→ distributed diversity becomes replicated winners
```

The data support this as the operative mechanism in the tested branch. They
do not prove that every possible distributed cell protocol has an eight-item
limit.

## Evidence anchors

```text
KC-4A fixtures:
527fa3c2230c16475629d2f4b444bfc2d934b707815d67aee532c91f0079a5f5

KC-4A benchmark:
28a7f737a63d847acc0f9ee72a399bb54593e4633768457e55773e5714bd06cf

KC-4A receipt:
ab208ee5ca4b73c393ecf409ec775d148fd7f6f1f97bbd854dba819ca1114ebb

KC-4B fixtures:
6ab5b3dd87537fae5edac5f298e221c9ade24a91885417c19ca4c7ab2a881642

KC-4B benchmark:
ae7f4b3300440dd2daa00182c2d580bec3ad6b3304e0e68666c212005c2d8a1a

KC-4B receipt:
a0552d5f10030a5fdcd18ead414484e86011979e23a6a6e21685056c7b23b84a
```

## Reopen rule

This branch may be reopened only by a separately authorized branch with a
genuinely different local collision-routing hypothesis. It must attack the
observed diversity collapse directly and remain inside the existing total
budget:

```text
total state budget: 1024 bytes
central packet map: forbidden
global routing table: forbidden
hidden history: forbidden
unbounded probing: forbidden
automatic population growth: forbidden
```

The first go/no-go target must be materially more than 8 of 64 recoverable
identities under the same budget and a frozen adversarial collision bank. A
scheduler tweak, longer horizon, additional cells, or cosmetic parameter
change is not a new hypothesis and does not reopen this branch.
