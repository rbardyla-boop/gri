# WILDFLOWER current capability map

Status: post-320 development diagnostic. This is a local evidence map, not a
qualification or architecture-success claim.

Evidence basis:

- immutable 320-R3 artifact: `artifacts/development_seed320.json`;
- engineering-only alternate-support scenarios using both store
  implementations;
- engineering history/correction benchmark through 1,000,000 retained
  events;
- source and contract tests, with no scientific seed rerun.

## Demonstrated

- Local contradiction rollback. R3 removed `0/9555` false durable claims and
  recovered `2287/2287` rollback opportunities.
- Transitive provenance replacement. R3 reconstructed `4453/4453` Metric-B
  opportunities with global precision and recall of `1.0`.
- Machine-native justification lineage. R3 recorded `2144` same-semantics,
  changed-lineage events with distinct support identities.
- Deterministic replay. The production store and R3 artifact both report
  deterministic replay true.
- Bounded active state. R3 stayed below the `8192` active-claim bound; the
  maximum observed production challenge state was `4147` claims and `4900`
  active supports.
- Selective dirty-cone correction. In the scaling adversary, Dual Authority
  visited one claim and one support per single correction while flat
  recomputation scanned every retained event.
- Independent control framework. Seven mechanisms consumed the same recorded
  stream with independent state. The flat recompute control was not given
  fake provenance capability.
- Provenance queries. The store can answer current justification, grounded
  lineage, dependent-support, surviving-independent-path, and
  regenerated-versus-preserved questions through explicit support metadata.
- Practical correction crossover in the local benchmark. Flat scanning was
  faster at 100 and 1,000 retained events; Dual Authority was faster at
  10,000, 100,000, and 1,000,000 events for the tested correction prefixes.

## Demonstrated only in synthetic tests

- Alternate-support continuous preservation. A production-shaped engineering
  case with two independent derived supports produced exactly `1/1` Metric-A
  preservation, with the bad path ungrounded, the good path grounded, and the
  claim continuously committed without recomputation. A 100-case engineering
  scale test produced `100/100` in both Reference and Incremental stores.
- Canonical duplicate reuse. Contract tests demonstrate that identical packet,
  semantic-parent, and lineage inputs reuse one support ID, while changed
  lineage creates a new support ID. R3 itself observed no duplicate-reuse
  opportunities: `19110` insertion attempts produced `19110` creations and
  zero reuses.
- Multiple independent grounded lineage paths and selective impact queries.

## Not yet demonstrated

- A meaningful scientific Metric-A result. R3 had `0` opportunities because
  each scored tick emits only one derived support per relation/parity claim;
  no alternate derived support exists before the witness. The artifact stores
  the transition-stream count/hash, not the full stream, so a per-transition
  historical audit cannot be reconstructed without rerunning.
- Reliable raw perception.
- General world modeling.
- Linguistic abstraction.
- Long-lived autonomous development.
- Usefulness beyond toy numeric worlds.
- Superiority to simple recomputation at every workload. Dual Authority adds
  provenance and selective-update capability, but the flat control ties its
  R3 safety outcome and is faster on short histories.
- Predictive authority passing all frozen gates. R3 missed H8 maximum by
  `0.0000806700` (`1.0000806700` versus the `1.00` limit).

## Metric-A diagnosis

The zero denominator is primarily a challenge-design insufficiency, appearing
as an actual absence of redundant derived evidence in this environment. It is
not supported as a seed-specific chance event, canonicalization side effect,
metric implementation defect, or representation limitation:

- R3 had `4453` invalidated-and-recomputed derived opportunities, but zero
  pre-existing alternate-support opportunities.
- Final per-episode inventories had `970`, `513`, and `661` claims with more
  than one effective support, but zero claims with more than one grounded
  support. These are replacement/provenance states, not continuous alternate
  support before a witness.
- Canonicalization recorded zero reuses, and the contract tests preserve
  distinct changed-lineage identities.
- The scorer explicitly requires the alternate support to be grounded both
  before and after the witness; it would count the engineering diamond case.

## Flat recomputation versus Dual Authority

The registered `WITNESS_PLUS_RECOMPUTE_NO_DAG` replay applies an evaluator-
supplied recomputed stream, so its R3 replay time is not an end-to-end cost for
generating that recomputation. The honest scaling adversary measured the
history scan itself.

For correction prefixes `1/10/100/1000`, flat correction work was
`history_size * corrections`; the Dual harness performed four dirty-cone
visits per toggle, with zero history revisits. Flat was faster at 100 and
1,000 events because of fixed store overhead. Dual was faster at 10,000 events
and above. Both reached the expected final state in every tested case.

Dual Authority additionally answered provenance and selective-rollback
queries. The flat mechanism stores committed values only; answering those
questions requires reconstructing dependency and lineage bookkeeping, which
is effectively reintroducing a DAG.

## Potential future use

- Lifetime episodic or semantic memory.
- Belief revision after corrected observations.
- Provenance-aware agents.
- Local AI knowledge maintenance.
- Auditable machine reasoning.
- Context-window reduction through structured state.
- Scientific and technical agent memory.
- Autonomous systems that must revise beliefs after sensor corrections.

These are potential uses, not demonstrated capabilities.

## Decision gate

**B. CREATE 0.3 CHALLENGE REPAIR.**

Do not run 321 unchanged. The current challenge is structurally incapable of
providing the preregistered Metric-A denominator, while the mechanism passes
the synthetic preservation contract, transitive Metric B, safety, and the
large-history correction benchmark. A successor should add an explicit,
pre-registered alternate-evidence challenge and define its opportunity
denominator before any new scientific seed is authorized.

