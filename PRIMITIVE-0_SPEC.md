# PRIMITIVE-0 SPECIFICATION
## Minimum Machine-Native Cognitive Interchange

**Status:** FROZEN FOR IMPLEMENTATION  
**Version:** 0.1.0  
**Scope:** Determine the minimum internal representation that machines can transfer, store, combine, and reason over without requiring an explicit natural-language intermediate substrate.

---

## 1. Research Question

> What is the cheapest digital primitive that machines can transfer, reason over, store, and combine internally, with natural language generated only at the human boundary?

PRIMITIVE-0 tests the interchange representation only. It does not test digital identity, dimensional memory, GRI geometry, long-term memory architecture, provenance architecture, or consciousness.

---

## 2. Hard Experimental Rules

### 2.1 Semantic specification is not wire specification

```text
SEMANTIC SPEC
what information the primitive can represent and manipulate

            ≠

WIRE SPEC
binary / packed integers / text serialization / tensors / model-native encoding
```

A candidate fails semantically only when it cannot preserve or manipulate information required by the frozen task suite without mandatory external machinery.

Tokenizer inefficiency, binary packing efficiency, and transport encoding are measured separately.

No bit width is frozen in PRIMITIVE-0.

### 2.2 No explicit natural-language intermediate substrate

No explicit natural-language intermediate representation may be emitted, stored, reparsed, or passed between inference stages.

Permitted:

```text
PACKETS → mechanism → PACKETS
```

Forbidden:

```text
PACKET
  ↓
English explanation
  ↓
English reasoning
  ↓
parser
  ↓
PACKET
```

This rule does not make claims about what a neural model internally represents.

### 2.3 Same exam for every candidate

All candidates receive the same fixture semantics, permitted transformations, initial state, and required outputs.

Candidate-specific adapters are allowed only when required to present the same frozen semantics to the candidate. Adapter count, size, training, model calls, and execution cost are measured as part of total system cost.

### 2.4 Total primitive cost includes mandatory external machinery

A primitive is not judged only by packet size.

Any mandatory side channel, schema table, adapter, request protocol, operation table, learned translation matrix, context blob, or special-case semantic mechanism required for correctness counts toward the candidate's total system complexity.

### 2.5 Replayability is measured

Where deterministic behavior is expected:

```text
same packets
same initial state
same mechanism
same seed
→ same packet trajectory
```

For stochastic mechanisms, the experiment must record enough receipt information to reproduce the stochastic trajectory when the implementation supports seeded replay.

Replay failure is recorded independently from task failure.

### 2.6 Frozen benchmark cannot be edited to rescue a candidate

A fixture may be corrected only if the experiment itself is invalid, ambiguous, internally inconsistent, or incorrectly encoded.

A semantic weakness discovered in a candidate does not authorize changing the fixture.

---

## 3. Frozen Candidate Set

### Candidate A

```text
(SUBJECT, RELATION, OBJECT)
```

### Candidate B

```text
(SUBJECT, RELATION, OBJECT, VALUE)
```

### Candidate C

```text
(ACT, SUBJECT, RELATION, OBJECT, VALUE)
```

### Candidate D

```text
(ACT, SUBJECT, RELATION, OBJECT, VALUE, CONFIDENCE)
```

### Candidate E

```text
fixed state vector
```

The vector dimensionality must be declared before the first scored run and may not be changed within that run series.

### Candidate F

```text
latent vector
```

The latent dimensionality, producing model, consuming model, normalization rules, and adapter requirements must be declared.

**Recorded handicap:** latent states may require learned or engineered adapters between model families. Adapter cost is not excluded; it is part of interoperability and total system complexity.

### Candidate G

```text
symbolic + latent
```

Both components and their interaction contract must be declared before a scored run.

---

## 4. Candidate C Prior — Not a Verdict

The current prior is:

```text
ACT | SUBJECT | RELATION | OBJECT | VALUE
```

Example semantic packet:

```text
ASSERT | claim_17 | CONTRADICTS | claim_4 | -720
```

This prior receives no scoring advantage.

`VALUE` is a generic signed scalar. PRIMITIVE-0 does not define it as confidence, truth, salience, probability, or utility. Its meaning may depend on ACT and RELATION.

Candidate D tests whether a distinct confidence field is worth its extra cost.

---

## 5. Frozen Task Suite

### T1 — RELAY

Transfer an input primitive through a mechanism and reproduce the required information without semantic loss.

### T2 — COMPOSE

Combine compatible relations to derive a valid new relation.

### T3 — CONTRADICT

Preserve mutually incompatible assertions without silently collapsing one into the other.

### T4 — UPDATE

Modify an existing operational relation and correctly expose the new current state.

### T5 — REQUEST_RESPONSE

Represent a request directed to another machine and return a semantically distinct response.

### T6 — MULTISTEP_TRANSFORM

Perform repeated primitive transformations across multiple steps without an explicit natural-language intermediate.

### T7 — INFORMATION_COLLISION

Distinguish near-identical primitives whose semantic difference is important.

### T8 — NOVEL_COMBINATION

Use already-known symbols in a combination not present in the fixture examples and produce the required result.

---

## 6. Frozen Metric Groups

No single composite score is authorized in PRIMITIVE-0.

### 6.1 TRANSPORT

- wire bytes transferred
- storage bytes

### 6.2 INFERENCE

- deterministic operations
- model calls
- input tokens
- output tokens
- latency

### 6.3 FIDELITY

- exact reconstruction
- information retained
- collision errors
- error propagation

### 6.4 UTILITY

- task success
- multistep success
- novel composition success

### 6.5 INTEROPERABILITY

Evaluate separately across:

```text
SAME MODEL
SAME FAMILY
DIFFERENT MODEL FAMILY
SYMBOLIC ENGINE
FUTURE / UNKNOWN IMPLEMENTATION
```

Record:

- cross-model compatibility
- cross-architecture compatibility
- symbolic compatibility
- adapter requirements

`FUTURE / UNKNOWN IMPLEMENTATION` is assessed structurally: does the semantic representation have an implementation-independent specification, or does it intrinsically depend on a specific current model representation?

### 6.6 SYSTEM COMPLEXITY

- schema growth
- side channels required
- adapters required
- adapter training required
- external lookup structures required
- special-case task logic required

### 6.7 BOUNDARY TAX

- human → primitive conversion cost
- primitive → human conversion cost

Boundary translation is permitted only at the human boundary and is not permitted as an intermediate reasoning substrate.

### 6.8 REPLAY

- deterministic reproducibility
- stochastic reproducibility from receipt
- trajectory divergence location

---

## 7. Semantic Evaluator Authority

Fixtures use a richer evaluator/oracle format than any candidate. The evaluator format is not a candidate representation and is not counted as candidate machinery.

Its only purposes are:

1. describe the exam unambiguously;
2. define initial state;
3. define permitted transformations;
4. define required output semantics;
5. evaluate candidate results.

A candidate is never required to copy the evaluator schema internally.

---

## 8. Side-Channel Accounting Rule

For every candidate and every task, record:

```text
REQUIRED_SIDE_CHANNELS = []
```

If a candidate cannot complete a task without adding information outside its declared primitive, each added mechanism must be listed.

Examples:

```text
intent side channel
speaker side channel
confidence table
operation table
request/response wrapper
learned latent adapter
hidden context vector
task-specific rule
```

If a side channel is required for semantics, it counts as part of the candidate system.

---

## 9. Candidate Modification Rule

A candidate may be repaired only by creating a versioned variant.

Example:

```text
C0 = ACT,S,R,O,V
C1 = ACT,S,R,O,V + TYPE
```

C0 results remain preserved.

A repair does not retroactively change the frozen candidate.

This is the PRIMITIVE-0 application of Exhaustion Before Abandonment: failures are localized before a candidate is expanded.

---

## 10. Experiment Validity

The following produce:

```text
EXPERIMENT_INVALID
```

not candidate failure:

- fixture mismatch
- seed mismatch where seed equality is required
- evaluator bug
- implementation bug that prevents the candidate from expressing its declared semantics
- accidental natural-language intermediate leakage
- benchmark mutation after candidate results were observed
- hidden side channel not accounted for
- unequal fixture semantics across candidates
- unrecorded adapter
- stochastic run lacking required receipt data

An invalid run cannot be converted into `FAIL`, `INSUFFICIENT`, or a scientific conclusion.

---

## 11. PRIMITIVE-0 Completion Condition

PRIMITIVE-0 is complete only when all frozen candidates A–G have been run against T1–T8 under the same frozen fixtures, or when a candidate is formally recorded as unable to instantiate the required experiment and that inability itself is documented.

The experiment may conclude:

```text
CLEAR_WINNER_WITHIN_TESTED_SCOPE
TRADEOFF_FRONTIER
NO_SINGLE_WINNER
ALL_CANDIDATES_INSUFFICIENT
EXPERIMENT_INCOMPLETE
```

No result may claim a universal cognitive primitive.

---

## 12. Explicitly Parked Work

Not authorized inside PRIMITIVE-0:

- H-DM-01 identity continuity
- H-DM-02 operational forgetting
- dimensional memory
- memory tiers
- GRI geometry
- curvature
- E8
- long-term provenance architecture
- model selfhood
- consciousness claims
- ENCODING-0 bit-width optimization

The follow-on encoding study is separate:

```text
ENCODING-0
fixed width
variable integers
dictionary coding
delta coding
packed batches
other encodings
```

Only after PRIMITIVE-0 establishes which semantic candidates remain worth encoding.

---

## 13. Follow-On Question

PRIMITIVE-1 is not authorized until PRIMITIVE-0 is complete.

Its question is:

> Can repeated machine-native state transformations perform useful multi-step inference without an explicit natural-language intermediate substrate?
