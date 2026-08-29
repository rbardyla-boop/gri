from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from generate_sem0r import build_dataset
from sem0r_gen_core import FAMILIES, LABELS

EXPECTED = {
    'cases': 72,
    'pairs': 36,
    'decisions': 457,
    'families': 8,
    'revision_pairs': 18,
    'invariance_pairs': 18,
    'label_patterns': 47,
    'max_pattern_frequency': 4,
    'min_props': 5,
    'max_props': 8,
}


def validate() -> dict[str, Any]:
    cases, golds = build_dataset()
    errors: list[str] = []
    if len(cases) != EXPECTED['cases']:
        errors.append(f"case count {len(cases)}")
    if len(golds) != len(cases):
        errors.append('case/gold count mismatch')
    ids = [c['id'] for c in cases]
    if len(ids) != len(set(ids)):
        errors.append('duplicate case ids')
    gold_by_id = {g['id']: g for g in golds}
    if set(ids) != set(gold_by_id):
        errors.append('case/gold id mismatch')
    pair_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    patterns = Counter()
    family_counts = Counter()
    decisions = 0
    one_each = 0
    for case in cases:
        family_counts[case['family']] += 1
        if case['family'] not in FAMILIES:
            errors.append(f"unknown family {case['family']}")
        if case['pair_kind'] not in {'REVISION', 'INVARIANCE'}:
            errors.append(f"bad pair kind {case['id']}")
        pair_map[case['pair_id']].append(case)
        pids = [p['id'] for p in case['propositions']]
        sids = {s['id'] for s in case['context']}
        if not EXPECTED['min_props'] <= len(pids) <= EXPECTED['max_props']:
            errors.append(f"prop count out of range {case['id']}={len(pids)}")
        if len(pids) != len(set(pids)):
            errors.append(f"duplicate proposition id {case['id']}")
        if case['focus_proposition'] not in set(pids):
            errors.append(f"focus missing {case['id']}")
        gold = gold_by_id[case['id']]['gold']
        if set(gold) != set(pids):
            errors.append(f"gold proposition mismatch {case['id']}")
        local = Counter()
        for pid, item in gold.items():
            label = item.get('label')
            if label not in LABELS:
                errors.append(f"invalid label {case['id']}:{pid}:{label}")
            local[label] += 1
            evidence = item.get('evidence')
            if not isinstance(evidence, list):
                errors.append(f"bad evidence list {case['id']}:{pid}")
            elif any(eid not in sids for eid in evidence):
                errors.append(f"foreign evidence id {case['id']}:{pid}")
        if all(local[l] == 1 for l in LABELS):
            one_each += 1
        patterns[tuple(local[l] for l in LABELS)] += 1
        decisions += len(pids)
    if set(family_counts) != set(FAMILIES):
        errors.append(f"family set mismatch {sorted(family_counts)}")
    if len(pair_map) != EXPECTED['pairs']:
        errors.append(f"pair count {len(pair_map)}")
    revision = invariance = 0
    for pair_id, rows in pair_map.items():
        if len(rows) != 2 or {r['variant'] for r in rows} != {'A', 'B'}:
            errors.append(f"pair shape {pair_id}")
            continue
        kinds = {r['pair_kind'] for r in rows}
        if len(kinds) != 1:
            errors.append(f"pair kind mismatch {pair_id}")
        elif 'REVISION' in kinds:
            revision += 1
        else:
            invariance += 1
    if decisions != EXPECTED['decisions']:
        errors.append(f"decision count {decisions}")
    if revision != EXPECTED['revision_pairs']:
        errors.append(f"revision pairs {revision}")
    if invariance != EXPECTED['invariance_pairs']:
        errors.append(f"invariance pairs {invariance}")
    if len(patterns) != EXPECTED['label_patterns']:
        errors.append(f"label patterns {len(patterns)}")
    maxfreq = max(patterns.values()) if patterns else 0
    if maxfreq != EXPECTED['max_pattern_frequency']:
        errors.append(f"max pattern frequency {maxfreq}")
    if one_each != 0:
        errors.append(f"one-of-each cases {one_each}")
    result = {
        'status': 'PASS' if not errors else 'FAIL',
        'errors': errors,
        'case_count': len(cases),
        'pair_count': len(pair_map),
        'decision_count': decisions,
        'family_count': len(family_counts),
        'revision_pairs': revision,
        'invariance_pairs': invariance,
        'label_patterns': len(patterns),
        'max_pattern_frequency': maxfreq,
        'one_of_each_cases': one_each,
        'prop_count_distribution': dict(sorted(Counter(len(c['propositions']) for c in cases).items())),
        'global_label_counts': dict(Counter(item['label'] for g in golds for item in g['gold'].values())),
    }
    if errors:
        raise AssertionError(json.dumps(result, indent=2, sort_keys=True))
    return result


if __name__ == '__main__':
    print(json.dumps(validate(), indent=2, sort_keys=True))
