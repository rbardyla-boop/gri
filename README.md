# GRI — Geometric Recurrent Intelligence

This repository is a standalone research program for testing whether locally geometric, weight-tied recurrent computation provides measurable generalization or efficiency advantages over simpler matched systems.

The repository begins with **WORLD-0**, a deterministic synthetic relational-reasoning benchmark. WORLD-0 is the exam, not the model.

## Current intended sequence

1. GRI-00 foundation contract.
2. GRI-01 mathematical specification.
3. GRI-02 WORLD-0 benchmark and validator.
4. Only after benchmark freeze: matched non-geometric and geometric model baselines.

## WORLD-0 measures

- direct relation retrieval;
- inverse relations;
- compositional transitive reasoning;
- extrapolation from train chain lengths 1–4 to held-out depths 5, 8, 16, 32, and 64;
- deterministic replay and artifact validation;
- isolated contradiction cases;
- deterministic SO(4) local-frame perturbations that must not change semantics.

It does not measure consciousness, general intelligence, natural-language ability, or human cognition.

## Commands

```bash
python scripts/generate_world0.py --seed 1337 --output artifacts/generated/world0_v0_1
python scripts/validate_world0.py artifacts/generated/world0_v0_1
pytest
```
