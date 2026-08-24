from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.erc3a.channel_schema import CHANNEL_SCHEMA, SAMPLE_COUNT, SAMPLE_RATE_HZ, TIME_COLUMN
from experiments.erc3b.protocol import (
    ARCHIVE_PUBLISHED_MD5,
    ARCHIVE_URL,
    EXPECTED_PKL_MEMBERS,
    EXPECTED_ROWS,
    EXPECTED_TARGETS,
    EXPECTED_TYPES,
    LABELS_MD5,
    LABELS_URL,
    PER_STRATUM,
)

CALIBRATION_COUNT = 8
SCIENCE_COUNT = 64
CALIBRATION_SALT = "ERC-3D-CAL-v1"
SCIENCE_SALT = "ERC-3D-SCI-v1"
OLD_ERC3A_MAP = Path("experiments/erc3a/ERC3A_ACQUISITION_MAP.json")
ERC3B_CALIBRATION_MAP = Path("experiments/erc3b/ERC3B_CALIBRATION_ACQUISITION_MAP.json")
ERC3B_SCIENCE_MAP = Path("experiments/erc3b/ERC3B_SCIENCE_ACQUISITION_MAP.json")
ERC3C_CALIBRATION_MAP = Path("experiments/erc3c/ERC3C_CALIBRATION_ACQUISITION_MAP.json")
ERC3C_SCIENCE_MAP = Path("experiments/erc3c/ERC3C_SCIENCE_ACQUISITION_MAP.json")
EXPECTED_COLUMNS = (TIME_COLUMN, *CHANNEL_SCHEMA)
EXPECTED_ERC3A_IDS_SHA256 = "aef9418b6ee352f0c2ab96ac6ecb7e097aa834662a646453495905a1c6dcf6db"
EXPECTED_ERC3B_CALIBRATION_IDS_SHA256 = "eb22af50794fd52b5dca50bfea97aeec733ef2b829c870299b261d2012f0cec1"
EXPECTED_ERC3B_SCIENCE_IDS_SHA256 = "2c7709b66306bd4f3c2b9bf5c7e0ee1aea0177a360ab29e4e1c12d0a7be8778e"
EXPECTED_ERC3C_CALIBRATION_IDS_SHA256 = "0659bbd0bded89a50e569f79e097ee8489e74961b4a4d8c0c28ab12657432781"
EXPECTED_ERC3C_SCIENCE_IDS_SHA256 = "e0d79911fa5fba0fdceed5f8ab1d67116b3f12c35f322f8b11e4f5b80799ec95"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def opaque_id(prefix: str, sample_id: int) -> str:
    # Raw sample IDs remain inside the private selector only.
    return f"{prefix}-" + sha256_text(f"{prefix}|{sample_id}")[:24]
