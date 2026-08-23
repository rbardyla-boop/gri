from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

DEFINITION_URL = (
    "https://iair.mchtr.pw.edu.pl/content/download/173/857/file/"
    "damadics-benchmark-definition.zip"
)
DESCRIPTION_URL = (
    "https://iair.mchtr.pw.edu.pl/content/download/161/809/file/"
    "damadics-lublin-data-description.zip"
)
EXPECTED_ARCHIVE_SHA256 = {
    "benchmark_definition": "216bdd72e1b6ee1ebf77d8ed2609f67a8ce5cdc806cf9f288e067ccfb6be6e04",
    "data_file_description": "ee6f4083fae635c34bd6e33b068553a401e9e182e50f0914c5956f3073b7625a",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "gri-erc2a-metadata-extractor/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read()
    if not body:
        raise ValueError(f"empty response from {url}")
    return body


def extract_single_pdf(name: str, url: str, expected_archive_sha256: str, output_dir: Path) -> dict:
    archive_body = fetch(url)
    archive_sha = sha256_bytes(archive_body)
    if archive_sha != expected_archive_sha256:
        raise ValueError(
            f"{name} archive SHA mismatch: {archive_sha} != {expected_archive_sha256}"
        )
    with zipfile.ZipFile(BytesIO(archive_body)) as archive:
        files = [info for info in archive.infolist() if not info.is_dir()]
        if len(files) != 1 or not files[0].filename.lower().endswith(".pdf"):
            raise ValueError(f"{name} expected exactly one PDF")
        pdf_name = files[0].filename
        pdf_body = archive.read(files[0])

    reader = PdfReader(BytesIO(pdf_body))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(f"\n===== PAGE {index} =====\n{text}\n")
    text_body = "".join(pages)
    if not text_body.strip():
        raise ValueError(f"{name} extracted no PDF text")

    text_path = output_dir / f"{name}.txt"
    text_path.write_text(text_body, encoding="utf-8")
    return {
        "name": name,
        "url": url,
        "archive_sha256": archive_sha,
        "pdf_name": pdf_name,
        "pdf_sha256": sha256_bytes(pdf_body),
        "page_count": len(reader.pages),
        "text_sha256": sha256_bytes(text_body.encode("utf-8")),
        "text_path": text_path.name,
        "text_bytes": len(text_body.encode("utf-8")),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    documents = [
        extract_single_pdf(
            "benchmark_definition",
            DEFINITION_URL,
            EXPECTED_ARCHIVE_SHA256["benchmark_definition"],
            args.output_dir,
        ),
        extract_single_pdf(
            "data_file_description",
            DESCRIPTION_URL,
            EXPECTED_ARCHIVE_SHA256["data_file_description"],
            args.output_dir,
        ),
    ]
    result = {
        "unit": "ERC-2A",
        "status": "ERC2A_OFFICIAL_METADATA_TEXT_EXTRACTED",
        "telemetry_downloaded": False,
        "scientific_predictions": 0,
        "scorer_opened": False,
        "documents": documents,
    }
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"))
    result["record_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    report = args.output_dir / "ERC2A_METADATA_EXTRACTION.json"
    report.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
