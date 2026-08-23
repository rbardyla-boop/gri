# TE0 — Tool Ecology Sandbox

Status: **DEVELOPMENT / NOT SCIENTIFIC AUTHORITY**

## Claim under test

> A frozen local model can discover and retain useful external tool recipes through disposable search, while an independent verifier prevents failed, shortcut, fragile, or overfit recipes from becoming durable authority.

TE0 does not claim AGI, autonomous scientific discovery, self-improving model weights, consciousness, or general problem solving.

## Why TE0 exists

Repeated GRI failures occurred at different layers: instrument/readout failure, interface collision, host/resource failure, retrieval/state failure, and unnecessary architectural complexity. TE0 makes failure classification part of the discovery loop so that the system can conclude that the missing mechanism is not a tool.

The loop is:

`classify -> propose small tools -> compose -> compare to simple nulls -> grind -> ablate -> choose one champion -> burn Vault authorization -> judge once -> promote or reject -> ledger`

## Components

### ToolSmith

ToolSmith proposes tiny declarative tools from BUILD evidence and a failure diagnosis. Its v0 DSL is intentionally small and transparent. It cannot use `eval`, `exec`, imports, subprocesses, filesystem access, or networking.

### Composer

Composer searches type-compatible recipes on DEV only. Search is bounded by maximum depth, cost, and candidate count. The objective penalizes extra tools and resource cost.

### NullSmith

NullSmith scores embarrassingly simple transparent alternatives before complex recipes receive credit. A candidate that cannot materially beat its null does not deserve mechanism credit.

### Grinder

Grinder applies explicit allow-listed mutations to a fixed recipe and records counterexamples. It may find failures; it does not modify the candidate while testing it.

### Ablator

Ablator deletes one component at a time. If removing a tool does not reduce performance, that tool does not earn credit.

### Judge

Judge is one-shot and cannot optimize candidates. The Vault consumption marker is written before scoring so a crash still burns the run. PASS, FAIL, and INCONCLUSIVE are the only verdict classes.

### Ledger

The experiment ledger is append-only and hash-chained. Failed recipes remain evidence rather than disappearing from memory.

### Skill Packet

A skill packet may be created only after Judge PASS and must bind the exact recipe and Judge receipt. It does not modify the frozen model.

## Data separation

- **BUILD**: visible to ToolSmith.
- **DEV**: visible to Composer, Grinder, null controls, and ablation.
- **VAULT**: unavailable to development commands. Only Judge receives it after a champion and authorization are frozen.

The public TE0-E0 fixture is a pipeline qualification specimen, not scientific evidence; its Vault is intentionally public so CI can prove the machinery without consuming a scientific holdout.

## Local sandbox boundary

`experiments/forge/sandbox.sh` launches the qualification inside rootless Podman or Docker when available. The repository is read-only, `/scratch` is the only writable bind mount, network is disabled, Linux capabilities are dropped, privilege escalation is disabled, PID/CPU/RAM limits are set, and the container image must already exist locally (`--pull=never`).

This is a containment aid, **not** a hostile-code or kernel-security proof. For that reason v0 ToolSmith does not generate arbitrary executable code.

## TE0-E0 qualification

The first public fixture is a deliberately small interface-normalization failure. ToolSmith sees BUILD examples, proposes transparent normalization/lookup tools, Composer searches combinations on DEV, and Judge tests the frozen champion once on the public qualification Vault. CI requires:

- multi-tool repair found;
- DEV score = 1.0;
- Vault score = 1.0;
- margin over simple null >= 0.5;
- second Vault attempt blocked;
- candidate model calls = 0;
- no scientific authority granted by the qualification itself.

## Promotion rule

A recipe becomes durable only if all of the following hold:

1. the failure class is not an unresolved integrity/resource/measurement blocker;
2. the recipe beats transparent nulls on DEV;
3. Grinder counterexamples are recorded;
4. ablation supports the claimed component credit;
5. the exact champion is frozen before Vault exposure;
6. Judge passes the one-shot Vault gate;
7. the skill packet binds the Judge receipt;
8. the ledger remains valid.

## Next research gate

After the public TE0-E0 pipeline qualifies, TE0 should be given **one previously understood project failure** with a fresh hidden Vault. The preferred first scientific target is an interface/instrument failure rather than a broad model-capability failure. Success requires independently rediscovering a repair that survives hidden testing without touching model weights or frozen scientific artifacts.
