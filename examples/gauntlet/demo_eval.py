from __future__ import annotations

import json
from pathlib import Path


result = {
    "candidate": {"accuracy": 0.80},
    "baseline": {"accuracy": 0.50},
    "integrity": {"schema_valid": True},
}

output = Path(".gauntlet/demo_result.json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
