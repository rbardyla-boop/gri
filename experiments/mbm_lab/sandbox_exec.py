from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def limits(memory_mb: int, cpu_seconds: int, pids: int):
    def apply() -> None:
        if memory_mb > 0:
            cap = memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        if cpu_seconds > 0:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        if pids > 0 and hasattr(resource, "RLIMIT_NPROC"):
            resource.setrlimit(resource.RLIMIT_NPROC, (pids, pids))
    return apply


def build_bwrap(workspace: Path, command: list[str], network: bool) -> list[str]:
    cmd = [
        "bwrap",
        "--die-with-parent",
        "--new-session",
        "--unshare-user",
        "--unshare-pid",
        "--unshare-uts",
        "--unshare-ipc",
        "--ro-bind", "/", "/",
        "--bind", str(workspace), str(workspace),
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "--chdir", str(workspace),
    ]
    if not network:
        cmd.append("--unshare-net")
    return cmd + ["--"] + command


def build_podman(workspace: Path, command: list[str], network: bool, image: str, memory_mb: int, pids: int) -> list[str]:
    cmd = [
        "podman", "run", "--rm",
        "--read-only",
        "--userns=keep-id",
        "--security-opt=no-new-privileges",
        "--cap-drop=ALL",
        "--pids-limit", str(pids),
        "--memory", f"{memory_mb}m",
        "-v", f"{workspace}:/work:rw,Z",
        "-w", "/work",
    ]
    cmd += ["--network", "slirp4netns"] if network else ["--network", "none"]
    return cmd + [image] + command


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", type=Path, default=Path.cwd())
    ap.add_argument("--backend", choices=["auto", "bwrap", "podman"], default="auto")
    ap.add_argument("--image", default="python:3.12-slim")
    ap.add_argument("--network", action="store_true")
    ap.add_argument("--memory-mb", type=int, default=2048)
    ap.add_argument("--cpu-seconds", type=int, default=300)
    ap.add_argument("--pids", type=int, default=128)
    ap.add_argument("--timeout", type=float, default=330.0)
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("command", nargs=argparse.REMAINDER)
    args = ap.parse_args()

    if not args.command:
        raise SystemExit("command required after --")
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    workspace = args.workspace.resolve()
    if not workspace.is_dir():
        raise NotADirectoryError(workspace)
    if args.receipt.exists():
        raise FileExistsError(args.receipt)

    backend = args.backend
    if backend == "auto":
        if shutil.which("bwrap"):
            backend = "bwrap"
        elif shutil.which("podman"):
            backend = "podman"
        else:
            raise RuntimeError("no sandbox backend found; install bubblewrap or rootless Podman")

    if backend == "bwrap":
        if not shutil.which("bwrap"):
            raise RuntimeError("bwrap not found")
        full = build_bwrap(workspace, command, args.network)
        preexec = limits(args.memory_mb, args.cpu_seconds, args.pids)
    else:
        if not shutil.which("podman"):
            raise RuntimeError("podman not found")
        full = build_podman(workspace, command, args.network, args.image, args.memory_mb, args.pids)
        preexec = None

    started = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()
    proc = subprocess.run(full, text=True, capture_output=True, timeout=args.timeout, check=False, preexec_fn=preexec)
    elapsed = time.monotonic() - t0

    receipt = {
        "status": "MBM_SANDBOX_EXECUTION",
        "backend": backend,
        "workspace": str(workspace),
        "command": command,
        "network": args.network,
        "started_at": started,
        "elapsed_seconds": elapsed,
        "returncode": proc.returncode,
        "stdout_sha256": hashlib.sha256(proc.stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(proc.stderr.encode()).hexdigest(),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "limits": {"memory_mb": args.memory_mb, "cpu_seconds": args.cpu_seconds, "pids": args.pids},
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ["status", "backend", "returncode", "elapsed_seconds"]}, indent=2))
    raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
