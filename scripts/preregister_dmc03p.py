#!/usr/bin/env python3
"""Generate the DMC-03P structural preregistration receipt only."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dmc03p.preregistration import generate_artifacts


if __name__ == "__main__":
    import json

    print(json.dumps(generate_artifacts(), indent=2, sort_keys=True))
