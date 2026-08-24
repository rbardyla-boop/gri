from __future__ import annotations

import hashlib

COMPILER_SHA256 = "2d7135512894736281d1d0381a07bd76e1eb0052cf61c61ae5359f02f2d1288d"
DATA_BINDING_RECORD_SHA256 = "d9cb7cd9220efc2e1214010d3febc289fbf011678fb74e85d086649f16dcedf1"
WINDOW_SECONDS = 300
EXPECTED_CASES = 13
EXPECTED_PER_ACTUATOR = {"A1": 6, "A2": 5, "A3": 2}

ARCHIVES = {
    "part2": {
        "url": "https://iair.mchtr.pw.edu.pl/content/download/164/821/file/Lublin_all_data_part2.zip",
        "sha256": "5e23c3b0e5adcb50541704024846d54f33bc374e1fd36f50b1043a663dfba803",
    },
    "part3": {
        "url": "https://iair.mchtr.pw.edu.pl/content/download/165/825/file/Lublin_all_data_part3.zip",
        "sha256": "2e961f290e3a7fdd3ebf3e2688af207cd1affef065aae13e3fb68755f7ee9628",
    },
    "part4": {
        "url": "https://iair.mchtr.pw.edu.pl/content/download/166/829/file/Lublin_all_data_part4.zip",
        "sha256": "d8a61f82c3b66df5f566bc8c78060db678cc886ab94f4059bab5de3b68784cf2",
    },
}

DAYS = {
    "2001-10-30": {
        "archive": "part4",
        "member": "Lublin_all_data/30102001.txt",
        "raw_sha256": "75706a15cff60b132ae7fd291ce08a06bb0ef0df6ed65a15cb05fe18889363d1",
    },
    "2001-11-09": {
        "archive": "part2",
        "member": "Lublin_all_data/09112001.txt",
        "raw_sha256": "b3af2f899fe23c2826a0821fd9024a9dcc6c1a7f99e2191b752bb6b4a218d488",
    },
    "2001-11-17": {
        "archive": "part3",
        "member": "Lublin_all_data/17112001.txt",
        "raw_sha256": "2744046eedf781c157f0bc02db96be2b3651063112d04d2e80f56260594b1538",
    },
    "2001-11-20": {
        "archive": "part3",
        "member": "Lublin_all_data/20112001.txt",
        "raw_sha256": "8ce1310dcfb8f4907aecc2414dc8dbd013b382cf9fc08e45b2e740b74f9fec79",
    },
}

# Mechanically derived by terminal ERC-2A schedule qualification.  No target
# actuator is present here; the live producer is intentionally truth-blind.
EVENTS_PUBLIC = (
    {"item": 1, "date": "2001-10-30", "start": 58800},
    {"item": 2, "date": "2001-11-09", "start": 57275},
    {"item": 4, "date": "2001-11-09", "start": 58520},
    {"item": 5, "date": "2001-11-17", "start": 54600},
    {"item": 6, "date": "2001-11-17", "start": 56670},
    {"item": 7, "date": "2001-11-20", "start": 37780},
    {"item": 8, "date": "2001-11-17", "start": 53780},
    {"item": 9, "date": "2001-11-17", "start": 54193},
    {"item": 10, "date": "2001-11-17", "start": 55482},
    {"item": 11, "date": "2001-11-17", "start": 55977},
    {"item": 13, "date": "2001-11-20", "start": 44400},
    {"item": 14, "date": "2001-10-30", "start": 57340},
    {"item": 19, "date": "2001-11-17", "start": 58150},
)

# Official DAMADICS columns are 1-based.  Column 1 is time.  The three
# actuator-local six-signal blocks are contiguous and are projected without
# smoothing, resampling, interpolation, feature construction, or category
# relabeling.
SIGNAL_COLUMNS = (
    (2, "A1_P1"), (3, "A1_P2"), (4, "A1_T1"), (5, "A1_F"), (6, "A1_CV"), (7, "A1_X"),
    (18, "A2_P1"), (19, "A2_P2"), (20, "A2_T1"), (21, "A2_F"), (22, "A2_CV"), (23, "A2_X"),
    (24, "A3_P1"), (25, "A3_P2"), (26, "A3_T1"), (27, "A3_F"), (28, "A3_CV"), (29, "A3_X"),
)


def opaque_id(event: dict) -> str:
    payload = f"ERC2AR|{event['item']}|{event['date']}|{event['start']}"
    return "E1-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def expected_opaque_ids() -> tuple[str, ...]:
    return tuple(opaque_id(event) for event in EVENTS_PUBLIC)
