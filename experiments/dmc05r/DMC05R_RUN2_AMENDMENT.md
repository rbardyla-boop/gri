# DMC-05R Run 2 engineering amendment

Run 1 is classified `ENGINEERING_FAILURE_NO_SCIENTIFIC_VERDICT`.

The first frozen DMC worker completed its 2,376 core evaluations in process,
then stopped on the first exploratory `SURPRISE_DEPENDENCY` query. The adapter
had copied the source write descriptor's normalized `A,B` order into a query
descriptor. Frozen DMC-04B validates query descriptors in normalized `B,A`
order. The child wrote no receipt, and no DMC capability value, aggregate,
gate, or terminal state was serialized or inspected.

Run 1 is preserved at
`artifacts/dmc05r/run1_engineering_failure/`, including the exact frozen
harness, preflight, fixture manifests, deterministic worker receipts, failure
receipt, and traceback.

## Authorized repair

Run 2 may make exactly two result-independent changes:

1. Construct exploratory query descriptors by preserving the same A and B
   token identities but serializing them in frozen query order `B,A`.
2. Extend the test suite to validate every constructed exploratory query with
   the frozen DMC-04B scorer-view validator.

The repair does not alter any primary DMC-05R counterfactual, source case,
record payload, creation episode, query, target, answer, oracle field,
checkpoint, model, weight, feature, capacity, seed, threshold, system,
resource dimension, terminal name, or verdict precedence. It changes only the
schema-valid serialization of the already-preregistered exploratory query.

No training is authorized. Run 2 must receive a new runner/test hash freeze
before tests or scientific execution.
