from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile


ROOT = Path(__file__).resolve().parents[2]
ARCHIVES = (
    "PRIMITIVE-0_REFERENCE_IMPLEMENTATION_v0.1.0.zip",
    "PRIMITIVE-0_C1_STABLE_REFERENCE_REPAIR_v0.1.0.zip",
)
TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".json",
    ".py",
    ".toml",
    ".yaml",
    ".yml",
    ".csv",
}
KEYWORDS = (
    "NO RESULTS",
    "PASS",
    "FAIL",
    "fixture",
    "candidate",
    "T1",
    "RELAY",
    "run_",
    "pytest",
    "reference",
    "verdict",
    "repair",
    "result",
    "side channel",
    "natural language",
)
MAX_TEXT_BYTES = 512_000
MAX_MATCHES_PER_FILE = 40


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        return False
    return bool(path.parts)


def is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def inspect_archive(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    result: dict[str, object] = {
        "archive": path.name,
        "archive_sha256": sha256_bytes(raw),
        "archive_bytes": len(raw),
    }
    with zipfile.ZipFile(path) as archive:
        corrupt = archive.testzip()
        infos = archive.infolist()
        names = [info.filename for info in infos]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        unsafe = sorted(info.filename for info in infos if not safe_member(info.filename))
        symlinks = sorted(info.filename for info in infos if is_symlink(info))
        files = []
        text_evidence = []
        for info in infos:
            if info.is_dir():
                continue
            data = archive.read(info)
            member = {
                "path": info.filename,
                "bytes": info.file_size,
                "compressed_bytes": info.compress_size,
                "crc32": f"{info.CRC:08x}",
                "sha256": sha256_bytes(data),
            }
            files.append(member)
            suffix = PurePosixPath(info.filename).suffix.lower()
            if suffix not in TEXT_SUFFIXES or info.file_size > MAX_TEXT_BYTES:
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            matches = []
            for line_number, line in enumerate(text.splitlines(), 1):
                if any(keyword.lower() in line.lower() for keyword in KEYWORDS):
                    matches.append({"line": line_number, "text": line[:300]})
                    if len(matches) >= MAX_MATCHES_PER_FILE:
                        break
            text_evidence.append(
                {
                    "path": info.filename,
                    "line_count": len(text.splitlines()),
                    "first_lines": text.splitlines()[:20],
                    "keyword_matches": matches,
                }
            )
        result.update(
            {
                "zip_integrity_pass": corrupt is None,
                "first_corrupt_member": corrupt,
                "member_count": len(infos),
                "file_count": len(files),
                "duplicate_members": duplicates,
                "unsafe_paths": unsafe,
                "symlinks": symlinks,
                "files": files,
                "text_evidence": text_evidence,
            }
        )
    return result


def main() -> int:
    reports = []
    for name in ARCHIVES:
        path = ROOT / name
        if not path.exists():
            raise SystemExit(f"missing archive: {name}")
        reports.append(inspect_archive(path))

    overall_pass = all(
        report["zip_integrity_pass"]
        and not report["duplicate_members"]
        and not report["unsafe_paths"]
        and not report["symlinks"]
        for report in reports
    )
    report = {
        "status": "PRIMITIVE0_ARCHIVE_STATIC_AUDIT",
        "scientific_execution_performed": False,
        "primitive0_authorized": False,
        "overall_archive_safety_pass": overall_pass,
        "archives": reports,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    report["receipt_sha256"] = sha256_bytes(canonical)

    out = Path("artifacts/primitive0_archive_audit.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    for archive_report in reports:
        print(
            archive_report["archive"],
            "files=",
            archive_report["file_count"],
            "zip_ok=",
            archive_report["zip_integrity_pass"],
            "sha256=",
            archive_report["archive_sha256"],
        )
        print("members:")
        for member in archive_report["files"]:
            print(" ", member["path"], member["bytes"], member["sha256"])
        print("text evidence:")
        for evidence in archive_report["text_evidence"]:
            print(" FILE", evidence["path"])
            for line in evidence["first_lines"]:
                print("  HEAD", line[:300])
            for match in evidence["keyword_matches"]:
                print("  MATCH", match["line"], match["text"])
    print("archive_safety_pass", overall_pass)
    print("receipt_sha256", report["receipt_sha256"])
    return 0 if overall_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
