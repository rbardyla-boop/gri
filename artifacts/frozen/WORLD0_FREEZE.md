# WORLD-0 Freeze Record

Frozen artifact: `artifacts/frozen/world0_v0_1/`

Generation command:

```bash
python scripts/generate_world0.py --seed 1337 --output artifacts/generated/world0_v0_1
```

Validation command:

```bash
python scripts/validate_world0.py artifacts/generated/world0_v0_1
```

Freeze preconditions satisfied:

- unit suite: 25 passed;
- validator terminal status: `GRI_02_WORLD0_PASS`;
- train chain lengths restricted to 1–4;
- extrapolation depths isolated at 5, 8, 16, 32, 64;
- split sample IDs disjoint;
- train/validation/IID answer labels exactly balanced;
- contradiction cases isolated;
- SO(4) frame matrices deterministic, orthogonal, determinant +1;
- canonical serialization and SHA-256 identities checked.

The frozen artifact must not be modified by downstream model experiments. A changed benchmark requires a new version and new freeze record.
