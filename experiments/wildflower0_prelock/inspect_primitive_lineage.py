from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile


ROOT = Path(__file__).resolve().parents[2]
OUT = Path("artifacts/primitive_lineage_static_audit.json")
TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".py"}
MAX_TEXT_BYTES = 1_500_000
HIGH_SIGNAL = re.compile(
    r"\b(status|verdict|terminal|result|conclusion|winner|selected|recommend|next|pass|fail|"
    r"promot|retire|freeze|sufficient|insufficient|surviv|frontier|handoff|question)\b",
    re.IGNORECASE,
)
MAX_SIGNAL_LINES = 80
MAX_JSON_SCALARS = 120
JSON_KEYS = re.compile(
    r"(status|verdict|result|conclusion|winner|selected|recommend|pass|fail|promot|retire|"
    r"freeze|sufficient|surviv|frontier|next|benchmark|version|candidate|question)",
    re.IGNORECASE,
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(name: str) -> bool:
    p = PurePosixPath(name)
    return bool(p.parts) and not p.is_absolute() and ".." not in p.parts


def is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF)


def flatten_json(value, path="", out=None):
    if out is None:
        out = []
    if len(out) >= MAX_JSON_SCALARS:
        return out
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if isinstance(child, (dict, list)):
                flatten_json(child, child_path, out)
            elif JSON_KEYS.search(str(key)):
                out.append({"path": child_path, "value": child})
                if len(out) >= MAX_JSON_SCALARS:
                    break
    elif isinstance(value, list):
        for index, child in enumerate(value[:50]):
            flatten_json(child, f"{path}[{index}]", out)
            if len(out) >= MAX_JSON_SCALARS:
                break
    return out


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
            signal.append({"line": number, "text": line[:500]})
            if len(signal) >= MAX_SIGNAL_LINES:
                break
    item: dict[str, object] = {
        "path": name,
        "bytes": len(data),
        "sha256": sha256(data),
        "first_lines": text.splitlines()[:16],
        "signal_lines": signal,
    }
    if PurePosixPath(name).suffix.lower() == ".json":
        try:
            item["json_scalars"] = flatten_json(json.loads(text))
        except json.JSONDecodeError as exc:
            item["json_error"] = str(exc)
    return item


def inspect_archive(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    result: dict[str, object] = {
        "archive": path.name,
        "archive_sha256": sha256(raw),
        "archive_bytes": len(raw),
    }
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        names = [info.filename for info in infos]
        duplicate = sorted({name for name in names if names.count(name) > 1})
        unsafe = sorted(info.filename for info in infos if not safe_name(info.filename))
        symlinks = sorted(info.filename for info in infos if is_symlink(info))
        corrupt = zf.testzip()
        member_summary = []
        text = []
        nested = []
        result_files = []
        for info in infos:
            if info.is_dir():
                continue
            data = zf.read(info)
            member_summary.append(
                {
                    "path": info.filename,
                    "bytes": info.file_size,
                    "sha256": sha256(data),
                }
            )
            lower = info.filename.lower()
            if any(token in lower for token in ("result", "verdict", "conclusion", "handoff", "summary")):
                result_files.append(info.filename)
            if lower.endswith(".zip"):
                nested.append(
                    {
                        "path": info.filename,
                        "bytes": len(data),
                        "sha256": sha256(data),
                    }
                )
            evidence = inspect_text(info.filename, data)
            if evidence is not None and (
                evidence["signal_lines"]
                or any(token in lower for token in ("readme", "result", "verdict", "conclusion", "handoff", "spec"))
            ):
                text.append(evidence)
        result.update(
            {
                "zip_integrity_pass": corrupt is None,
                "first_corrupt_member": corrupt,
                "member_count": len(infos),
                "duplicate_members": duplicate,
                "unsafe_paths": unsafe,
                "symlinks": symlinks,
                "result_like_files": result_files,
                "nested_archives": nested,
                "members": member_summary,
                "text_evidence": text,
            }
        )
    return result


def sort_key(path: Path):
    name = path.stem
    parts = re.split(r"([0-9]+)", name)
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def main() -> int:
    archives = sorted(ROOT.glob("PRIMITIVE-*.zip"), key=sort_key)
    reports = [inspect_archive(path) for path in archives]
    safe = all(
        report["zip_integrity_pass"]
        and not report["duplicate_members"]
        and not report["unsafe_paths"]
        and not report["symlinks"]
        for report in reports
    )
    report = {
        "status": "PRIMITIVE_LINEAGE_STATIC_AUDIT",
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
        print("ARCHIVE", item["archive"], item["archive_sha256"], "results", len(item["result_like_files"]))
        for evidence in item["text_evidence"]:
            if any(token in evidence["path"].lower() for token in ("result", "verdict", "conclusion", "handoff", "readme")):
                print(" FILE", evidence["path"])
                for line in evidence["signal_lines"][:20]:
                    print("  ", line["line"], line["text"])
    print("receipt_sha256", report["receipt_sha256"])
    return 0 if safe else 2


if __name__ == "__main__":
    raise SystemExit(main())
