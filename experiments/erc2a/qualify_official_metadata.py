from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

DATES = ("October 30, 2001", "November 9, 2001", "November 17, 2001", "November 20, 2001")
EXPECTED_EVENTS = 19
CANONICAL_SIGNALS = {
    "A1": {
        "P1": "P51_05",
        "P2": "P51_06",
        "T1": "T51_01",
        "F": "F51_01",
        "CV": "LC51_03CV",
        "X": "LC51_03X",
    },
    "A2": {
        "P1": "P57_03",
        "P2": "P57_04",
        "T1": "T57_03",
        "F": "FC57_03PV",
        "CV": "FC57_03CV",
        "X": "FC57_03X",
    },
    "A3": {
        "P1": "P74_00",
        "P2": "P74_01",
        "T1": "T74_00",
        "F": "F74_00",
        "CV": "LC74_20CV",
        "X": "LC74_20X",
    },
}


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def iso_date(value: str) -> str:
    return datetime.strptime(value, "%B %d, %Y").date().isoformat()


def _table_rows(text: str) -> list[tuple[str, str]]:
    """Reconstruct logical fault-table rows from PDF-extracted wrapped lines.

    The official PDF wraps ordinary descriptions and, for item 10, even
    separates the item/fault prefix from the sample/date onto the next line.
    A logical row therefore begins only at an item-number + fault-tag prefix
    and continues until another such prefix or a new actuator table begins.
    """
    rows: list[tuple[str, str]] = []
    actuator: str | None = None
    pending: list[str] = []

    def flush() -> None:
        nonlocal pending
        if actuator is not None and pending:
            row = " ".join(pending).strip()
            if any(date in row for date in DATES):
                rows.append((actuator, row))
        pending = []

    for raw in text.splitlines():
        line = " ".join(raw.split())
        if "Table 3. Index of artificial faults introduced in Actuator 1" in line:
            flush()
            actuator = "A1"
            continue
        if "Table 4. Index of artificial faults introduced in Actuator 2" in line:
            flush()
            actuator = "A2"
            continue
        if "Table 5. Index of artificial faults introduced in Actuator 3" in line:
            flush()
            actuator = "A3"
            continue
        if actuator is None:
            continue
        if line.startswith("=====") or line.startswith("Item Fault tag"):
            continue

        is_new_row = re.match(r"^\d+\s+f\d+", line, flags=re.I) is not None
        if is_new_row:
            flush()
            pending = [line]
        elif pending:
            pending.append(line)

    flush()
    return rows


def parse_events(text: str) -> list[dict]:
    events: list[dict] = []
    for actuator, line in _table_rows(text):
        date_match = next((date for date in DATES if date in line), None)
        if date_match is None:
            raise ValueError(f"fault row missing expected date: {line}")
        # The official PDF renders the f19 footnote marker as `f194)`.
        # Limit the actual fault number to two digits, then consume optional
        # footnote `4)` separately.
        match = re.match(
            r"^(?P<item>\d+)\s+f(?P<fault>\d{1,2})(?:4\))?\s+"
            r"(?P<sample>(?:\d+\s*-\s*\d+)|(?:start at\s+\d+))\s+",
            line,
            flags=re.I,
        )
        if not match:
            raise ValueError(f"unparsed artificial-fault row: {line}")
        sample = re.sub(r"\s+", " ", match.group("sample")).strip()
        if sample.lower().startswith("start at"):
            start = int(sample.split()[-1])
            end = 86400
            open_ended = True
        else:
            left, right = re.split(r"\s*-\s*", sample)
            start, end = int(left), int(right)
            open_ended = False
        events.append(
            {
                "item": int(match.group("item")),
                "actuator": actuator,
                "fault": "f" + match.group("fault"),
                "date": iso_date(date_match),
                "start": start,
                "end": end,
                "open_ended": open_ended,
            }
        )

    events.sort(key=lambda row: row["item"])
    if len(events) != EXPECTED_EVENTS or [row["item"] for row in events] != list(range(1, EXPECTED_EVENTS + 1)):
        raise ValueError(f"expected items 1..19, parsed {len(events)} rows: {[r['item'] for r in events]}")
    return events


def classify_window_confounds(events: list[dict]) -> tuple[list[dict], list[dict]]:
    clean = []
    confounded = []
    for event in events:
        window_start = event["start"] - 300
        window_end = event["start"] + 300
        conflicts = []
        for other in events:
            if other["item"] == event["item"] or other["date"] != event["date"]:
                continue
            if other["start"] < window_end and other["end"] > window_start:
                conflicts.append(other["item"])
        row = {
            **event,
            "analysis_window": [window_start, window_end],
            "conflicting_items": conflicts,
        }
        if window_start < 0 or window_end > 86400 or conflicts:
            confounded.append(row)
        else:
            clean.append(row)
    return clean, confounded


def qualify_signal_map(text: str) -> dict:
    missing = []
    duplicate_symbol_assignments = []
    all_symbols: list[str] = []
    for actuator, mapping in CANONICAL_SIGNALS.items():
        for canonical, symbol in mapping.items():
            hits = len(re.findall(rf"\b{re.escape(symbol)}\b", text))
            if hits < 1:
                missing.append({"actuator": actuator, "canonical": canonical, "symbol": symbol})
            all_symbols.append(symbol)
    if len(set(all_symbols)) != len(all_symbols):
        duplicate_symbol_assignments = sorted(symbol for symbol in set(all_symbols) if all_symbols.count(symbol) > 1)
    return {
        "expected_actuators": 3,
        "expected_signals_per_actuator": 6,
        "mapping": CANONICAL_SIGNALS,
        "missing": missing,
        "duplicate_symbol_assignments": duplicate_symbol_assignments,
        "pass": not missing and not duplicate_symbol_assignments,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--description-text", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    description = args.description_text.read_text(encoding="utf-8")
    events = parse_events(description)
    clean, confounded = classify_window_confounds(events)
    signal_map = qualify_signal_map(description)

    all_windows_clean = len(clean) == EXPECTED_EVENTS
    if not signal_map["pass"]:
        status = "ERC2A_COLUMN_MAP_QUALIFICATION_FAIL"
    elif not all_windows_clean:
        status = "ERC2A_SCHEDULE_QUALIFICATION_FAIL"
    else:
        status = "ERC2A_METADATA_QUALIFICATION_PASS"

    result = {
        "unit": "ERC-2A",
        "status": status,
        "telemetry_downloaded": False,
        "scientific_predictions": 0,
        "scorer_opened": False,
        "event_count": len(events),
        "clean_event_count": len(clean),
        "confounded_event_count": len(confounded),
        "events": events,
        "clean_events": clean,
        "confounded_events": confounded,
        "signal_map": signal_map,
        "description_text_sha256": sha256_text(description),
    }
    result["record_sha256"] = sha256_text(canonical_json(result))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "unit": result["unit"],
        "status": result["status"],
        "event_count": result["event_count"],
        "clean_event_count": result["clean_event_count"],
        "confounded_event_count": result["confounded_event_count"],
        "signal_map_pass": result["signal_map"]["pass"],
        "clean_items": [row["item"] for row in clean],
        "confounded_items": [row["item"] for row in confounded],
        "record_sha256": result["record_sha256"],
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
