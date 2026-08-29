from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile


ROOT = Path(__file__).resolve().parents[2]
OUT = Path("artifacts/encoding_lineage_static_audit.json")
TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".py", ".csv"}
MAX_TEXT_BYTES = 1_500_000
HIGH_SIGNAL = re.compile(
    r"\b(status|verdict|terminal|result|conclusion|winner|selected|recommend|next|pass|fail|"
    r"promot|retire|freeze|sufficient|insufficient|surviv|frontier|handoff|question|byte|bit|"
    r"wire|storage|compression|encode|decode|entropy|dictionary|token|symbol|latent|packet|cost)\b",
    re.IGNORECASE,
)
MAX_SIGNAL_LINES = 100


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(path.parts) and not path.is_absolute() and ".." not in path.parts


def is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF)


def inspect_text(name: str, data: bytes) -> dict[str, object] | None:
    if PurePosixPath(name).suffix.lower() not in TEXT_SUFFIXES or len(data) > MAX_TEXT_BYTES:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    signal = []
    for number, line in enumerate(text.splitlines(), 1):
        if HIGH_SIGNAL.search(line):
            signal.append({"line": number, "text": line[:600]})
            if len(signal) >= MAX_SIGNAL_LINES:
                break
    lower = name.lower()
    if not signal and not any(
        token in lower for token in ("readme", "result", "verdict", "conclusion", "handoff", "spec", "report")
    ):
        return None
    return {
        "path": name,
        "bytes": len(data),
        "sha256": sha256(data),
        "first_lines": text.splitlines()[:20],
        "signal_lines": signal,
    }


def inspect_archive(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        duplicate = sorted({name for name in names if names.count(name) > 1})
        unsafe = sorted(info.filename for info in infos if not safe_name(info.filename))
        symlinks = sorted(info.filename for info in infos if is_symlink(info))
        corrupt = archive.testzip()
        result_like = []
        evidence = []
        members = []
        for info in infos:
            if info.is_dir():
                continue
            data = archive.read(info)
            members.append({"path": info.filename, "bytes": len(data), "sha256": sha256(data)})
            lower = info.filename.lower()
            if any(token in lower for token in ("result", "verdict", "conclusion", "report", "handoff")):
                result_like.append(info.filename)
            text = inspect_text(info.filename, data)
            if text is not None:
                evidence.append(text)
        return {
            "archive": path.name,
            "archive_sha256": sha256(raw),
            "archive_bytes": len(raw),
            "zip_integrity_pass": corrupt is None,
            "first_corrupt_member": corrupt,
            "member_count": len(infos),
            "duplicate_members": duplicate,
            "unsafe_paths": unsafe,
            "symlinks": symlinks,
            "result_like_files": result_like,
            "members": members,
            "text_evidence": evidence,
        }


def natural_key(path: Path):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"([0-9]+)", path.stem)]


def main() -> int:
    archives = sorted(ROOT.glob("ENCODING-*.zip"), key=natural_key)
    reports = [inspect_archive(path) for path in archives]
    safe = all(
        item["zip_integrity_pass"]
        and not item["duplicate_members"]
        and not item["unsafe_paths"]
        and not item["symlinks"]
        for item in reports
    )
    report = {
        "status": "ENCODING_LINEAGE_STATIC_AUDIT",
        "scientific_execution_performed": False,
        "archive_count": len(reports),
        "archive_safety_pass": safe,
        "archives": reports,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    report["receipt_sha256"] = sha256(canonical)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print("archive_count", len(reports))
    print("archive_safety_pass", safe)
    for item in reports:
        print("ARCHIVE", item["archive"], item["archive_sha256"], "result_like", len(item["result_like_files"]))
        for evidence in item["text_evidence"]:
            lower = evidence["path"].lower()
            if any(token in lower for token in ("result", "verdict", "conclusion", "readme", "handoff", "report")):
                print(" FILE", evidence["path"])
                for line in evidence["signal_lines"][:30]:
                    print("  ", line["line"], line["text"])
    print("receipt_sha256", report["receipt_sha256"])
    return 0 if safe else 2


if __name__ == "__main__":
    raise SystemExit(main())
