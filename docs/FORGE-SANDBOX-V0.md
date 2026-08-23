# FORGE Sandbox v0 — bounded tool-combination research

## Purpose

Forge exists to turn project failures into search constraints instead of reasons to stop.

The recurring failure classes in GRI/SEM/LCB work are:

1. weak or missing nulls;
2. hidden benchmark shortcuts;
3. mechanism confounding;
4. prior-art collision;
5. overfitting to a development instrument;
6. apparent wins that vanish under ablation, context removal, replay, noise, bias, or matched-resource comparison.

Forge does **not** optimize for making a preferred idea pass. It searches for small tool chains that survive explicit failure attacks.

## Local containment boundary

`experiments/forge/sandbox.sh` prefers rootless Podman, then Docker. At runtime it uses:

- no network;
- read-only root filesystem;
- repository mounted read-only;
- only `/scratch` writable;
- all Linux capabilities dropped;
- no-new-privileges;
- fixed process, memory, and CPU limits;
- no image pulls during a run;
- no GPU in v0.

This is a bounded research sandbox, not a claim of protection against a malicious kernel/container escape.

## Tool roles

### Grinder

Attacks a fixed candidate with allow-listed mutations and preserves counterexamples. Examples: context deletion, semantic pair reversal, noise increase, bias injection, drive withdrawal, seed changes, resource reduction.

### NullSmith

Produces the simplest transparent comparator capable of addressing the same task. A candidate that cannot beat the null loses mechanism credit.

### Ablator

Deletes or replaces one component at a time. If performance survives removal, the component does not receive credit.

### Toolsmith

Builds type-compatible candidate chains from registered primitives only. It does not generate or execute arbitrary source code in v0.

### Mixer

Searches combinations under fixed depth/cost/run budgets using DEVELOPMENT cases only. The holdout is not an input to search.

### Judge

Hands a selected candidate and its evidence to GRI Gauntlet. Forge cannot award the final scientific claim.

### Archivist

Records chain IDs, tool manifests, seeds, resource budgets, failures, receipts, and hashes so failed combinations remain knowledge.

## Scientific anti-gaming rule

The central rule is:

> Search may optimize on DEVELOPMENT evidence. It may not see the sealed holdout. The selected champion receives one holdout evaluation, and that receipt cannot be overwritten.

If a chain fails holdout, the failure is frozen. Any continued optimization creates a successor experiment with a new holdout.

## End-state alignment

Forge is intended to support three distinct project levels without conflating them:

- **Semantic function:** discover whether explicit semantic tools or compositions improve SEM-style semantic control without shortcut leakage.
- **Substrate mechanisms:** search/ablate dynamical-memory mechanisms against static latch, Schlögl, parametron, and flow-removed controls.
- **Research epistemology:** use Gauntlet to decide which component, if any, deserves credit.

The target is not an autonomous self-improving agent. The target is a **bounded mechanism-discovery workbench** that can cheaply generate, combine, attack, and discard hypotheses while keeping frozen evidence.

## v0 implementation

`experiments/forge/forge.py` provides:

- typed tool registry;
- bounded deterministic chain enumeration;
- development-only candidate search;
- cost/complexity tie-breaking;
- one-shot content-bound holdout receipt;
- Grinder counterexample mining.

The first implementation deliberately omits arbitrary code generation, network tools, repo writes, shell tools, model downloads, and autonomous merge/release authority.

## Next gates

1. Run v0 tests inside the local sandbox.
2. Add explicit SEM-0R mutation adapters **without exposing scorer gold to Toolsmith/Mixer**.
3. Add LCB/FET parameter-mutation adapters.
4. Add NullSmith and Ablator registries.
5. Integrate Gauntlet receipts.
6. Only then test tool-chain search on a disposable development benchmark.
