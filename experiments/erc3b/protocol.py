from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.erc3a.channel_schema import CHANNEL_SCHEMA, SAMPLE_COUNT, TIME_COLUMN

LABELS_URL = "https://zenodo.org/records/21109169/files/hv_double_line_90kv_labels.csv?download=1"
LABELS_MD5 = "5f015330f77ed53b76bd5db26e83c48d"
ARCHIVE_URL = "https://zenodo.org/records/21109169/files/hv_double_line_90kv_preprocessed_data.zip?download=1"
ARCHIVE_PUBLISHED_MD5 = "7cf176f169299b825ba6a6be102edca8"
EXPECTED_ROWS = 9022
EXPECTED_PKL_MEMBERS = 9022
CALIBRATION_COUNT = 8
SCIENCE_COUNT = 64
PER_STRATUM = 4
EXPECTED_TARGETS = ("Line_1_2_a", "Line_1_2_b", "Line_2_3_a", "Line_2_3_b")
EXPECTED_TYPES = (0, 1, 2, 3)
CALIBRATION_SALT = "ERC3B-TIMEBASE-CAL-v1"
SCIENCE_SALT = "ERC3B-PROTECT90-SCI-v1"
OLD_ERC3A_MAP = Path("experiments/erc3a/ERC3A_ACQUISITION_MAP.json")
EXPECTED_OLD_ERC3A_IDS_SHA256 = "aef9418b6ee352f0c2ab96ac6ecb7e097aa834662a646453495905a1c6dcf6db"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: object) -> str:
    return sha256_text(canonical_json(value))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def opaque_id(prefix: str, sample_id: int) -> str:
    # The raw ID is used only inside this private selector and never emitted in
    # a producer-visible object.
    return f"{prefix}-" + sha256_text(f"{prefix}|{sample_id}")[:24]


def expected_columns() -> tuple[str, ...]:
    return (TIME_COLUMN, *CHANNEL_SCHEMA)


def frozen_schema_record() -> dict:
    return {
        "time_column": TIME_COLUMN,
        "sample_count": SAMPLE_COUNT,
        "channel_count": len(CHANNEL_SCHEMA),
        "channel_schema": list(CHANNEL_SCHEMA),
    }
