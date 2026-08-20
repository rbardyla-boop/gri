# GRI-05 Recovery Handoff

Recovered from `GRI_RESEARCH_FULL_HISTORY.bundle` at baseline commit `3188c2723464a6ba2b53ceae967aa08dbd1a7766`.

This is a functional reconstruction of the missing GRI-05 branch. It does **not** reproduce the lost commit SHAs `04ea63e8...` or `5172e3e8...`.

## Branch

`agent/gri-so4-capacity-match`

## Commits

- `97313e36bf257d61a4ed047e39766b6cd6d77cae` — preregister exact 30,912-vs-30,912 capacity match.
- `ce05b6f2e7e96ed2febfc272dde759509e570631` — adjacency-only execution; dense-vs-sparse output and gradient equivalence.
- `0988333434b97410bd766128355326b7bf6847f8` — exact resumable-training equivalence audit.

## Verification

- `pytest -q` -> 36/36 PASS.
- `python scripts/validate_world0.py artifacts/frozen/world0_v0_1` -> `GRI_02_WORLD0_PASS`.
- Frozen WORLD-0 files are unchanged relative to `origin/main`.
- Resumable-training audit uses seed 9090, outside preregistered evidence seeds 1337-1341.
- Baseline and SO(4) uninterrupted-vs-resumed runs match exactly in final loss, model tensors, AdamW state, and Python/NumPy/PyTorch RNG state.

## Import into stale checkout

Preferred:

```bash
git fetch /path/to/GRI_GRI05_RECOVERED.bundle agent/gri-so4-capacity-match:agent/gri-so4-capacity-match
git checkout agent/gri-so4-capacity-match
```

Or apply the three patches in order on top of `3188c27`.

No preregistered GRI-05 seed result is included in this handoff.
