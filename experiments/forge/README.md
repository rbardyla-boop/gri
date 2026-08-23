# Forge / TE0

TE0 is a bounded local tool-ecology sandbox for discovery-and-kill experiments.

## Public qualification

From the repository root, with either rootless Podman or Docker installed and `python:3.11-slim` already present locally:

```bash
podman pull python:3.11-slim   # or: docker pull python:3.11-slim
./experiments/forge/sandbox.sh
```

The image pull is intentionally separate. `sandbox.sh` uses `--pull=never` and `--network=none` during the run.

To run the public qualification without the container boundary (engineering diagnosis only):

```bash
python -B -m experiments.forge.qualify_te0_e0 --scratch /tmp/te0-e0
```

The TE0-E0 fixture is public and non-scientific. It qualifies the pipeline only.

## Development search

`te0_dev.py` accepts BUILD and DEV files but intentionally has no Vault argument.

## Vault judge

The Vault path is supplied only to `te0_authorize.py` and `te0_judge.py` after a champion is frozen. The consumption marker is created before score computation. Reusing the same authorization/marker fails closed.

See `docs/TE0-TOOL-ECOLOGY-SANDBOX.md` for the architecture and authority boundaries.
