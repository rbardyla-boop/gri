from __future__ import annotations

import json
import sys


def main() -> None:
    fixture = json.load(sys.stdin)
    if set(fixture) < {"id", "kind", "prompt", "target"}:
        raise ValueError("invalid synthetic fixture")
    json.dump({"prediction": fixture["target"]}, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
