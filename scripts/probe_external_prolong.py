#!/usr/bin/env python3
"""Audit PRO-LONG's published GPT-5.5 matched-action comparison and lineage.

The 500-action PRO-LONG scorecard describes itself as the 1,000-action run
"truncated at 500 actions". This probe checks both the attractive matched-budget
comparison and whether that stated lineage reconciles game-by-game with the
published 1,000-action scorecard at the same pinned commit.

A lineage mismatch does not prove the result is false. It means Gauntlet cannot
admit the re-score as clean mechanism-credit evidence without reconciliation.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path


REPO = "alexisfox7/PRO-LONG"
COMMIT = "9d2f2d46fea8759ed494ce5b0166c7004a2e97c4"
ROOT = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/research/arc-agi-3/scorecards"
FULL_URL = f"{ROOT}/prolong_r3_online_scorecards.txt"
AT500_URL = f"{ROOT}/prolong_r3_online_scorecards_at500.txt"
BASELINE_URL = f"{ROOT}/inprompt_r3_online_scorecards.txt"
OUTPUT = Path(".gauntlet/external-prolong-evidence.json")

GAME_RE = re.compile(
    r"^(?P<game>[a-z0-9]+)\s+(?P<score>\d+(?:\.\d+)?)%\s+levels=(?P<levels>\d+/\d+)\s+acts=(?P<acts>\d+)"
    r"(?:\s+\(full:\s*(?P<full>\d+(?:\.\d+)?)%\))?\s*$"
)
REPLAY_RE = re.compile(r"^\s*replay:\s+(?P<url>https://arcprize\.org/replay/[A-Za-z0-9-]+)\s*$")
MEAN_RE = re.compile(r"Mean:\s*(?P<mean>\d+(?:\.\d+)?)%")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "gri-gauntlet-external-probe/1"})
    with urllib.request.urlopen(req, timeout=60) as response:
        if getattr(response, "status", 200) != 200:
            raise RuntimeError(f"unexpected HTTP status for {url}: {response.status}")
        return response.read()


def parse_scorecard(text: str) -> dict:
    games: dict[str, dict] = {}
    pending: str | None = None
    for raw in text.splitlines():
        game_match = GAME_RE.match(raw)
        if game_match:
            game = game_match.group("game")
            if game in games:
                raise RuntimeError(f"duplicate game row: {game}")
            games[game] = {
                "score": float(game_match.group("score")),
                "levels": game_match.group("levels"),
                "acts": int(game_match.group("acts")),
                "reported_full_score": (
                    float(game_match.group("full")) if game_match.group("full") is not None else None
                ),
                "replay": None,
            }
            pending = game
            continue
        replay_match = REPLAY_RE.match(raw)
        if replay_match and pending is not None:
            games[pending]["replay"] = replay_match.group("url")
            pending = None

    mean_match = MEAN_RE.search(text)
    if mean_match is None:
        raise RuntimeError("scorecard mean not found")
    if len(games) != 25:
        raise RuntimeError(f"expected 25 game rows, got {len(games)}")
    if any(row["replay"] is None for row in games.values()):
        raise RuntimeError("one or more game rows lack replay URLs")
    return {"mean": float(mean_match.group("mean")), "games": games}


def setting(text: str, key: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    return match.group(1) if match else None


def main() -> int:
    full_bytes = fetch(FULL_URL)
    at500_bytes = fetch(AT500_URL)
    baseline_bytes = fetch(BASELINE_URL)
    full_text = full_bytes.decode("utf-8")
    at500_text = at500_bytes.decode("utf-8")
    baseline_text = baseline_bytes.decode("utf-8")

    if "truncated at 500 actions" not in at500_text or "scored at 500-action cutoff" not in at500_text:
        raise RuntimeError("500-action scorecard no longer states the expected truncation lineage")

    full = parse_scorecard(full_text)
    at500 = parse_scorecard(at500_text)
    baseline = parse_scorecard(baseline_text)

    if full["mean"] != 50.2 or at500["mean"] != 45.6 or baseline["mean"] != 24.7:
        raise RuntimeError(
            f"pinned means changed: full={full['mean']}, at500={at500['mean']}, baseline={baseline['mean']}"
        )

    common_settings = ("backend", "reasoning-effort", "operation-mode", "grid-mode", "session-mode")
    settings_equal = {
        key: setting(at500_text, key) == setting(baseline_text, key) and setting(at500_text, key) is not None
        for key in common_settings
    }
    candidate_action_cap = setting(at500_text, "action-cap")
    baseline_action_cap = setting(baseline_text, "action-cap")
    action_cap_equal = candidate_action_cap == baseline_action_cap == "20"
    candidate_scored_actions = 500 if "scored at 500-action cutoff" in at500_text else None
    baseline_max_actions = int(setting(baseline_text, "max-actions") or -1)

    replay_mismatches: list[str] = []
    reported_full_score_mismatches: list[str] = []
    impossible_prefix_rows: list[str] = []
    for game in sorted(full["games"]):
        source = full["games"][game]
        truncated = at500["games"][game]
        if source["replay"] != truncated["replay"]:
            replay_mismatches.append(game)
        if truncated["reported_full_score"] != source["score"]:
            reported_full_score_mismatches.append(game)
        # If the source run itself ended within 500 actions and the re-score
        # claims the same replay, a prefix truncation should not require more
        # actions than the source. Record suspicious rows rather than attempting
        # to infer ARC's scoring semantics.
        if (
            source["acts"] <= 500
            and source["replay"] == truncated["replay"]
            and truncated["acts"] > source["acts"]
        ):
            impossible_prefix_rows.append(game)

    lineage_pass = not replay_mismatches and not reported_full_score_mismatches and not impossible_prefix_rows

    evidence = {
        "schema_version": 1,
        "probe_type": "PINNED_PUBLIC_SOURCE_RETROSPECTIVE",
        "source": {
            "repository": REPO,
            "commit": COMMIT,
            "files": {
                "full": {"url": FULL_URL, "sha256": hashlib.sha256(full_bytes).hexdigest()},
                "at500": {"url": AT500_URL, "sha256": hashlib.sha256(at500_bytes).hexdigest()},
                "baseline": {"url": BASELINE_URL, "sha256": hashlib.sha256(baseline_bytes).hexdigest()},
            },
        },
        "published": {
            "full_1000_mean": full["mean"],
            "candidate_500_rescore_mean": at500["mean"],
            "baseline_500_mean": baseline["mean"],
            "matched_gap_points": round(at500["mean"] - baseline["mean"], 10),
        },
        "matched_budget": {
            "candidate_scored_actions": candidate_scored_actions,
            "baseline_max_actions": baseline_max_actions,
            "action_budget_equal": candidate_scored_actions == baseline_max_actions == 500,
            "action_cap_equal": action_cap_equal,
            "settings_equal": settings_equal,
            "all_common_settings_equal": all(settings_equal.values()),
        },
        "lineage": {
            "claimed_truncation_of_1000_action_run": True,
            "pass": lineage_pass,
            "replay_mismatches": replay_mismatches,
            "reported_full_score_mismatches": reported_full_score_mismatches,
            "impossible_prefix_rows": impossible_prefix_rows,
        },
        "boundary": {
            "fresh_rerun": False,
            "result_falsehood_established": False,
            "mechanism_credit_admissible_without_reconciliation": lineage_pass,
        },
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
