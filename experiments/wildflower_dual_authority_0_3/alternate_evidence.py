"""Deterministic alternate-evidence challenge for Dual-Authority-0.3.

The challenge is deliberately separate from the Nursery predictor.  It gives
the controls ordinary numeric prediction/witness frames, while the evaluator
computes Metric A from grounded root-support lineage.  Support ids, immediate
parent keys, labels, prose, and Python object identity are never used as an
independence criterion.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import itertools
from typing import Iterable

from . import store as d
from .controls import RecordedTransition, StreamClaim
from .metrics import StoreSnapshot, snapshot_store


PRESERVED = "PRESERVED"
RECOMPUTED = "RECOMPUTED"
REVOKED = "REVOKED"
UNCHANGED = "UNCHANGED"

CASE_NAMES = (
    "true_independent_alternate",
    "both_paths_invalidated",
    "same_root_masquerade",
    "duplicate_lineage",
    "alternate_already_ungrounded",
    "alternate_only_after_witness",
    "semantic_value_changes",
    "one_of_three_survives",
    "two_of_three_survive",
    "nested_transitive_alternate",
    "diamond_shared_ancestor",
    "five_level_derivation",
    "alternate_disappears_and_returns",
    "canonical_reuse_no_independence",
    "lineage_collision_rejection",
    "same_parent_keys_changed_lineage",
    "partial_ancestor_overlap",
    "unrelated_branch",
)
HOSTILE_CASE_CODES = tuple(range(1, len(CASE_NAMES) + 1))
EMITTED_HOSTILE_CASE_CODES = tuple(code for code in HOSTILE_CASE_CODES if code != 1)
POSITIVE_HOSTILE_CASE_CODES = (1, 8, 9, 10, 12)


def expected_metric_a_opportunity(case_code: int) -> bool:
    """Frozen graph-contract expectation used only for evaluator auditing."""

    if case_code not in HOSTILE_CASE_CODES:
        raise ValueError(f"unknown alternate-evidence case code: {case_code}")
    return case_code in POSITIVE_HOSTILE_CASE_CODES


@dataclass(frozen=True)
class AlternateCaseSpec:
    event_id: int
    case_code: int
    case_name: str
    target: d.Packet
    frames: tuple[RecordedTransition, ...]
    correction_index: int
    truth_value: int
    recomputation_attempted: bool = False


def world_root_identity(packet: d.Packet | tuple[int, int, int, int, int, int]) -> str:
    """Return the canonical identity of a grounded world root.

    The complete numeric world packet is part of the identity.  This means
    equal claim keys with different grounded evidence remain distinguishable,
    while repeated copies of the same evidence are not independent.
    """

    numeric = packet.numeric_tuple() if isinstance(packet, d.Packet) else tuple(packet)
    return d.canonical_hash(("world-root", numeric))


def grounded_root_sets(
    snapshot: StoreSnapshot,
    key: d.ClaimKey,
    _trail: frozenset[d.ClaimKey] = frozenset(),
) -> tuple[frozenset[str], ...]:
    """Enumerate grounded root sets for a claim from a frozen snapshot."""

    if key in _trail:
        raise ValueError("support cycle detected while classifying challenge")
    result: set[frozenset[str]] = set()
    for support_id in snapshot.support_ids_for_claim(key):
        support = snapshot.supports.get(support_id)
        if support is None or not (support.enabled and support.effective and support.grounded):
            continue
        if support.kind == d.SUPPORT_WORLD:
            result.add(frozenset({world_root_identity(support.packet)}))
        elif support.kind == d.SUPPORT_DERIVED:
            parent_sets = [
                grounded_root_sets(snapshot, parent, _trail | {key})
                for parent in support.parents
            ]
            if any(not paths for paths in parent_sets):
                continue
            for combination in itertools.product(*parent_sets):
                roots = frozenset().union(*combination)
                result.add(roots)
    return tuple(sorted(result, key=lambda roots: tuple(sorted(roots))))


def grounded_path_ids(
    snapshot: StoreSnapshot,
    key: d.ClaimKey,
) -> dict[str, frozenset[str]]:
    """Map canonical grounded path identities to their canonical root sets."""

    return {
        d.canonical_hash(("grounded-root-path", tuple(sorted(roots)))): roots
        for roots in grounded_root_sets(snapshot, key)
    }


def _maximum_independent_root_count(root_sets: Iterable[frozenset[str]]) -> int:
    roots = tuple(root_sets)
    best = 0
    for size in range(1, len(roots) + 1):
        for combination in itertools.combinations(roots, size):
            if all(
                not (left & right)
                for left, right in itertools.combinations(combination, 2)
            ):
                best = size
    return best


def _status_name(status: int) -> str:
    return {
        d.STATUS_PROVISIONAL: "PROVISIONAL",
        d.STATUS_COMMITTED: "COMMITTED",
        d.STATUS_REVOKED: "REVOKED",
        d.STATUS_CONFLICTED: "CONFLICTED",
    }.get(status, f"UNKNOWN_{status}")


def classify_alternate_event(
    spec: AlternateCaseSpec,
    before_witness: StoreSnapshot,
    after_witness: StoreSnapshot,
    after_recompute: StoreSnapshot,
) -> dict[str, object]:
    """Classify one challenge using only evaluator-side frozen snapshots."""

    key = (spec.target.stable_reference, spec.target.value)
    pre_paths = grounded_path_ids(before_witness, key)
    after_paths = grounded_path_ids(after_witness, key)
    final_paths = grounded_path_ids(after_recompute, key)
    pre_status = before_witness.status(key)
    after_status = after_witness.status(key)
    final_status = after_recompute.status(key)
    invalidated = sorted(set(pre_paths).difference(after_paths))
    survivors = sorted(set(pre_paths).intersection(after_paths))
    # A path that was present before the witness but absent immediately after
    # it is still "new post-witness" when it is restored by recomputation.
    new_paths = sorted(set(final_paths).difference(after_paths))
    pre_independent = _maximum_independent_root_count(pre_paths.values())
    correct_and_committed = (
        spec.target.value == spec.truth_value and pre_status == d.STATUS_COMMITTED
    )
    opportunity = bool(
        correct_and_committed
        and len(pre_paths) >= 2
        and pre_independent >= 2
        and invalidated
        and survivors
    )
    success = bool(
        opportunity
        and after_status == d.STATUS_COMMITTED
        and survivors
        and not (set(invalidated) & set(after_paths))
        and all(
            roots
            for path_id, roots in after_paths.items()
            if path_id in survivors
        )
        and not new_paths
    )
    recomputation_opportunity = bool(
        correct_and_committed
        and invalidated
        and not survivors
        and spec.recomputation_attempted
    )
    recomputation_success = bool(
        recomputation_opportunity
        and new_paths
        and final_status == d.STATUS_COMMITTED
    )
    if opportunity:
        primary = PRESERVED if success else REVOKED
    elif recomputation_success:
        primary = RECOMPUTED
    elif after_status != d.STATUS_COMMITTED and final_status != d.STATUS_COMMITTED:
        primary = REVOKED
    else:
        primary = UNCHANGED
    return {
        "event_id": spec.event_id,
        "case_code": spec.case_code,
        "case_name": spec.case_name,
        "claim_key": [spec.target.stable_reference, spec.target.value],
        "pre_witness_grounded_path_count": len(pre_paths),
        "pre_witness_independent_root_count": pre_independent,
        "invalidated_path_ids": invalidated,
        "surviving_preexisting_path_ids": survivors,
        "post_witness_status": _status_name(after_status),
        "post_witness_status_code": after_status,
        "final_status": _status_name(final_status),
        "new_post_witness_path_ids": new_paths,
        "recomputation_attempted": spec.recomputation_attempted,
        "primary_classification": primary,
        "metric_a_opportunity": opportunity,
        "metric_a_success": success,
        "metric_b_opportunity": recomputation_opportunity,
        "metric_b_success": recomputation_success,
    }


def _packet(reference: int, value: int, act: int) -> d.Packet:
    return d.Packet(reference, act, reference, d.REL_X, 0, value)


def _claim(reference: int, value: int, parents: tuple[d.ClaimKey, ...]) -> StreamClaim:
    return StreamClaim(_packet(reference, value, d.ACT_DERIVE), parents)


def _world_frame(tick: int, packets: tuple[d.Packet, ...]) -> RecordedTransition:
    return RecordedTransition(
        tick=tick,
        # Every control must be able to create the parent claim key.  The
        # witness then supplies the grounded authority for the same numeric
        # packet; the proposal remains an ordinary mechanism input.
        predictions=tuple(
            StreamClaim(_packet(packet.stable_reference, packet.value, d.ACT_PROPOSE))
            for packet in packets
        ),
        witnesses=packets,
        recomputed=(),
        authority=1.0,
        truth_packets=(),
    )


def _derive_frame(
    tick: int,
    claims: tuple[StreamClaim, ...],
) -> RecordedTransition:
    return RecordedTransition(
        tick=tick,
        predictions=claims,
        witnesses=(),
        recomputed=(),
        authority=1.0,
        truth_packets=(),
    )


def _correction_frame(
    tick: int,
    target: d.Packet,
    witnesses: tuple[d.Packet, ...],
    *,
    recomputed: tuple[StreamClaim, ...] = (),
) -> RecordedTransition:
    return RecordedTransition(
        tick=tick,
        predictions=(),
        witnesses=witnesses,
        recomputed=tuple(recomputed),
        authority=1.0,
        truth_packets=(_packet(target.stable_reference, target.value, d.ACT_OBSERVE),),
    )


def _path(
    base: int,
    path_index: int,
    depth: int,
    *,
    shared_roots: tuple[int, ...] = (),
) -> tuple[tuple[d.Packet, ...], tuple[StreamClaim, ...], d.ClaimKey]:
    """Create a grounded chain and return its last claim key."""

    root_refs = shared_roots or (base + path_index * 100 + 1,)
    root_keys = tuple((reference, 0) for reference in root_refs)
    claims: list[StreamClaim] = []
    parent_keys = root_keys
    for level in range(depth):
        reference = base + path_index * 100 + 10 + level
        claim = _claim(reference, 0, parent_keys)
        claims.append(claim)
        parent_keys = ((reference, 0),)
    return (
        tuple(_packet(reference, 0, d.ACT_OBSERVE) for reference in root_refs),
        tuple(claims),
        parent_keys[0],
    )


def _build_case(
    event_id: int,
    case_code: int,
    start_tick: int,
) -> AlternateCaseSpec:
    base = 4_000_000 + event_id * 10_000
    target_ref = base + 9_000
    target_value = 1
    target = _packet(target_ref, target_value, d.ACT_DERIVE)
    roots: list[d.Packet] = []
    claims: list[StreamClaim] = []
    leaves: list[d.ClaimKey] = []
    correction_refs: list[int] = []
    recompute_claims: list[StreamClaim] = []
    correction_index = 2
    recomputation_attempted = False

    def add_path(index: int, depth: int = 1, shared: tuple[int, ...] = ()) -> None:
        root_packets, path_claims, leaf = _path(
            base, index, depth, shared_roots=shared
        )
        roots.extend(root_packets)
        claims.extend(path_claims)
        leaves.append(leaf)
        correction_refs.append(path_claims[-1].packet.stable_reference)

    if case_code == 1:
        add_path(0, 2)
        add_path(1, 2)
    elif case_code == 2:
        add_path(0, 1)
        add_path(1, 1)
        correction_refs = [claims[0].packet.stable_reference, claims[1].packet.stable_reference]
    elif case_code == 3:
        shared = (base + 1,)
        add_path(0, 2, shared)
        add_path(1, 2, shared)
    elif case_code == 4:
        add_path(0, 2)
        claims.append(_claim(claims[0].packet.stable_reference, 0, claims[0].semantic_parents))
        leaves = [leaves[0], leaves[0]]
    elif case_code == 5:
        add_path(0, 1)
        add_path(1, 1)
        correction_index = 3
    elif case_code == 6:
        add_path(0, 2)
        add_path(1, 2)
        correction_index = 2
        recomputation_attempted = True
        recompute_claims = (_claim(target_ref, target_value, (leaves[1],)),)
    elif case_code == 7:
        add_path(0, 1)
        add_path(1, 1)
        target_value = 0
        target = _packet(target_ref, target_value, d.ACT_DERIVE)
    elif case_code in (8, 9):
        add_path(0, 1)
        add_path(1, 1)
        add_path(2, 1)
        correction_refs = (
            [claims[0].packet.stable_reference, claims[1].packet.stable_reference]
            if case_code == 8
            else [claims[0].packet.stable_reference]
        )
    elif case_code == 10:
        add_path(0, 3)
        add_path(1, 3)
    elif case_code == 11:
        shared = (base + 1,)
        add_path(0, 2, shared)
        add_path(1, 2, shared)
    elif case_code == 12:
        add_path(0, 5)
        add_path(1, 5)
    elif case_code == 13:
        add_path(0, 1)
        add_path(1, 1)
        correction_refs = [claims[0].packet.stable_reference, claims[1].packet.stable_reference]
        correction_index = 2
        recomputation_attempted = True
        recompute_claims = (
            _claim(claims[1].packet.stable_reference, 0, claims[1].semantic_parents),
            _claim(target_ref, target_value, (leaves[1],)),
        )
    elif case_code == 14:
        add_path(0, 1)
        claims.append(_claim(claims[0].packet.stable_reference, 0, claims[0].semantic_parents))
        leaves = [leaves[0], leaves[0]]
    elif case_code == 15:
        shared = (base + 1,)
        add_path(0, 1, shared)
        add_path(1, 2, shared)
        correction_refs = [claims[0].packet.stable_reference]
    elif case_code == 16:
        root = _packet(base + 1, 0, d.ACT_OBSERVE)
        roots.append(root)
        intermediate = _claim(base + 10, 0, ((base + 1, 0),))
        claims.append(intermediate)
        leaves = [(base + 10, 0)]
        correction_refs = [base + 10]
        correction_index = 3
        recomputation_attempted = False
    elif case_code == 17:
        add_path(0, 1, (base + 1, base + 2))
        add_path(1, 1, (base + 1, base + 3))
        correction_refs = [claims[0].packet.stable_reference]
    elif case_code == 18:
        add_path(0, 1)
        unrelated_root = _packet(base + 5_000, 0, d.ACT_OBSERVE)
        roots.append(unrelated_root)
        correction_refs = []
    else:
        raise ValueError(f"unknown alternate-evidence case code: {case_code}")

    if case_code in (1, 3, 6, 10, 12, 14):
        correction_refs = [correction_refs[0]]
    elif case_code == 15:
        # A simulated identity collision is rejected as non-independent: both
        # candidate paths intentionally share the only grounded root.
        correction_refs = [correction_refs[0]]

    # Roots are emitted once.  A shared root is deduplicated by numeric packet.
    unique_roots = tuple(dict.fromkeys(roots))
    root_frame = _world_frame(start_tick, unique_roots)
    derive_claims = tuple(claims)
    target_claims = tuple(
        StreamClaim(target, (leaf,)) for leaf in leaves
    )
    # Case 6 deliberately has only the bad pre-witness path; case 13 uses both
    # paths initially and restores one only after both have been witnessed away.
    if case_code == 6:
        target_claims = (target_claims[0],)
    derive_frame = _derive_frame(start_tick + 1, derive_claims + target_claims)

    # Case 5 makes the alternate ungrounded before the target exists.
    pre_frames = [root_frame, derive_frame]
    if case_code == 5:
        pre_frames.append(
            _correction_frame(
                start_tick + 2,
                target,
                (_packet(correction_refs[1], 1, d.ACT_OBSERVE),),
            )
        )
        correction_refs = [correction_refs[0]]
        correction_index = 3
    if case_code == 16:
        # Add the same semantic parent keys with a different lineage after an
        # independent root becomes grounded; this must not create independence.
        alternate_root = d.Packet(
            base + 1,
            d.ACT_OBSERVE,
            base + 1,
            d.REL_ABOVE,
            0,
            0,
        )
        pre_frames.append(
            _world_frame(start_tick + 2, (alternate_root,))
        )
        pre_frames.append(
            _derive_frame(
                start_tick + 3,
                (
                    _claim(base + 10, 0, ((base + 1, 0),)),
                    _claim(target_ref, target_value, (leaves[0],)),
                ),
            )
        )
        correction_index = 4

    correction_witnesses = tuple(
        _packet(reference, 1, d.ACT_OBSERVE) for reference in correction_refs
    )
    correction = _correction_frame(
        start_tick + correction_index,
        target,
        correction_witnesses,
        recomputed=recompute_claims,
    )
    frames = tuple(pre_frames) + (correction,)
    truth_value = 1 if case_code != 7 else 1
    return AlternateCaseSpec(
        event_id=event_id,
        case_code=case_code,
        case_name=CASE_NAMES[case_code - 1],
        target=target,
        frames=frames,
        correction_index=len(frames) - 1,
        truth_value=truth_value,
        recomputation_attempted=recomputation_attempted,
    )


def _consume_reference_event(
    epistemic_store: d.ReferenceProvenanceStore,
    frame: RecordedTransition,
) -> None:
    for claim in frame.predictions:
        if claim.packet.act == d.ACT_DERIVE:
            epistemic_store.derive(claim.packet, claim.semantic_parents)
        else:
            epistemic_store.propose(claim.packet)
    for packet in frame.witnesses:
        epistemic_store.observe(packet)


def evaluate_case(spec: AlternateCaseSpec) -> tuple[dict[str, object], tuple[RecordedTransition, ...]]:
    oracle = d.ReferenceProvenanceStore()
    before: StoreSnapshot | None = None
    after_witness: StoreSnapshot | None = None
    after_recompute: StoreSnapshot | None = None
    for index, frame in enumerate(spec.frames):
        if index == spec.correction_index:
            before = snapshot_store(oracle)
            _consume_reference_event(oracle, frame)
            after_witness = snapshot_store(oracle)
            for claim in frame.recomputed:
                if claim.packet.act == d.ACT_DERIVE:
                    oracle.derive(claim.packet, claim.semantic_parents)
                else:
                    oracle.propose(claim.packet)
            after_recompute = snapshot_store(oracle)
        else:
            _consume_reference_event(oracle, frame)
    if before is None or after_witness is None or after_recompute is None:
        raise RuntimeError("alternate challenge did not contain a correction event")
    event = classify_alternate_event(spec, before, after_witness, after_recompute)
    expected_opportunity = expected_metric_a_opportunity(spec.case_code)
    event["expected_metric_a_opportunity"] = expected_opportunity
    event["false_opportunity_classification"] = bool(
        event["metric_a_opportunity"] and not expected_opportunity
    )
    frames = list(spec.frames)
    correction = frames[spec.correction_index]
    if bool(event["metric_a_opportunity"]):
        frames[spec.correction_index] = replace(
            correction,
            preservation_targets=(StreamClaim(spec.target),),
        )
    return event, tuple(frames)


def build_alternate_evidence_challenge(
    episode_ordinal: int,
    *,
    valid_cases: int = 40,
    include_hostile: bool = True,
    start_tick: int = 1_000_000,
) -> tuple[tuple[RecordedTransition, ...], tuple[dict[str, object], ...], dict[str, object]]:
    """Build and independently audit one deterministic challenge episode."""

    if valid_cases < 1:
        raise ValueError("valid_cases must be positive")
    event_rows: list[dict[str, object]] = []
    frames: list[RecordedTransition] = []
    event_id_base = episode_ordinal * 1_000 + 1
    # Case 1 is intentionally represented by the guaranteed-positive workload.
    # The emitted hostile additions are codes 2--18, preserving all 18 hostile
    # behaviors without duplicating the same positive event construction.
    case_codes = [1] * valid_cases
    if include_hostile:
        case_codes.extend(EMITTED_HOSTILE_CASE_CODES)
    tick = start_tick
    for offset, case_code in enumerate(case_codes):
        spec = _build_case(event_id_base + offset, case_code, tick)
        event, case_frames = evaluate_case(spec)
        event["episode_ordinal"] = episode_ordinal
        event_rows.append(event)
        frames.extend(case_frames)
        tick += len(case_frames) + 1
    opportunities = sum(bool(row["metric_a_opportunity"]) for row in event_rows)
    successes = sum(bool(row["metric_a_success"]) for row in event_rows)
    false_classifications = sum(
        bool(row["false_opportunity_classification"])
        for row in event_rows
    )
    emitted_hostile_codes = sorted(
        {int(row["case_code"]) for row in event_rows if int(row["case_code"]) != 1}
    )
    positive_hostile_codes = sorted(
        {
            int(row["case_code"])
            for row in event_rows
            if int(row["case_code"]) != 1
            and bool(row["expected_metric_a_opportunity"])
        }
    )
    counts: dict[str, int] = {}
    for row in event_rows:
        name = str(row["primary_classification"])
        counts[name] = counts.get(name, 0) + 1
    summary = {
        "episode_ordinal": episode_ordinal,
        "guaranteed_valid_cases": valid_cases,
        "guaranteed_metric_a_opportunities": valid_cases,
        "guaranteed_positive_event_count": valid_cases,
        "guaranteed_positive_case_code": 1,
        "represented_hostile_case_codes": list(HOSTILE_CASE_CODES),
        "emitted_hostile_case_codes": emitted_hostile_codes,
        "additional_hostile_case_count": len(emitted_hostile_codes),
        "expected_positive_hostile_case_codes": list(POSITIVE_HOSTILE_CASE_CODES),
        "emitted_positive_hostile_case_codes": positive_hostile_codes,
        "expected_metric_a_opportunities": sum(
            bool(row["expected_metric_a_opportunity"]) for row in event_rows
        ),
        "event_count": len(event_rows),
        "metric_a_opportunities": opportunities,
        "metric_a_successes": successes,
        "metric_a_rate": successes / opportunities if opportunities else 1.0,
        "metric_b_opportunities": sum(bool(row["metric_b_opportunity"]) for row in event_rows),
        "metric_b_successes": sum(bool(row["metric_b_success"]) for row in event_rows),
        "false_opportunity_classifications": false_classifications,
        "classification_counts": counts,
    }
    return tuple(frames), tuple(event_rows), summary
