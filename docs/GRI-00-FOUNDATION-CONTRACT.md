# GRI-00 — Foundation Contract

Status: PROVISIONAL RESEARCH CONTRACT

Primary question: can constrained, locally geometric recurrent state evolution provide reproducible algorithmic-generalization or efficiency advantages over matched unconstrained recurrent systems?

## Six primitives

1. Node — mutable computational state.
2. Frame — local coordinate interpretation.
3. Connection — transport between frames.
4. Relation — invariant relation information between nodes.
5. Dynamics — one weight-tied recurrent update law.
6. Readout — restricted machine-scorable output.

## Required boundaries

- No E8 dependency in the base architecture.
- No language model dependency in WORLD-0.
- Local-frame independence must be an architectural invariant, not a learned preference.
- Recurrent depth reuses the same parameters.
- Memory, learned connections, curvature, and E8 are ablations that must earn inclusion.
- No consciousness, brain-equivalence, or theory-of-everything claims.

## Experimental ratchet

Each added mechanism must beat its matched parent under preregistered metrics or be removed.
