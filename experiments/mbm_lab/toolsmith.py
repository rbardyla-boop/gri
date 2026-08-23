from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REQUIRED = {"name", "command", "timeout_seconds", "network", "description"}

WRAPPER = '''from __future__ import annotations
import json
import subprocess
import sys

NAME = {name!r}
COMMAND = {command!r}
TIMEOUT = {timeout!r}
NETWORK = {network!r}


def main() -> None:
    payload = json.load(sys.stdin)
    proc = subprocess.run(
        COMMAND,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=TIMEOUT,
        check=False,
    )
    result = {{
        "tool": NAME,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }}
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\\n")


if __name__ == "__main__":
    main()
'''

SMOKE = '''from pathlib import Path
import subprocess
import sys


def test_wrapper_exists_and_compiles():
    path = Path(__file__).with_name({wrapper_name!r})
    assert path.is_file()
    subprocess.run([sys.executable, "-m", "py_compile", str(path)], check=True)
'''


def validate(contract: dict) -> None:
    missing = REQUIRED - set(contract)
    if missing:
        raise ValueError(f"missing fields: {sorted(missing)}")
    if set(contract) - REQUIRED:
        raise ValueError(f"unexpected fields: {sorted(set(contract) - REQUIRED)}")
    name = contract["name"]
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", name):
        raise ValueError("invalid tool name")
    command = contract["command"]
    if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x for x in command):
        raise ValueError("command must be a non-empty string array")
    timeout = contract["timeout_seconds"]
    if not isinstance(timeout, (int, float)) or timeout <= 0 or timeout > 3600:
        raise ValueError("timeout_seconds must be >0 and <=3600")
    if type(contract["network"]) is not bool:
        raise ValueError("network must be boolean")
    if not isinstance(contract["description"], str) or not contract["description"].strip():
        raise ValueError("description required")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    validate(contract)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    wrapper = args.out_dir / f"{contract['name']}.py"
    test = args.out_dir / f"test_{contract['name']}.py"
    if wrapper.exists() or test.exists():
        raise FileExistsError("tool output already exists")

    wrapper.write_text(
        WRAPPER.format(
            name=contract["name"],
            command=contract["command"],
            timeout=contract["timeout_seconds"],
            network=contract["network"],
        ),
        encoding="utf-8",
    )
    test.write_text(SMOKE.format(wrapper_name=wrapper.name), encoding="utf-8")
    print(json.dumps({
        "status": "TOOLSMITH_CREATED",
        "name": contract["name"],
        "wrapper": str(wrapper),
        "test": str(test),
        "network": contract["network"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
