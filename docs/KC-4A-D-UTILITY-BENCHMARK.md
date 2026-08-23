# KC-4A-D — Utility Benchmark

## Status

```text
KC-4A-D: COMPLETE
VERDICT: KC_4A_DEV_COMPLETE
SCIENTIFIC VERDICT: FORBIDDEN
ADVANTAGE CLAIM: NOT COMPUTED
```

KC-4A-D compares the existing eight KC-1A cells with a simple centralized
64-slot baseline. Both declare 64 logical packet slots and 1024 state bytes.
The KC condition uses only frozen KC-3D ticks and KC-3C local contacts; the
central condition writes to an explicit 64-slot address space. Neither system
learns or receives semantic labels beyond the frozen packet identities.

The six frozen cases cover eight-packet distribution, 64-packet pressure,
node loss before and after propagation, partial disconnection, and same-slot
conflict. Metrics include retained/recovered/lost identities, unexpected
identities, occupied slots, state digests, communication, operations, restart,
and replay.

Observed development metrics are not a scientific advantage verdict. In this
fixture set, KC recovers all eight low-pressure packets but retains only 8/64
under the 64-packet pressure case; the centralized baseline recovers 64/64.
The node-loss and partial-disconnection cases are likewise recorded without
choosing a winner or generalizing beyond these exact configurations.

## Anchors

```text
KC-4A-D fixtures SHA-256:
527fa3c2230c16475629d2f4b444bfc2d934b707815d67aee532c91f0079a5f5

KC-4A-D config SHA-256:
842e4d230a1f4bb73b94f1fa8d06116a02b9850dc099141e4748ced7e8bb8ba1

KC-4A-D benchmark source SHA-256:
28a7f737a63d847acc0f9ee72a399bb54593e4633768457e55773e5714bd06cf

KC-3D tick source SHA-256:
290ad31ad658318f10e14a39aa0be6a7de684d8f527061447a44ed4fa7bf5502

KC-3D config SHA-256:
0eeb04cf496d4bd77c5a1ecf9e81286bc57a8508daa9577eb929694fef2bbb6e

KC-3C activation source SHA-256:
780c9209cb1cf199e1a719edbad24ce873b4fe33e24874a2387cda1561ad567d

KC-3A manager source SHA-256:
af28edf692724d3bdc4a4737cd546f055f42832c6ae854898f7c7cf6b595f8f7

KC-1A source SHA-256:
2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173

KC-4A-D receipt SHA-256:
ab208ee5ca4b73c393ecf409ec775d148fd7f6f1f97bbd854dba819ca1114ebb
```
