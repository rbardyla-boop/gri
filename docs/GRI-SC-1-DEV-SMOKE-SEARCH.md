# GRI-SC-1 — Bounded DEV_SMOKE Search

## Status

```text
AUTHORIZED FOR DEVELOPMENT SEARCH ONLY
SCIENTIFIC VERDICT: FORBIDDEN
CANDIDATE FREEZE: NOT AUTHORIZED
```

The search used the final amended GRI-SC-0 contract anchor:

```text
5174be19336f0f30597a22f78917b189708fe406f4f588dccc2989bd4b642e50
```

No frozen GRI-02B artifact, scientific ledger entry, or candidate-freeze
decision was changed.

## Search space

Only two narrow branch-free formulations were tested:

### A — branch-free affine parent form

```text
h_next = tanh(W h + E[token] + b)
```

```text
state slots:       8
trainable params: 170
recurrent ops:    97
selector compares: 0 in the transition path
```

This is the existing generic transform-every-step route, included as a
negative development reference.

### B — branch-free token-coded residual

```text
u       = tanh(D ⊙ h + E[token])
r       = u - h
h_next  = h + E[token][semantic_code] · r
```

The fixed embedding coordinate is `0` for `WAIT` and `1` for all other
tokens. No equality test or branch selects the path. The manifest counts the
diagonal transform, token lookup, residual arithmetic, and readout within the
frozen envelope:

```text
state slots:       8
trainable params:  96
fixed params:      10
recurrent ops:    57
recurrent+query:  78
selector compares: 0 in the transition path
```

## Development results

| Candidate | SIM preflight | Fit accuracy | Held-out accuracy | Restart smoke |
|---|---:|---:|---:|---:|
| SC-1-A affine | PASS | 0.5714 | 0.5288 | PASS |
| SC-1-B residual | PASS | 0.5000 | 0.5000 | PASS |

The smoke trained on the 350 fit fixtures for 80 development epochs with
seed `20260820`. It evaluated all 558 fixtures, including 208 held-out
fixtures. Restart smoke covered 192 prefix cases across 32 fixtures.

These are engineering signals only. They are not scientific accuracy gates,
not a verdict, and not evidence of impossibility.

## Bounded conclusion

```text
NO_PROMISING_CONSTRUCTION_IN_BOUNDED_SMOKE
```

This search did not find an in-budget branch-free construction that produced
a promising smoke signal. It does not prove that no such construction exists.

The subsequent SC-1R constructive analysis resolved that distinction for
Candidate B: the declared branch-free residual form is representable on the
frozen fixture family, despite failing the short SGD smoke. That result is
recorded separately and does not promote the candidate.

Because no candidate earned promotion, `GRI-SC-2` remains unauthorized. A
future search may require a separately authorized formulation or a narrower
formal analysis; it may not silently convert this development result into a
scientific claim.

## Evidence

- [Search receipt](../artifacts/results/gri_sc1_search_receipt.json)
- [Candidate A receipt](../artifacts/results/gri_sc1_a_dev_smoke.json)
- [Candidate B receipt](../artifacts/results/gri_sc1_b_dev_smoke.json)
- [Candidate A source](../experiments/candidates/GRI-SC-1/branchfree_affine.py)
- [Candidate B source](../experiments/candidates/GRI-SC-1/branchfree_residual.py)
- [SC-1R representability analysis](GRI-SC-1R-RESULT.md)
- [SC-1R receipt](../artifacts/results/gri_sc1r_branchfree_residual_receipt.json)

Search receipt SHA-256:

```text
bd5704ebc3b023b9317e13319f7c9ad548a7b23087a9048058d1dee9cc208ec0
```

## Current boundary

```text
GRI-SC-0: SELECTOR-COST LOWER BOUND DISPROVED BY CONSTRUCTION
GRI-SC-1: DEV_SMOKE COMPLETE — NO PROMISING CONSTRUCTION
GRI-SC-1R: REPRESENTABLE — ANALYSIS ONLY
GRI-SC-1R.1: ACCOUNTING AUDIT PASS
GRI-SC-2: NOT AUTHORIZED
SCIENTIFIC LEDGER: UNCHANGED
SUCCESSOR: NOT AUTHORIZED
```
