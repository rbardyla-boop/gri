from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

# This is intentionally broader than the four-key regression inherited from
# ERC-3A.  The calibration/science producer boundary cannot carry truth,
# source identity, or resistance metadata.
FORBIDDEN_PRODUCER_FIELDS = frozenset(
    {
        "sample_id",
        "fault_target",
        "sc_type",
        "sc_location",
        "fault_resistance",
        "resistance",
        "truth",
        "scorer_map",
    }
)
_FORBIDDEN_JSON_KEY = re.compile(
    r'"(?:sample_id|fault_target|sc_type|sc_location|fault_resistance|resistance|truth|scorer_map)"\s*:'
)


def json_files(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".json":
            files.append(path)
        elif path.is_dir():
            files.extend(p for p in path.rglob("*.json") if p.is_file())
    return sorted(set(files))


def _walk_keys(value: object, location: str = "$") -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_PRODUCER_FIELDS:
                violations.append(f"{location}.{key}")
            violations.extend(_walk_keys(child, f"{location}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_walk_keys(child, f"{location}[{index}]"))
    return violations


def scan(paths: Iterable[Path]) -> dict[str, list[str]]:
    violations: dict[str, list[str]] = {}
    for path in json_files(paths):
        raw = path.read_text(encoding="utf-8")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid producer-visible JSON: {path}: {exc}") from exc
        found = _walk_keys(value)
        if _FORBIDDEN_JSON_KEY.search(raw):
            found.append("raw-json-key")
        if found:
            violations[str(path)] = sorted(set(found))
    return violations


def assert_clean(paths: Iterable[Path]) -> None:
    violations = scan(paths)
    if violations:
        raise AssertionError(f"ERC3B producer identity leakage: {json.dumps(violations, sort_keys=True)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    assert_clean(args.paths)
    print("ERC3B_PRODUCER_IDENTITY_BOUNDARY_PASS")


if __name__ == "__main__":
    main()
