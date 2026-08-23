from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path
from typing import Any

from .core import read_json


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _install_guard(manifest: dict[str, Any]) -> None:
    root = Path(manifest["root"]).resolve()
    protected = tuple((root / value).resolve() for value in manifest.get("protected_roots", []))
    run_cfg = manifest.get("run", {})
    deny_subprocess = bool(run_cfg.get("deny_subprocess", True))
    deny_network = bool(run_cfg.get("deny_network", False))

    def audit(event: str, args: tuple[Any, ...]) -> None:
        if event == "open" and args:
            raw = args[0]
            if isinstance(raw, (str, bytes, os.PathLike)):
                try:
                    candidate = Path(raw).resolve()
                except (OSError, TypeError, ValueError):
                    candidate = None
                if candidate is not None and any(_is_within(candidate, protected_root) for protected_root in protected):
                    raise PermissionError(f"GAUNTLET_HOLDOUT_VIOLATION: open blocked: {candidate}")

        if deny_subprocess and (
            event.startswith("subprocess.")
            or event == "os.system"
            or event.startswith("os.exec")
            or event.startswith("os.spawn")
        ):
            raise PermissionError(f"GAUNTLET_SUBPROCESS_VIOLATION: {event}")

        if deny_network and event == "socket.connect":
            raise PermissionError("GAUNTLET_NETWORK_VIOLATION: socket.connect")

    sys.addaudithook(audit)


def _install_target_paths(root: Path) -> None:
    """Expose target-project imports only after the trusted guard is loaded.

    The parent process starts this module with Python isolated mode, so a target
    repository cannot replace ``gauntlet._guard_exec`` through CWD or
    ``PYTHONPATH`` shadowing. Once this trusted module and its audit hook are
    resident, the normal project root/src paths are added for the experiment
    entrypoint itself.
    """

    candidates = [root, root / "src"]
    for candidate in reversed(candidates):
        if candidate.is_dir():
            resolved = str(candidate.resolve())
            if resolved not in sys.path:
                sys.path.insert(0, resolved)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python -m gauntlet._guard_exec MANIFEST", file=sys.stderr)
        return 2
    manifest_path = Path(argv[0]).resolve()
    manifest = read_json(manifest_path)
    root = Path(manifest["root"]).resolve()
    run_cfg = manifest["run"]
    if run_cfg.get("mode") != "python":
        print("guard executor requires run.mode='python'", file=sys.stderr)
        return 2

    entry = (root / str(run_cfg["entry"])).resolve()
    try:
        entry.relative_to(root)
    except ValueError:
        print("python entry escapes experiment root", file=sys.stderr)
        return 2
    if not entry.is_file():
        print(f"python entry missing: {entry}", file=sys.stderr)
        return 2

    _install_guard(manifest)
    _install_target_paths(root)
    old_argv = sys.argv
    sys.argv = [str(entry), *[str(value) for value in run_cfg.get("args", [])]]
    try:
        runpy.run_path(str(entry), run_name="__main__")
    except SystemExit as exc:
        if exc.code is None:
            return 0
        if isinstance(exc.code, int):
            return exc.code
        print(str(exc.code), file=sys.stderr)
        return 1
    finally:
        sys.argv = old_argv
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
