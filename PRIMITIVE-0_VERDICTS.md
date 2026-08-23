# PRIMITIVE-0 VERDICTS
## Frozen Verdict Contract and Results Template

**Version:** 0.1.0  
**Status:** FROZEN TEMPLATE — NO RESULTS YET

---

## 1. Run-Level Execution Verdict

Every scored run must first receive one execution verdict.

```text
RUN_VALID
EXPERIMENT_INVALID
```

`EXPERIMENT_INVALID` is not evidence for or against a candidate.

### Invalid-run causes

Record one or more:

```text
FIXTURE_MISMATCH
SEED_MISMATCH
EVALUATOR_ERROR
IMPLEMENTATION_ERROR
NATURAL_LANGUAGE_LEAK
BENCHMARK_MUTATION
HIDDEN_SIDE_CHANNEL
UNEQUAL_CANDIDATE_INPUT
UNRECORDED_ADAPTER
REPLAY_RECEIPT_MISSING
OTHER
```

---

## 2. Task-Level Semantic Verdict

For each valid candidate × task result:

```text
PASS
PARTIAL
FAIL
NOT_INSTANTIABLE
```

Definitions:

### PASS

Required semantic output is produced with no unaccounted machinery.

### PARTIAL

Some required semantics survive, but at least one required distinction, transformation, or output is incomplete.

### FAIL

The candidate system produces an incorrect semantic result.

### NOT_INSTANTIABLE

The declared candidate cannot be meaningfully instantiated for the task without changing the frozen candidate definition.

Mandatory external machinery may convert an apparent `NOT_INSTANTIABLE` case into a runnable system, but all such machinery must be counted under SYSTEM COMPLEXITY.

---

## 3. Failure Classification

A non-pass result must be classified where possible:

```text
REPRESENTATIONAL_INSUFFICIENCY
INFERENCE_FAILURE
INFORMATION_COLLISION
UPDATE_AMBIGUITY
INTENT_AMBIGUITY
COMPOSITION_FAILURE
INTEROPERABILITY_FAILURE
REPLAY_FAILURE
ADAPTER_FAILURE
SCHEMA_EXPLOSION
SIDE_CHANNEL_DEPENDENCE
BOUNDARY_TRANSLATION_FAILURE
OTHER
```

This classification is descriptive, not a new score.

---

## 4. Candidate Evidence Record

Use one record per candidate.

```text
CANDIDATE:
VERSION:
MECHANISM:
MODEL / ENGINE:
SEED POLICY:
DECLARED REPRESENTATION:
DECLARED ADAPTERS:
DECLARED SIDE CHANNELS:
DECLARED EXTERNAL TABLES:
```

### Task Results

| Task | Verdict | Failure class | Required side channels | Notes |
|---|---|---|---|---|
| T1 RELAY | UNRUN | — | — | — |
| T2 COMPOSE | UNRUN | — | — | — |
| T3 CONTRADICT | UNRUN | — | — | — |
| T4 UPDATE | UNRUN | — | — | — |
| T5 REQUEST_RESPONSE | UNRUN | — | — | — |
| T6 MULTISTEP_TRANSFORM | UNRUN | — | — | — |
| T7 INFORMATION_COLLISION | UNRUN | — | — | — |
| T8 NOVEL_COMBINATION | UNRUN | — | — | — |

### TRANSPORT

```text
wire_bytes_total:
wire_bytes_per_packet:
storage_bytes_total:
```

### INFERENCE

```text
deterministic_operations:
model_calls:
input_tokens:
output_tokens:
latency_measurement:
```

### FIDELITY

```text
exact_reconstruction:
information_retained:
collision_errors:
error_propagation:
```

### UTILITY

```text
tasks_passed:
multistep_success:
novel_combination_success:
```

### INTEROPERABILITY

```text
same_model:
same_family:
different_model_family:
symbolic_engine:
future_unknown_structural_portability:
```

### SYSTEM COMPLEXITY

```text
schema_growth:
side_channels_required:
adapters_required:
adapter_training_required:
external_lookup_structures:
special_case_logic:
```

### BOUNDARY TAX

```text
human_to_primitive:
primitive_to_human:
```

### REPLAY

```text
deterministic_replay:
stochastic_replay_from_receipt:
first_divergence:
```

---

## 5. Candidate-Level Interpretation

Candidate-level interpretations may use:

```text
SEMANTICALLY_SUFFICIENT_WITHIN_TESTED_SCOPE
SEMANTICALLY_INSUFFICIENT_WITHIN_TESTED_SCOPE
SUFFICIENT_WITH_EXTERNAL_MACHINERY
MIXED
INSUFFICIENT_EVIDENCE
```

These are interpretations of the metric vector, not replacements for raw results.

No candidate receives a single scalar score in PRIMITIVE-0.

---

## 6. Experiment-Level Terminal Verdict

After all candidates have completed the frozen exam:

```text
CLEAR_WINNER_WITHIN_TESTED_SCOPE
TRADEOFF_FRONTIER
NO_SINGLE_WINNER
ALL_CANDIDATES_INSUFFICIENT
EXPERIMENT_INCOMPLETE
```

### CLEAR_WINNER_WITHIN_TESTED_SCOPE

One candidate is not merely smallest on one metric; it dominates the relevant tested alternatives without hiding mandatory semantics in side channels or adapters.

### TRADEOFF_FRONTIER

Different candidates dominate different metric groups and no scientifically justified scalar weighting exists.

### NO_SINGLE_WINNER

Multiple substantially different representations are required for different task classes, or complementary substrates outperform every single substrate.

### ALL_CANDIDATES_INSUFFICIENT

Every frozen candidate has a material semantic or operational failure that prevents it from satisfying the benchmark.

### EXPERIMENT_INCOMPLETE

Required candidates, tasks, or validity checks remain unexecuted.

---

## 7. Prohibited Verdicts

PRIMITIVE-0 may not conclude:

```text
PROVEN
UNIVERSAL
HUMAN-LIKE
CONSCIOUS
TRUE COGNITIVE LANGUAGE
THE MIND'S INSTRUCTION SET
```

The strongest authorized claim is bounded to the frozen tasks and tested mechanisms.
