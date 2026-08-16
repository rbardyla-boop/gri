from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from .schema import Fact, Sample


def _sorted_facts(facts: Iterable[Fact]) -> list[dict[str, object]]:
    return [f.to_dict() for f in sorted(facts, key=lambda x: (x.subject, x.relation.value, x.object))]


def semantic_identity_payload(
    *, benchmark_version: str, task_family: str, chain_length: int,
    facts: Iterable[Fact], query: dict[str, int], answer: str | None,
    contradiction_label: bool,
) -> dict[str, object]:
    return {
        "benchmark_version": benchmark_version,
        "task_family": task_family,
        "chain_length": chain_length,
        "facts": _sorted_facts(facts),
        "query": query,
        "answer": answer,
        "contradiction_label": contradiction_label,
    }


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sample_semantic_id(sample: Sample) -> str:
    payload = semantic_identity_payload(
        benchmark_version=sample.benchmark_version,
        task_family=sample.task_family.value,
        chain_length=sample.chain_length,
        facts=sample.facts,
        query=sample.query.to_dict(),
        answer=sample.answer.value if sample.answer else None,
        contradiction_label=sample.contradiction_label,
    )
    return stable_sha256(payload)


def canonical_sample_line(sample: Sample) -> str:
    return canonical_json(sample.to_dict())


def write_jsonl(path: Path, samples: Iterable[Sample]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for sample in samples:
            handle.write(canonical_sample_line(sample) + "\n")


def read_jsonl(path: Path) -> list[Sample]:
    samples: list[Sample] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                samples.append(Sample.from_dict(raw))
            except Exception as exc:
                raise ValueError(f"{path}:{line_no}: invalid sample: {exc}") from exc
    return samples


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()
