# GRI-01E — Constructive Representability Result

**Verdict:**

```text
PARTIAL_GENERALIZATION
```

The exact frozen cell architecture was solved deterministically with fixed
LBFGS settings, fit only on train delays 1/2/4, then evaluated unchanged on
held-out delays 8/16.

## Evidence

```text
architecture:       h'=tanh(W h + b + E[token]); logits=O h + c
config SHA-256:      a91c7b9cd26eb7b5593ae8ecc7d708a64e6d7ac4fbecf6595417a6f244916dfd
implementation SHA:  16855b669e96759781dbc322b33d82de1ff6ad9da9c1f0d0d3588b2e47f58ed1
receipt SHA-256:     54a019caedd9065497a959376730e18e380b89a5aba1fc4ad98bad0245b15a6a
replay:              PASS
```

| State dimension | Train accuracy | Held-out accuracy | Interpretation |
|---:|---:|---:|---|
| 2 | 0.875 | 0.875 | incomplete construction |
| 4 | 0.875 | 0.875 | incomplete construction |
| 8 | 1.000 | 0.500 | fits train, fails delay generalization |

## Interpretation

This does not support `REPRESENTABLE` for the frozen GRI-01 mechanism on the
full recurrence fixture. It does locate a boundary: dimension 8 can fit the
short-delay training set under a deterministic constructive solve, but its
state evolution does not carry the task correctly to held-out delays. Dimensions
2 and 4 do not fit all training cells under the same solve.

Together with GRI-01D's 100% explicit-control result, the evidence now points
to a limitation in the current tanh transition/readout formulation or its
representational generalization—not a failure of the task or of recurrence as
such. No optimizer tuning, geometry, memory addition, or architecture change
was performed.
