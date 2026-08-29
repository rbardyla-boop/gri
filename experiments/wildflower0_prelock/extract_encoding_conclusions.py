from __future__ import annotations

from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    "ENCODING-0_v0.1.0.zip": "results_encoding0/ENCODING-0_CONCLUSION.md",
    "ENCODING-1_v0.1.0.zip": "ENCODING-1/results/ENCODING-1_CONCLUSION.md",
    "ENCODING-1A_v0.1.0.zip": "ENCODING-1A/results/ENCODING-1A_CONCLUSION.md",
    "ENCODING-1B_v0.1.0.zip": "ENCODING-1B/results/ENCODING-1B_CONCLUSION.md",
    "ENCODING-2_v0.1.0.zip": "ENCODING-2/results/ENCODING-2_CONCLUSION.md",
}


def main() -> int:
    for archive_name, member in TARGETS.items():
        print("=" * 80)
        print(archive_name, "::", member)
        with zipfile.ZipFile(ROOT / archive_name) as archive:
            text = archive.read(member).decode("utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
