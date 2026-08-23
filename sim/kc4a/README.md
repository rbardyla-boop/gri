# KC-4A-D — Utility Benchmark

KC-4A-D is a development-only equal-budget distributed-memory benchmark. It
compares the existing eight KC-1A cells × eight slots with a simple centralized
64-slot baseline. Both declare 64 logical packet slots and 1024 state bytes.

The frozen fixtures cover locally distributed knowledge, 64-packet pressure,
node loss before and after propagation, partial disconnection, and same-slot
conflicts. Metrics include retained/recovered/lost identities, unexpected
identities, state bytes, communication, operations, restart, and exact replay.

This benchmark does not claim better answers, reasoning, learning, or AI value.
It records whether a concrete bounded distributed-memory task produces a
measurable difference under the declared comparison. No advantage threshold or
scientific verdict is authorized.

