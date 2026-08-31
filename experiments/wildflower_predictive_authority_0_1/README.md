# WILDFLOWER Predictive Authority 0.1

This is a design-only successor for the predictive/authority layer. It is
separate from the frozen `wildflower_dual_authority_0_3` experiment.

Current status:

- no scientific seed is authorized or executed;
- seeds 311–351 are historical and cannot be reused;
- the transparent null remains a first-class competitor;
- Dual-Authority-0.3 is treated as a fixed downstream epistemic consumer;
- `--profile-only` runs synthetic diagnostics and audits the frozen 340
  artifact without using scientific selectors.

The runner is ready for a later, separately authorized run:

```text
python -m experiments.wildflower_predictive_authority_0_1.run_predictive_authority01 --help
```

Scientific execution is fail-closed until an explicit future authorization is
introduced. No authorization file is present in this prelock.
