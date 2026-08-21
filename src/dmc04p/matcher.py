from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import torch
from torch import nn


ATOMS = ("A", "B")
ATOM_SIZE = 8
CAPACITY = 16
HIDDEN_DIM = 49
MESSAGE_DIM = 51
TRAIN_DEPTH = 4
EVIDENCE_SEEDS = (1337, 1338, 1339, 1340, 1341)
NON_EVIDENCE_SEED = 9090
TRAINING_EPOCHS = 80
TRAINING_BATCH_SIZE = 64
TRAINING_LR = 1e-2
TRAINING_WEIGHT_DECAY = 0.0
TRAINING_GRAD_CLIP = 1.0

CODEBOOKS = {
    "write_A": tuple(f"write_A_token_{index}" for index in range(ATOM_SIZE)),
    "query_A": tuple(f"query_A_token_{index}" for index in range(ATOM_SIZE)),
    "write_B": tuple(f"write_B_token_{index}" for index in range(ATOM_SIZE)),
    "query_B": tuple(f"query_B_token_{index}" for index in range(ATOM_SIZE)),
}

_WRITE_RE = re.compile(r"^write_([AB])_token_([0-7])$")
_QUERY_RE = re.compile(r"^query_([AB])_token_([0-7])$")
_FORBIDDEN_SCORER_KEYS = {
    "logical_key",
    "answer",
    "value",
    "hidden_value",
    "record_id",
    "case_id",
    "target_record_id",
    "oracle_view",
    "oracle_decision",
    "correct_candidate_index",
}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _token_index(token: str, *, side: str, atom: str) -> int:
    vocabulary = CODEBOOKS[f"{side}_{atom}"]
    if token not in vocabulary:
        raise ValueError(f"token is not in frozen {side}_{atom} vocabulary")
    return vocabulary.index(token)


def _one_hot(index: int) -> torch.Tensor:
    result = torch.zeros(ATOM_SIZE, dtype=torch.float32)
    result[index] = 1.0
    return result


@dataclass(frozen=True)
class EncodedAddress:
    A: torch.Tensor
    B: torch.Tensor


def encode_write_descriptor(descriptor: dict[str, Any]) -> EncodedAddress:
    if set(descriptor) != {"tokens", "attribute_order"}:
        raise ValueError("write descriptor fields are not frozen DMC-04A fields")
    if descriptor["attribute_order"] != ["A", "B"]:
        raise ValueError("write descriptor order is not A,B")
    tokens = descriptor["tokens"]
    if not isinstance(tokens, list) or len(tokens) != 2:
        raise ValueError("write descriptor must contain exactly two tokens")
    matches = [_WRITE_RE.match(token) for token in tokens]
    if any(match is None for match in matches) or {match.group(1) for match in matches} != {"A", "B"}:
        raise ValueError("write descriptor must contain one A and one B token")
    values = {match.group(1): int(match.group(2)) for match in matches}
    for atom, value in values.items():
        expected = f"write_{atom}_token_{value}"
        if expected not in CODEBOOKS[f"write_{atom}"]:
            raise ValueError("write codebook-local token ordering mismatch")
    return EncodedAddress(A=_one_hot(_token_index(f"write_A_token_{values['A']}", side="write", atom="A")), B=_one_hot(_token_index(f"write_B_token_{values['B']}", side="write", atom="B")))


def encode_query_descriptor(descriptor: dict[str, Any]) -> EncodedAddress:
    if set(descriptor) != {"tokens", "attribute_order", "noise_token_count"}:
        raise ValueError("query descriptor fields are not frozen DMC-04A fields")
    if descriptor["attribute_order"] != ["B", "A"]:
        raise ValueError("query descriptor order is not B,A")
    tokens = descriptor["tokens"]
    noise_count = descriptor["noise_token_count"]
    if not isinstance(tokens, list) or not isinstance(noise_count, int) or noise_count < 0 or len(tokens) != 2 + noise_count:
        raise ValueError("query descriptor token/noise cardinality mismatch")
    matches = [_QUERY_RE.match(token) for token in tokens[:2]]
    if any(match is None for match in matches) or {match.group(1) for match in matches} != {"A", "B"}:
        raise ValueError("query descriptor must contain one A and one B token")
    if any(not isinstance(token, str) or not token.startswith("noise_token_") for token in tokens[2:]):
        raise ValueError("query descriptor has malformed noise token")
    values = {match.group(1): int(match.group(2)) for match in matches}
    for atom, value in values.items():
        expected = f"query_{atom}_token_{value}"
        if expected not in CODEBOOKS[f"query_{atom}"]:
            raise ValueError("query codebook-local token ordering mismatch")
    return EncodedAddress(A=_one_hot(_token_index(f"query_A_token_{values['A']}", side="query", atom="A")), B=_one_hot(_token_index(f"query_B_token_{values['B']}", side="query", atom="B")))


class FactorizedAssociativeMatcher(nn.Module):
    """Exactly two independent 8x8 atomic correspondence matrices."""

    def __init__(self, *, seed: int | None = None) -> None:
        super().__init__()
        if seed is not None:
            torch.manual_seed(seed)
        self.W_A = nn.Parameter(torch.empty(ATOM_SIZE, ATOM_SIZE))
        self.W_B = nn.Parameter(torch.empty(ATOM_SIZE, ATOM_SIZE))
        nn.init.normal_(self.W_A, mean=0.0, std=0.02)
        nn.init.normal_(self.W_B, mean=0.0, std=0.02)

    def score_encoded(self, query: EncodedAddress, candidates: list[EncodedAddress]) -> torch.Tensor:
        if not candidates:
            raise ValueError("retrieval requires at least one candidate")
        candidate_A = torch.stack([candidate.A for candidate in candidates])
        candidate_B = torch.stack([candidate.B for candidate in candidates])
        score_A = torch.einsum("i,ij,nj->n", query.A, self.W_A, candidate_A)
        score_B = torch.einsum("i,ij,nj->n", query.B, self.W_B, candidate_B)
        return score_A + score_B

    def forward(self, query_descriptor: dict[str, Any], candidate_descriptors: list[dict[str, Any]]) -> torch.Tensor:
        return self.score_encoded(encode_query_descriptor(query_descriptor), [encode_write_descriptor(descriptor) for descriptor in candidate_descriptors])


def trainable_parameter_count(module: nn.Module) -> int:
    return sum(parameter.numel() for parameter in module.parameters() if parameter.requires_grad)


def build_optimizer(model: FactorizedAssociativeMatcher) -> torch.optim.Optimizer:
    if tuple(name for name, parameter in model.named_parameters() if parameter.requires_grad) != ("W_A", "W_B"):
        raise ValueError("retrieval optimizer is not isolated to W_A and W_B")
    if trainable_parameter_count(model) != 128:
        raise ValueError("factorized matcher does not have exactly 128 trainable parameters")
    return torch.optim.AdamW(model.parameters(), lr=TRAINING_LR, weight_decay=TRAINING_WEIGHT_DECAY)


def state_hash(model: nn.Module) -> str:
    payload = []
    for name, tensor in sorted(model.state_dict().items()):
        payload.append({"name": name, "dtype": str(tensor.dtype), "shape": list(tensor.shape), "bytes": tensor.detach().cpu().contiguous().numpy().tobytes().hex()})
    return _digest(canonical(payload))


def scorer_view(case: dict[str, Any]) -> dict[str, Any]:
    """Project a DMC-04A case onto the only fields the matcher may inspect."""

    neural = case["neural_view"]
    return {
        "query": {
            "query_descriptor": copy.deepcopy(neural["query"]["query_descriptor"]),
            "mode": neural["query"]["mode"],
            "as_of_episode": neural["query"]["as_of_episode"],
        },
        "candidates": [
            {
                "write_descriptor": copy.deepcopy(memory["write_descriptor"]),
                "creation_episode": memory["creation_episode"],
            }
            for memory in neural["memory"]
        ],
    }


def _scan_forbidden(value: Any, found: set[str] | None = None) -> set[str]:
    found = set() if found is None else found
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _FORBIDDEN_SCORER_KEYS:
                found.add(key)
            _scan_forbidden(child, found)
    elif isinstance(value, list):
        for child in value:
            _scan_forbidden(child, found)
    return found


def validate_scorer_view(view: dict[str, Any]) -> dict[str, Any]:
    required = {"query", "candidates"}
    if set(view) != required or set(view["query"]) != {"query_descriptor", "mode", "as_of_episode"}:
        raise ValueError("malformed retrieval scorer view")
    if len(view["candidates"]) > CAPACITY or not view["candidates"]:
        raise ValueError("retrieval scorer candidate capacity violation")
    for candidate in view["candidates"]:
        if set(candidate) != {"write_descriptor", "creation_episode"}:
            raise ValueError("candidate scorer view contains unauthorized fields")
    forbidden = _scan_forbidden(view)
    if forbidden:
        raise ValueError(f"retrieval scorer firewall violation: {sorted(forbidden)}")
    encode_query_descriptor(view["query"]["query_descriptor"])
    for candidate in view["candidates"]:
        encode_write_descriptor(candidate["write_descriptor"])
    return {"pass": True, "candidate_count": len(view["candidates"]), "forbidden_fields": sorted(forbidden)}


def candidate_scores(model: FactorizedAssociativeMatcher, case: dict[str, Any]) -> torch.Tensor:
    view = scorer_view(case)
    validate_scorer_view(view)
    return model(view["query"]["query_descriptor"], [candidate["write_descriptor"] for candidate in view["candidates"]])


def _descriptor_key(descriptor: dict[str, Any]) -> str:
    return canonical(descriptor)


def descriptor_groups(view: dict[str, Any]) -> list[list[int]]:
    groups: dict[str, list[int]] = defaultdict(list)
    for index, candidate in enumerate(view["candidates"]):
        groups[_descriptor_key(candidate["write_descriptor"])].append(index)
    return list(groups.values())


def group_scores(scores: torch.Tensor, view: dict[str, Any]) -> list[tuple[list[int], float]]:
    groups = descriptor_groups(view)
    if scores.ndim != 1 or scores.shape[0] != len(view["candidates"]):
        raise ValueError("candidate score shape mismatch")
    return [(indices, float(scores[indices[0]].detach().cpu().item())) for indices in groups]


def target_group(case: dict[str, Any]) -> dict[str, Any]:
    """Build supervision outside the scorer input; no answer is consulted."""

    view = scorer_view(case)
    target_record_id = case["oracle_view"]["target_record_id"]
    oracle_records = case["oracle_view"]["records"]
    target_index = next(index for index, record in enumerate(oracle_records) if record["record_id"] == target_record_id)
    target_descriptor = view["candidates"][target_index]["write_descriptor"]
    groups = descriptor_groups(view)
    target_group_index = next(index for index, indices in enumerate(groups) if target_index in indices)
    return {
        "target_candidate_index": target_index,
        "target_group_index": target_group_index,
        "target_group_descriptor": copy.deepcopy(target_descriptor),
        "loss_unit": "descriptor_group",
        "target_is_not_scorer_input": True,
    }


def resolver(case: dict[str, Any], scores: torch.Tensor) -> dict[str, Any]:
    """Resolve address group first, then current/history version zero-parametrically."""

    view = scorer_view(case)
    validate_scorer_view(view)
    groups = group_scores(scores, view)
    oracle_records = case["oracle_view"]["records"]
    group_order = sorted(
        range(len(groups)),
        key=lambda index: (-groups[index][1], min(_digest(str(oracle_records[item]["record_id"])) for item in groups[index][0])),
    )
    selected_group = groups[group_order[0]][0]
    mode = view["query"]["mode"]
    as_of = view["query"]["as_of_episode"]
    if mode == "history":
        eligible = [index for index in selected_group if view["candidates"][index]["creation_episode"] <= as_of]
    elif mode == "current":
        eligible = list(selected_group)
    else:
        raise ValueError("unknown version mode")
    if not eligible:
        raise ValueError("selected descriptor group has no temporally eligible record")
    selected_index = sorted(eligible, key=lambda index: (-view["candidates"][index]["creation_episode"], _digest(str(oracle_records[index]["record_id"]))))[0]
    return {
        "selected_candidate_index": selected_index,
        "selected_record_id": oracle_records[selected_index]["record_id"],
        "selected_group_indices": selected_group,
        "version_resolver": "latest eligible creation_episode; SHA256(record_id) tie break",
    }


def load_training_cases(root: Path) -> list[dict[str, Any]]:
    path = root / "artifacts/dmc04a/datasets/train.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def order_case_ids(case_ids: Iterable[str], *, seed: int, epoch: int) -> list[str]:
    return sorted(case_ids, key=lambda case_id: _digest(f"DMC04_ORDER|{seed}|{epoch}|{case_id}"))


def training_order(case_ids: list[str], *, seed: int, epoch: int, batch_size: int = TRAINING_BATCH_SIZE) -> dict[str, Any]:
    ordered = order_case_ids(case_ids, seed=seed, epoch=epoch)
    batches = [ordered[index:index + batch_size] for index in range(0, len(ordered), batch_size)]
    return {
        "seed": seed,
        "epoch": epoch,
        "batch_size": batch_size,
        "case_count": len(case_ids),
        "order_sha256": _digest(canonical(ordered)),
        "batch_sha256": _digest(canonical(batches)),
        "batches": batches,
    }


def build_shuffle_query_mapping(cases: list[dict[str, Any]]) -> dict[str, str]:
    groups: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for case in cases:
        groups[(case["split"], case["family"], case["condition"])].append(case["case_id"])
    mapping: dict[str, str] = {}
    for group, case_ids in sorted(groups.items()):
        ordered = sorted(case_ids)
        for index, case_id in enumerate(ordered):
            mapping[case_id] = ordered[(index + 1) % len(ordered)]
    return mapping
