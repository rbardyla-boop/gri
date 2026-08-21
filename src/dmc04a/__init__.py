"""DMC-04A deterministic associative-retrieval benchmark."""

from .benchmark import (
    CAPACITY,
    CASES_PER_CONDITION,
    FAMILIES,
    VALUES,
    build_dataset,
    build_split,
    canonical,
    content_hash,
    exact_token_retrieval,
    final_answer_from_record,
    oracle_retrieval,
    query_only_answer,
    random_retrieval,
    single_attribute_retrieval,
    validate_case,
)

__all__ = [
    "CAPACITY",
    "CASES_PER_CONDITION",
    "FAMILIES",
    "VALUES",
    "build_dataset",
    "build_split",
    "canonical",
    "content_hash",
    "exact_token_retrieval",
    "final_answer_from_record",
    "oracle_retrieval",
    "query_only_answer",
    "random_retrieval",
    "single_attribute_retrieval",
    "validate_case",
]
