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


def limits(memory_mb: int, cpu_seconds: int, pids: int = 0):
    """Apply process-local limits.

    RLIMIT_NPROC is intentionally optional. On Linux it is charged against the
    calling process's real host UID (and counts threads), not against a bwrap
    PID namespace. Applying a small value before launching bwrap can therefore
    prevent bwrap itself from creating namespaces on a normal desktop session.
    """
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


def probe_bwrap(workspace: Path) -> tuple[bool, str]:
    if not shutil.which("bwrap"):
        return False, "bwrap_not_found"
    probe = build_bwrap(workspace, ["/usr/bin/true"], network=False)
    try:
        proc = subprocess.run(probe, text=True, capture_output=True, timeout=5.0, check=False)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if proc.returncode == 0:
        return True, "ok"
    detail = (proc.stderr or proc.stdout or f"returncode={proc.returncode}").strip()
    return False, detail[:2000]


def build_podman(workspace: Path, command: list[str], network: bool, image: str, memory_mb: int, pids: int) -> list[str]:
    cmd = [
        "podman", "run", "--rm",
        "--read-only",
        "--userns=keep-id",
        "--security-opt=no-new-privileges",
        "--cap-drop=ALL",
        "--pids-limit", str(pids),
        "--memory", f"{memory_mb}m",
        "-v", f"{workspace}:{workspace}:rw,Z",
        "-w", str(workspace),
    ]
    broker = os.environ.get("TE0_MODEL_BROKER")
    if broker:
        cmd += ["-e", f"TE0_MODEL_BROKER={broker}"]
    cmd += ["--network", "slirp4netns"] if network else ["--network", "none"]
    return cmd + [image] + command


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", type=Path, default=Path.cwd())
    ap.add_argument("--backend", choices=["auto", "bwrap", "podman"], default="auto")
    ap.add_argument("--image", default="python:3.12-slim")
    ap.add_argument("--network", action="store_true")
    ap.add_argument("--memory-mb", type=int, default=4096)
    ap.add_argument("--cpu-seconds", type=int, default=900)
    ap.add_argument("--pids", type=int, default=128)
    ap.add_argument("--timeout", type=float, default=1800.0)
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

    requested_backend = args.backend
    backend = requested_backend
    selection = {"requested": requested_backend, "bwrap_probe": None, "fallback": False}

    if backend == "auto":
        bwrap_ok, bwrap_detail = probe_bwrap(workspace)
        selection["bwrap_probe"] = {"ok": bwrap_ok, "detail": bwrap_detail}
        if bwrap_ok:
            backend = "bwrap"
        elif shutil.which("podman"):
            backend = "podman"
            selection["fallback"] = True
        else:
            raise RuntimeError(
                "no usable sandbox backend: bwrap preflight failed and podman is unavailable; "
                f"bwrap detail: {bwrap_detail}"
            )

    if backend == "bwrap":
        if not shutil.which("bwrap"):
            raise RuntimeError("bwrap not found")
        if requested_backend == "bwrap":
            bwrap_ok, bwrap_detail = probe_bwrap(workspace)
            selection["bwrap_probe"] = {"ok": bwrap_ok, "detail": bwrap_detail}
            if not bwrap_ok:
                raise RuntimeError(f"bwrap preflight failed: {bwrap_detail}")
        full = build_bwrap(workspace, command, args.network)
        # Do not apply RLIMIT_NPROC here. Linux charges it against the real
        # host UID, so a desktop session with >= args.pids threads can make
        # bwrap's clone()/namespace creation fail with EAGAIN before the
        # sandbox exists. PID-count containment for bwrap should use cgroups.
        preexec = limits(args.memory_mb, args.cpu_seconds, pids=0)
        pids_enforced = False
        pids_mechanism = "not_enforced_for_bwrap; use cgroup/TasksMax in a later hardening pass"
    else:
        if not shutil.which("podman"):
            raise RuntimeError("podman not found")
        full = build_podman(workspace, command, args.network, args.image, args.memory_mb, args.pids)
        preexec = None
        pids_enforced = True
        pids_mechanism = "podman --pids-limit"

    started = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()
    proc = subprocess.run(full, text=True, capture_output=True, timeout=args.timeout, check=False, preexec_fn=preexec)
    elapsed = time.monotonic() - t0

    receipt = {
        "status": "MBM_SANDBOX_EXECUTION",
        "backend": backend,
        "backend_selection": selection,
        "workspace": str(workspace),
        "command": command,
        "network": args.network,
        "model_broker_socket": os.environ.get("TE0_MODEL_BROKER"),
        "started_at": started,
        "elapsed_seconds": elapsed,
        "returncode": proc.returncode,
        "stdout_sha256": hashlib.sha256(proc.stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(proc.stderr.encode()).hexdigest(),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "limits": {
            "memory_mb": args.memory_mb,
            "cpu_seconds": args.cpu_seconds,
            "pids_requested": args.pids,
            "pids_enforced": pids_enforced,
            "pids_mechanism": pids_mechanism,
        },
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ["status", "backend", "backend_selection", "returncode", "elapsed_seconds", "network", "limits"]}, indent=2))
    raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
