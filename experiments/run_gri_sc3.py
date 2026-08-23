#!/usr/bin/env python3
"""GRI-SC-3E single-run scientific executor.

The entrypoint is deliberately fail-closed.  It verifies the SC-3E, SC-3,
SC-2, GRI-02B, and development anchors before consuming the one execution
token.  It emits one of the three SC-3 mechanical verdicts on stdout only
after the token has been consumed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import platform
import random
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
import torch
from scipy.optimize import linprog
from torch import nn


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
ARTIFACTS = ROOT / "artifacts" / "results"
AUTH = EXPERIMENTS / "candidates" / "GRI-SC-3E-one-run-execution-authorization.json"
AUTH_RECEIPT = ARTIFACTS / "gri_sc3e_one_run_authorization_receipt.json"
SC3_CONTRACT = EXPERIMENTS / "candidates" / "GRI-SC-3-scientific-run-authorization.json"
SC3_RECORD = ROOT / "docs" / "GRI-SC-3-SCIENTIFIC-RUN-AUTHORIZATION.md"
SC3_VERIFICATION = ARTIFACTS / "gri_sc3_authorization_contract_receipt.json"
SC2_FREEZE = EXPERIMENTS / "candidates" / "GRI-SC-2-candidate-freeze.json"
SOURCE = EXPERIMENTS / "candidates" / "GRI-SC-1" / "branchfree_residual.py"
CANDIDATE_MANIFEST = EXPERIMENTS / "candidates" / "GRI-SC-1" / "branchfree_residual_manifest.json"
FIXTURES = EXPERIMENTS / "gri02b_fixture_bank.json"
RULES = EXPERIMENTS / "gri02b_operation_rules.json"
GRI02B_CONFIG = EXPERIMENTS / "gri02b_config.json"
GRI02B_HARNESS = EXPERIMENTS / "gri02b_preregistration.py"
GRI02B_RECEIPT = ARTIFACTS / "gri02b_preregistration_receipt.json"
GRI02B_CONTRACT = ROOT / "docs" / "GRI-02-AUTHORIZATION-CONTRACT.md"
SC1R1_RECEIPT = ARTIFACTS / "gri_sc1r1_selector_accounting_receipt.json"
SC1L_AUTH = ROOT / "docs" / "GRI-SC-1L-LEARNABILITY-AUTHORIZATION.md"
SC1L_RESULT = ARTIFACTS / "gri_sc1l_learnability_grid_receipt.json"
SIM = ROOT / "sim" / "gri_sim0.py"
SIM_EXPERIMENT = ROOT / "sim" / "experiment_manifest.json"

RESULT = ARTIFACTS / "gri_sc3_scientific_run_receipt.json"
REPLAY = ARTIFACTS / "gri_sc3_replay_receipt.json"
ENVIRONMENT = ARTIFACTS / "gri_sc3_environment_receipt.json"
PREFLIGHT = ARTIFACTS / "gri_sc3e_preflight_receipt.json"
CHECKPOINT_DIR = ARTIFACTS / "gri_sc3_checkpoints"

EXPECTED_AUTH_SHA = "82a20e72a663dd7301a636e3d034533b3050c39fe28dccd29c118cc0100bb8cb"
EXPECTED_AUTH_RECEIPT_SHA = "e96dbe25d269aab7e6f006ac6b5ed5e345abc1f799be0598f86f27ee94a5bf2f"
EXPECTED_SC3_SHA = "590d6606ff23cdfb02e9285f71772c9fab52d5b46fdd693a842ad83b5a242987"
EXPECTED_SC3_RECORD_SHA = "5606d312b5148debb9e1cac223bd00bbd1bd530c2ed08901b0d037dac36bdeb2"
EXPECTED_SC3_VERIFICATION_SHA = "d5cff851674232b3829ee0f7083655c07d11d7c749779c811c5398bf30fb74f4"
EXPECTED_SC2_SHA = "03ec6bc36c8b5d4d764bdbef3bccf875294c1b9b8512d23614643beef0638e9d"

DTYPES = {
    "float64": torch.float64,
    "float32": torch.float32,
    "float16": torch.float16,
    "bfloat16": torch.bfloat16,
}
REQUIRED_MODES = ("float64", "float32", "q8")
ALL_MODES = REQUIRED_MODES + ("float16", "bfloat16")


class PreflightFailure(RuntimeError):
    pass


def canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical(value)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("gri_sc3_candidate", path)
    if spec is None or spec.loader is None:
        raise PreflightFailure(f"cannot import candidate source: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()
    except Exception:
        return None


def run_sim_preflight() -> dict:
    result = subprocess.run(
        [
            sys.executable,
            str(SIM),
            "validate-candidate",
            "--experiment",
            str(SIM_EXPERIMENT),
            "--candidate",
            str(CANDIDATE_MANIFEST),
            "--source",
            str(SOURCE),
        ],
        cwd=SIM.parent,
        text=True,
        capture_output=True,
        check=False,
    )
    if not result.stdout.strip():
        raise PreflightFailure(f"simulator preflight emitted no JSON: {result.stderr}")
    payload = json.loads(result.stdout)
    if result.returncode != 0 or payload.get("status") != "PASS":
        raise PreflightFailure(f"simulator preflight failed: {payload}")
    return {"returncode": result.returncode, "result": payload}


def verify_hash(path: Path, expected: str, label: str) -> None:
    if not path.exists():
        raise PreflightFailure(f"missing {label}: {path}")
    actual = sha256(path)
    if actual != expected:
        raise PreflightFailure(f"{label} hash mismatch: {actual} != {expected}")


def preflight() -> dict:
    verify_hash(AUTH, EXPECTED_AUTH_SHA, "SC-3E authorization")
    verify_hash(AUTH_RECEIPT, EXPECTED_AUTH_RECEIPT_SHA, "SC-3E authorization receipt")
    verify_hash(SC3_CONTRACT, EXPECTED_SC3_SHA, "SC-3 contract")
    verify_hash(SC3_RECORD, EXPECTED_SC3_RECORD_SHA, "SC-3 record")
    verify_hash(SC3_VERIFICATION, EXPECTED_SC3_VERIFICATION_SHA, "SC-3 verification")
    verify_hash(SC2_FREEZE, EXPECTED_SC2_SHA, "SC-2 freeze")

    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    auth_receipt = json.loads(AUTH_RECEIPT.read_text(encoding="utf-8"))
    sc3 = json.loads(SC3_CONTRACT.read_text(encoding="utf-8"))
    sc2 = json.loads(SC2_FREEZE.read_text(encoding="utf-8"))
    if auth["executions_authorized"] != 1 or auth["development_runs"] != 0 or auth["retries"] != 0 or auth["post_result_tuning"] is not False:
        raise PreflightFailure("SC-3E execution budget is not exactly one/no retry")
    if auth_receipt["execution"]["execution_token_consumed"] is not False or auth_receipt["scientific_run_started"] is not False:
        raise PreflightFailure("SC-3E token is already consumed")
    if sc3["status"] != "CONTRACT_FROZEN_BEFORE_EXECUTION" or sc3["scientific_execution"] != "NOT_AUTHORIZED":
        raise PreflightFailure("SC-3 contract is not frozen-before-execution")
    if sc2["status"] != "FROZEN_BEFORE_SCIENTIFIC_RUN" or sc2["scientific_execution"] is not False:
        raise PreflightFailure("SC-2 freeze is not valid")

    expected = {
        SOURCE: sc3["candidate"]["source_sha256"],
        CANDIDATE_MANIFEST: sc3["candidate"]["manifest_sha256"],
        FIXTURES: sc3["inherited_anchors"]["fixture_bank_sha256"],
        RULES: sc3["inherited_anchors"]["operation_rules_sha256"],
        GRI02B_CONFIG: sc3["inherited_anchors"]["gri02b_config_sha256"],
        GRI02B_HARNESS: sc3["inherited_anchors"]["gri02b_harness_sha256"],
        GRI02B_RECEIPT: sc3["inherited_anchors"]["gri02b_receipt_sha256"],
        GRI02B_CONTRACT: sc3["inherited_anchors"]["gri02b_contract_sha256"],
        SC1R1_RECEIPT: sc3["inherited_anchors"]["sc1r1_accounting_receipt_sha256"],
        SC1L_AUTH: sc3["inherited_anchors"]["sc1l_authorization_sha256"],
        SC1L_RESULT: sc3["inherited_anchors"]["sc1l_result_sha256"],
    }
    for path, digest in expected.items():
        verify_hash(path, digest, str(path))

    for output in (RESULT, REPLAY, ENVIRONMENT, PREFLIGHT):
        if output.exists():
            raise PreflightFailure(f"single-run output already exists: {output}")
    if CHECKPOINT_DIR.exists():
        raise PreflightFailure(f"single-run checkpoints already exist: {CHECKPOINT_DIR}")

    fixture_bank = json.loads(FIXTURES.read_text(encoding="utf-8"))
    if fixture_bank["counts"] != {"by_family": {"preserve_correction": 36, "preserve_delayed_bit": 18, "preserve_order": 18, "transform_correction": 324, "transform_order": 162}, "fit": 350, "held_out": 208, "total": 558}:
        raise PreflightFailure("fixture counts differ from frozen SC-3 contract")
    if json.loads(GRI02B_RECEIPT.read_text(encoding="utf-8"))["candidate_present"] is not False:
        raise PreflightFailure("GRI-02B receipt reports candidate contamination")
    config = json.loads(GRI02B_CONFIG.read_text(encoding="utf-8"))
    if config["status"] != "FROZEN_BEFORE_RUN":
        raise PreflightFailure("GRI-02B config is not frozen")
    if json.loads(CANDIDATE_MANIFEST.read_text(encoding="utf-8"))["operations"]["selector_comparisons"] != 0:
        raise PreflightFailure("candidate manifest selector accounting is not zero")

    module = load_module(SOURCE)
    if not hasattr(module, "BranchFreeResidualCell"):
        raise PreflightFailure("Candidate B class is missing")
    sim_preflight = run_sim_preflight()
    import scipy.optimize  # noqa: F401

    return {
        "status": "PASS",
        "auth_sha256": sha256(AUTH),
        "auth_receipt_sha256": sha256(AUTH_RECEIPT),
        "sc3_sha256": sha256(SC3_CONTRACT),
        "sc3_record_sha256": sha256(SC3_RECORD),
        "sc3_verification_sha256": sha256(SC3_VERIFICATION),
        "sc2_sha256": sha256(SC2_FREEZE),
        "candidate_source_sha256": sha256(SOURCE),
        "candidate_manifest_sha256": sha256(CANDIDATE_MANIFEST),
        "fixture_bank_sha256": sha256(FIXTURES),
        "operation_rules_sha256": sha256(RULES),
        "gri02b_config_sha256": sha256(GRI02B_CONFIG),
        "gri02b_harness_sha256": sha256(GRI02B_HARNESS),
        "gri02b_receipt_sha256": sha256(GRI02B_RECEIPT),
        "gri02b_contract_sha256": sha256(GRI02B_CONTRACT),
        "sim_preflight": sim_preflight,
    }


def environment_receipt(preflight_result: dict) -> dict:
    versions = {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
    }
    return {
        "unit": "GRI-SC-3-ENVIRONMENT-RECEIPT",
        "status": "CAPTURED_BEFORE_EXECUTION",
        "runner_sha256": sha256(Path(__file__)),
        "command": "python3 experiments/run_gri_sc3.py --authorization experiments/candidates/GRI-SC-3E-one-run-execution-authorization.json",
        "versions": versions,
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "git_commit": git_commit(),
        "preflight_anchor_summary": preflight_result,
        "deterministic_algorithms": True,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def prepare_batch(rows: list[dict], index: dict[str, int]) -> tuple[torch.Tensor, torch.Tensor]:
    longest = max(len(row["tokens"]) for row in rows)
    padded = torch.full((len(rows), longest), index["PAD"], dtype=torch.long)
    lengths = torch.zeros(len(rows), dtype=torch.long)
    for row_index, row in enumerate(rows):
        ids = [index[token] for token in row["tokens"]]
        padded[row_index, : len(ids)] = torch.tensor(ids, dtype=torch.long)
        lengths[row_index] = len(ids)
    return padded, lengths


def q8_state(state: torch.Tensor) -> torch.Tensor:
    clipped = torch.clamp(state, -1.0, 1.0)
    quantized = torch.clamp(torch.round(clipped * 127.0), -127.0, 127.0)
    return quantized / 127.0


class ParentCell(nn.Module):
    def __init__(self, alphabet_size: int, width: int = 8):
        super().__init__()
        self.input = nn.Embedding(alphabet_size, width)
        self.transition = nn.Linear(width, width, bias=True)
        self.readout_layer = nn.Linear(width, 2, bias=True)
        self.state_width = width

    def initial_state(self, batch_size: int, *, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
        return torch.zeros(batch_size, self.state_width, dtype=dtype, device=device)

    def step(self, token_ids: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        return torch.tanh(self.transition(state) + self.input(token_ids))

    def readout(self, state: torch.Tensor) -> torch.Tensor:
        return self.readout_layer(state)


class StatelessBaseline(nn.Module):
    def __init__(self, alphabet_size: int, width: int = 8):
        super().__init__()
        self.input = nn.Embedding(alphabet_size, width)
        self.hidden = nn.Linear(width, width, bias=True)
        self.readout_layer = nn.Linear(width, 2, bias=True)

    def forward(self, token_ids: torch.Tensor) -> torch.Tensor:
        return self.readout_layer(torch.tanh(self.hidden(self.input(token_ids))))


def candidate_transform_step(model: nn.Module, token_ids: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
    embedded = model.input(token_ids)
    return torch.tanh(state * model.diagonal + embedded)


@torch.no_grad()
def recurrent_states(model: nn.Module, rows: list[dict], index: dict[str, int], behavior: str, mode: str) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    padded, lengths = prepare_batch(rows, index)
    q8 = mode == "q8"
    dtype = torch.float32 if q8 else DTYPES[mode]
    model = copy.deepcopy(model).to(dtype=dtype)
    state = model.initial_state(len(rows), dtype=dtype, device=torch.device("cpu"))
    final = torch.zeros_like(state)
    pre_query = torch.zeros_like(state)
    seen_query = torch.zeros(len(rows), dtype=torch.bool)
    query_ids = {index["QUERY_DELAY"], index["QUERY_CORRECTION"], index["QUERY_ORDER"]}
    for step in range(padded.shape[1]):
        active = lengths > step
        ids = padded[:, step]
        query_here = active & torch.tensor([int(value) in query_ids for value in ids.tolist()], dtype=torch.bool)
        first_query = query_here & ~seen_query
        pre_query = torch.where(first_query[:, None], state, pre_query)
        seen_query = seen_query | query_here
        if behavior == "candidate":
            next_state = model.step(ids, state)
        elif behavior == "no_preserve":
            next_state = candidate_transform_step(model, ids, state)
        elif behavior == "no_transform":
            next_state = state
        elif behavior == "no_recurrence":
            next_state = model.step(ids, torch.zeros_like(state))
        elif behavior == "parent":
            next_state = model.step(ids, state)
        else:
            raise ValueError(f"unknown behavior: {behavior}")
        if q8:
            next_state = q8_state(next_state)
        state = torch.where(active[:, None], next_state, state)
        final = torch.where(active[:, None], state, final)
    return final, pre_query, model


def prediction_metrics(predictions: np.ndarray, rows: list[dict]) -> dict:
    scopes = []
    for scope, predicate in (("all", lambda row: True), ("fit", lambda row: row["split"] == "fit"), ("held_out", lambda row: row["split"] == "held_out")):
        indices = [i for i, row in enumerate(rows) if predicate(row)]
        scopes.append({"scope": scope, "count": len(indices), "accuracy": float(np.mean([predictions[i] == rows[i]["label"] for i in indices]))})
    by_family = {}
    for family in sorted({row["family"] for row in rows}):
        indices = [i for i, row in enumerate(rows) if row["family"] == family]
        by_family[family] = {"count": len(indices), "accuracy": float(np.mean([predictions[i] == rows[i]["label"] for i in indices]))}
    by_task = {}
    for task in sorted({row["task"] for row in rows}):
        indices = [i for i, row in enumerate(rows) if row["task"] == task]
        by_task[task] = {"count": len(indices), "accuracy": float(np.mean([predictions[i] == rows[i]["label"] for i in indices]))}
    return {"scopes": scopes, "by_family": by_family, "by_task": by_task}


def scope_accuracy(metrics: dict, scope: str, families: list[str] | None = None) -> float:
    if families is None:
        return next(row["accuracy"] for row in metrics["scopes"] if row["scope"] == scope)
    return min(metrics["by_family"][family]["accuracy"] for family in families)


def fixed_decoder(states: np.ndarray, rows: list[dict]) -> dict:
    by_task = {}
    all_pass = True
    for task in sorted({row["task"] for row in rows}):
        task_indices = [i for i, row in enumerate(rows) if row["task"] == task]
        fit_indices = [i for i in task_indices if rows[i]["split"] == "fit"]
        x_fit = np.concatenate([states[fit_indices], np.ones((len(fit_indices), 1))], axis=1)
        labels = np.array([rows[i]["label"] for i in fit_indices], dtype=np.int64)
        signed = 2.0 * labels - 1.0
        result = linprog(np.zeros(x_fit.shape[1]), A_ub=-signed[:, None] * x_fit, b_ub=-np.ones(len(x_fit)), bounds=[(None, None)] * x_fit.shape[1], method="highs")
        if not result.success:
            all_pass = False
            by_task[task] = {"separator_found": False, "fit_accuracy": None, "held_out_accuracy": None, "minimum_geometric_margin": None}
            continue
        weights = result.x[:-1]
        bias = result.x[-1]
        task_rows = []
        for scope, predicate in (("fit", lambda row: row["split"] == "fit"), ("held_out", lambda row: row["split"] == "held_out")):
            selected = [i for i in task_indices if predicate(rows[i])]
            x = states[selected]
            y = np.array([rows[i]["label"] for i in selected], dtype=np.int64)
            scores = x @ weights + bias
            margins = (2.0 * y - 1.0) * scores
            norm = float(np.linalg.norm(weights))
            task_rows.append({"scope": scope, "count": len(selected), "accuracy": float(np.mean((scores >= 0).astype(np.int64) == y)), "minimum_geometric_margin": float(np.min(margins) / norm) if norm else None})
        task_pass = all(row["accuracy"] == 1.0 and row["minimum_geometric_margin"] is not None and row["minimum_geometric_margin"] > 0.0 for row in task_rows)
        all_pass = all_pass and task_pass
        by_task[task] = {"separator_found": True, "fit_accuracy": task_rows[0]["accuracy"], "held_out_accuracy": task_rows[1]["accuracy"], "minimum_geometric_margin": min(row["minimum_geometric_margin"] for row in task_rows), "rows": task_rows}
    return {"pass": all_pass, "by_task": by_task}


def state_separation(states: np.ndarray, rows: list[dict], q8: bool = False) -> dict:
    distances = {}
    for task in ("delayed_bit", "correction", "order"):
        task_rows = [(i, row) for i, row in enumerate(rows) if row["task"] == task and row["family"].startswith("preserve_")]
        by_delay = {}
        for i, row in task_rows:
            n = row["N"]
            by_delay.setdefault(n, {0: [], 1: []})[row["label"]].append(states[i])
        for n, groups in by_delay.items():
            if not groups[0] or not groups[1]:
                continue
            distances[n] = min(float(np.linalg.norm(a - b)) for a in groups[0] for b in groups[1])
        if 0 not in distances:
            return {"pass": False, "reason": f"missing N=0 separation for {task}", "distances": distances}
        baseline = distances[0]
        if baseline <= 0.0:
            return {"pass": False, "reason": f"zero N=0 separation for {task}", "distances": distances}
        if any(value < 0.5 * baseline for value in distances.values()):
            return {"pass": False, "reason": f"separation collapsed for {task}", "distances": distances, "baseline": baseline}
        if q8 and any(value <= 0.0 for value in distances.values()):
            return {"pass": False, "reason": f"q8 label merge for {task}", "distances": distances, "baseline": baseline}
    return {"pass": True, "distances": distances}


def evaluate_recurrent(model: nn.Module, rows: list[dict], index: dict[str, int], behavior: str, mode: str) -> dict:
    final, pre_query, evaluated_model = recurrent_states(model, rows, index, behavior, mode)
    with torch.no_grad():
        logits = evaluated_model.readout(final).detach().cpu().to(torch.float64).numpy()
    predictions = logits.argmax(axis=1)
    states = pre_query.detach().cpu().to(torch.float64).numpy()
    output = prediction_metrics(predictions, rows)
    result = {"output": output, "fixed_decoder": fixed_decoder(states, rows)}
    if behavior == "candidate" and mode in ("float64", "q8"):
        result["state_separation"] = state_separation(states, rows, q8=mode == "q8")
    return result


def evaluate_stateless(model: nn.Module, rows: list[dict], index: dict[str, int]) -> dict:
    model = copy.deepcopy(model).to(dtype=torch.float32)
    ids = torch.tensor([index[row["tokens"][-1]] for row in rows], dtype=torch.long)
    with torch.no_grad():
        predictions = model(ids).detach().cpu().argmax(1).numpy()
    return prediction_metrics(predictions, rows)


def train_recurrent(model: nn.Module, rows: list[dict], index: dict[str, int], learning_rate: float, epochs: int, behavior: str) -> None:
    padded, lengths = prepare_batch(rows, index)
    labels = torch.tensor([row["label"] for row in rows], dtype=torch.long)
    optimizer = torch.optim.SGD(model.parameters(), lr=learning_rate, momentum=0.0, weight_decay=0.0)
    criterion = nn.CrossEntropyLoss()
    for _ in range(epochs):
        optimizer.zero_grad(set_to_none=True)
        state = model.initial_state(len(rows), dtype=torch.float32, device=torch.device("cpu"))
        for step in range(padded.shape[1]):
            state = model.step(padded[:, step], state)
            active = lengths > step
            state = torch.where(active[:, None], state, torch.zeros_like(state))
        logits = model.readout(state)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()


def train_parent(model: ParentCell, rows: list[dict], index: dict[str, int], learning_rate: float, epochs: int) -> None:
    train_recurrent(model, rows, index, learning_rate, epochs, "parent")


def train_stateless(model: StatelessBaseline, rows: list[dict], index: dict[str, int], learning_rate: float, epochs: int) -> None:
    labels = torch.tensor([row["label"] for row in rows], dtype=torch.long)
    ids = torch.tensor([index[row["tokens"][-1]] for row in rows], dtype=torch.long)
    optimizer = torch.optim.SGD(model.parameters(), lr=learning_rate, momentum=0.0, weight_decay=0.0)
    criterion = nn.CrossEntropyLoss()
    for _ in range(epochs):
        optimizer.zero_grad(set_to_none=True)
        loss = criterion(model(ids), labels)
        loss.backward()
        optimizer.step()


def save_checkpoint(model: nn.Module, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), path)
    return sha256(path)


def load_candidate(module, path: Path) -> nn.Module:
    model = module.BranchFreeResidualCell(alphabet_size=10, state_width=8)
    model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
    return model


def load_parent(path: Path) -> ParentCell:
    model = ParentCell(10, 8)
    model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
    return model


def load_stateless(path: Path) -> StatelessBaseline:
    model = StatelessBaseline(10, 8)
    model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
    return model


@torch.no_grad()
def restart_check(model: nn.Module, rows: list[dict], index: dict[str, int], mode: str) -> dict:
    q8 = mode == "q8"
    dtype = torch.float32 if q8 else DTYPES[mode]
    evaluated = copy.deepcopy(model).to(dtype=dtype)
    checked = 0
    failures = []
    for row in rows:
        ids = [index[token] for token in row["tokens"]]
        prefix_states = [evaluated.initial_state(1, dtype=dtype, device=torch.device("cpu"))]
        for token_id in ids:
            token = torch.tensor([token_id], dtype=torch.long)
            next_state = evaluated.step(token, prefix_states[-1])
            prefix_states.append(q8_state(next_state) if q8 else next_state)
        full = prefix_states[-1]
        for split in range(len(ids) + 1):
            payload = evaluated.serialize_state(prefix_states[split])
            resumed = evaluated.restore_state(payload, dtype=dtype, device=torch.device("cpu"))
            for token_id in ids[split:]:
                token = torch.tensor([token_id], dtype=torch.long)
                next_state = evaluated.step(token, resumed)
                resumed = q8_state(next_state) if q8 else next_state
            checked += 1
            if not torch.equal(full, resumed):
                failures.append({"fixture_id": row["fixture_id"], "split": split})
                if len(failures) >= 10:
                    return {"status": "FAIL", "cases": checked, "failures": failures}
    return {"status": "PASS" if not failures else "FAIL", "cases": checked, "failures": failures}


def summarize_seed(seed: int, candidate: nn.Module, parent: nn.Module, stateless: nn.Module, rows: list[dict], fit: list[dict], index: dict[str, int], candidate_checkpoint: str, parent_checkpoint: str, stateless_checkpoint: str) -> dict:
    preserve_families = ["preserve_delayed_bit", "preserve_correction", "preserve_order"]
    transform_families = ["transform_correction", "transform_order"]
    candidate_modes = {mode: evaluate_recurrent(candidate, rows, index, "candidate", mode) for mode in ALL_MODES}
    parent_modes = {mode: evaluate_recurrent(parent, rows, index, "parent", mode) for mode in REQUIRED_MODES}
    ablation_modes = {
        "no_preserve": {mode: evaluate_recurrent(candidate, rows, index, "no_preserve", mode) for mode in REQUIRED_MODES},
        "no_transform": {mode: evaluate_recurrent(candidate, rows, index, "no_transform", mode) for mode in REQUIRED_MODES},
        "no_recurrence": {mode: evaluate_recurrent(candidate, rows, index, "no_recurrence", mode) for mode in REQUIRED_MODES},
    }
    stateless_metrics = evaluate_stateless(stateless, rows, index)
    candidate_preserve_pass = all(scope_accuracy(candidate_modes[mode]["output"], "all", preserve_families) == 1.0 for mode in REQUIRED_MODES)
    candidate_transform_pass = all(scope_accuracy(candidate_modes[mode]["output"], "all", transform_families) == 1.0 for mode in REQUIRED_MODES)
    candidate_fixed_decoder_pass = all(candidate_modes[mode]["fixed_decoder"]["pass"] for mode in REQUIRED_MODES)
    candidate_precision_pass = candidate_preserve_pass and candidate_transform_pass and candidate_fixed_decoder_pass and all(candidate_modes[mode]["state_separation"]["pass"] for mode in ("float64", "q8"))
    candidate_held_out_pass = all(scope_accuracy(candidate_modes[mode]["output"], "held_out") == 1.0 for mode in REQUIRED_MODES)
    parent_held_out_fails = any(scope_accuracy(parent_modes[mode]["output"], "held_out") < 1.0 for mode in REQUIRED_MODES)
    stateless_held_out_fails = scope_accuracy(stateless_metrics, "held_out") < 1.0
    no_preserve_failed = any(scope_accuracy(ablation_modes["no_preserve"][mode]["output"], "held_out") < 1.0 for mode in REQUIRED_MODES)
    no_transform_failed = any(scope_accuracy(ablation_modes["no_transform"][mode]["output"], "held_out", transform_families) < 1.0 for mode in REQUIRED_MODES)
    no_recurrence_failed = any(scope_accuracy(ablation_modes["no_recurrence"][mode]["output"], "held_out") < 1.0 for mode in REQUIRED_MODES)
    restart = {mode: restart_check(candidate, rows, index, mode) for mode in ("float64", "float32", "q8")}
    restart_pass = all(value["status"] == "PASS" for value in restart.values())
    return {
        "seed": seed,
        "candidate_checkpoint_sha256": candidate_checkpoint,
        "parent_checkpoint_sha256": parent_checkpoint,
        "stateless_checkpoint_sha256": stateless_checkpoint,
        "candidate": {"modes": candidate_modes, "preserve_pass": candidate_preserve_pass, "transform_pass": candidate_transform_pass, "fixed_decoder_pass": candidate_fixed_decoder_pass, "precision_pass": candidate_precision_pass},
        "parent": {"modes": parent_modes, "held_out_fails": parent_held_out_fails},
        "stateless": {"output": stateless_metrics, "held_out_fails": stateless_held_out_fails},
        "ablations": ablation_modes,
        "restart": restart,
        "verdict_inputs": {
            "candidate_preserve_pass": candidate_preserve_pass,
            "candidate_transform_pass": candidate_transform_pass,
            "candidate_fixed_decoder_pass": candidate_fixed_decoder_pass,
            "candidate_precision_pass": candidate_precision_pass,
            "parent_opponent_pass": candidate_held_out_pass and parent_held_out_fails,
            "stateless_opponent_pass": candidate_held_out_pass and stateless_held_out_fails,
            "no_preserve_ablation_failed": no_preserve_failed,
            "no_transform_ablation_failed": no_transform_failed,
            "no_recurrence_ablation_failed": no_recurrence_failed,
            "restart_pass": restart_pass,
        },
    }


def oracle_result(rows: list[dict]) -> dict:
    sys.path.insert(0, str(EXPERIMENTS))
    import gri02b_preregistration as prereg
    result = prereg.check_oracle(rows)
    return {"status": result["status"], "fixture_count": result["fixture_count"], "restart_cases": result["restart_cases"], "failures": result["failures"][:10]}


def run_scientific(module, rows: list[dict], fit: list[dict], index: dict[str, int], environment: dict) -> tuple[dict, dict]:
    manifest = json.loads(CANDIDATE_MANIFEST.read_text(encoding="utf-8"))
    training = json.loads(SC2_FREEZE.read_text(encoding="utf-8"))["training"]
    candidate_runs = []
    for seed in training["seeds"]:
        print(f"SC3 seed {seed}: training frozen candidate and controls", file=sys.stderr, flush=True)
        set_seed(seed)
        candidate = module.BranchFreeResidualCell(alphabet_size=10, state_width=8)
        train_recurrent(candidate, fit, index, training["learning_rate"], training["epochs"], "candidate")
        candidate_path = CHECKPOINT_DIR / f"seed_{seed}_candidate.pt"
        candidate_sha = save_checkpoint(candidate, candidate_path)

        set_seed(seed)
        parent = ParentCell(10, 8)
        train_parent(parent, fit, index, 0.03, 400)
        parent_path = CHECKPOINT_DIR / f"seed_{seed}_parent.pt"
        parent_sha = save_checkpoint(parent, parent_path)

        set_seed(seed)
        stateless = StatelessBaseline(10, 8)
        train_stateless(stateless, fit, index, 0.03, 400)
        stateless_path = CHECKPOINT_DIR / f"seed_{seed}_stateless.pt"
        stateless_sha = save_checkpoint(stateless, stateless_path)

        candidate_runs.append(summarize_seed(seed, candidate, parent, stateless, rows, fit, index, candidate_sha, parent_sha, stateless_sha))

    oracle = oracle_result(rows)
    replay_runs = []
    for run in candidate_runs:
        seed = run["seed"]
        candidate = load_candidate(module, CHECKPOINT_DIR / f"seed_{seed}_candidate.pt")
        parent = load_parent(CHECKPOINT_DIR / f"seed_{seed}_parent.pt")
        stateless = load_stateless(CHECKPOINT_DIR / f"seed_{seed}_stateless.pt")
        replay_runs.append(summarize_seed(seed, candidate, parent, stateless, rows, fit, index, run["candidate_checkpoint_sha256"], run["parent_checkpoint_sha256"], run["stateless_checkpoint_sha256"]))

    replay_basis = [{"seed": run["seed"], "verdict_inputs": run["verdict_inputs"], "candidate": run["candidate"], "parent": run["parent"], "stateless": run["stateless"], "ablations": run["ablations"], "restart": run["restart"]} for run in candidate_runs]
    replay_basis_again = [{"seed": run["seed"], "verdict_inputs": run["verdict_inputs"], "candidate": run["candidate"], "parent": run["parent"], "stateless": run["stateless"], "ablations": run["ablations"], "restart": run["restart"]} for run in replay_runs]
    replay_pass = canonical(replay_basis) == canonical(replay_basis_again)
    required_fields = [
        "candidate_preserve_pass", "candidate_transform_pass", "candidate_fixed_decoder_pass", "candidate_precision_pass",
        "parent_opponent_pass", "stateless_opponent_pass", "no_preserve_ablation_failed", "no_transform_ablation_failed",
        "no_recurrence_ablation_failed", "restart_pass",
    ]
    aggregate = {field: all(run["verdict_inputs"][field] for run in candidate_runs) for field in required_fields}
    aggregate["oracle_pass"] = oracle["status"] == "PASS"
    aggregate["replay_pass"] = replay_pass
    aggregate["budget_pass"] = (
        manifest["state"]["persistent_slots"] <= 8
        and manifest["parameters"]["trainable"] <= 170
        and manifest["operations"]["recurrent"] <= 97
        and manifest["operations"]["recurrent_plus_query"] <= 118
    )
    aggregate["artifact_integrity_pass"] = True
    final = "GRI_SC3_ADVANTAGE" if all(aggregate.values()) else "GRI_SC3_NO_ADVANTAGE"
    primary = {
        "unit": "GRI-SC-3-SCIENTIFIC-RUN",
        "candidate_id": manifest["candidate_id"],
        "candidate_runs": candidate_runs,
        "oracle": oracle,
        "aggregate_verdict_inputs": aggregate,
        "candidate_verdict": final,
    }
    replay = {
        "unit": "GRI-SC-3-DETERMINISTIC-REPLAY",
        "status": "PASS" if replay_pass else "FAIL",
        "primary_summary_sha256": hashlib.sha256(canonical(primary)).hexdigest(),
        "replayed_summary_sha256": hashlib.sha256(canonical({"candidate_runs": replay_runs, "oracle": oracle, "aggregate_verdict_inputs": aggregate})).hexdigest(),
        "matched": replay_pass,
        "environment_sha256": sha256(ENVIRONMENT),
    }
    return primary, replay


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, default=AUTH)
    args = parser.parse_args()
    if args.authorization.resolve() != AUTH.resolve():
        print("authorization path mismatch", file=sys.stderr)
        return 2
    try:
        preflight_result = preflight()
    except Exception as exc:
        print(f"SC3 preflight failed; authorization remains unconsumed: {exc}", file=sys.stderr)
        return 2

    try:
        env = environment_receipt(preflight_result)
        env_sha = write_json(ENVIRONMENT, env)
        consumed = {
            "unit": "GRI-SC-3E-PREFLIGHT",
            "status": "PASS_TOKEN_CONSUMED",
            "preflight": preflight_result,
            "environment_receipt_sha256": env_sha,
            "execution_token_consumed": True,
            "scientific_run_started": False,
            "retries": 0,
            "consumed_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        write_json(PREFLIGHT, consumed)
    except Exception as exc:
        print(f"SC3 preflight passed but token consumption could not be recorded: {exc}", file=sys.stderr)
        return 2

    try:
        fixture_bank = json.loads(FIXTURES.read_text(encoding="utf-8"))
        rows = fixture_bank["fixtures"]
        fit = [row for row in rows if row["split"] == "fit"]
        index = {token: i for i, token in enumerate(fixture_bank["alphabet"])}
        module = load_module(SOURCE)
        primary, replay = run_scientific(module, rows, fit, index, env)
        replay_sha = write_json(REPLAY, replay)
        result = {
            "unit": "GRI-SC-3-SCIENTIFIC-RUN",
            "status": "EXECUTED",
            "candidate_verdict": primary["candidate_verdict"],
            "execution_token_consumed": True,
            "retries": 0,
            "post_result_tuning": False,
            "source_sha256": sha256(SOURCE),
            "authorization_sha256": sha256(AUTH),
            "contract_sha256": sha256(SC3_CONTRACT),
            "freeze_sha256": sha256(SC2_FREEZE),
            "environment_receipt_sha256": sha256(ENVIRONMENT),
            "replay_receipt_sha256": replay_sha,
            "runner_sha256": sha256(Path(__file__)),
            "primary": primary,
            "replay": replay,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        result_sha = write_json(RESULT, result)
        print(primary["candidate_verdict"])
        print(f"SC3 result receipt SHA-256: {result_sha}", file=sys.stderr)
        return 0
    except Exception as exc:
        error = {
            "unit": "GRI-SC-3-SCIENTIFIC-RUN",
            "status": "EXECUTION_FAILURE",
            "candidate_verdict": "GRI_SC3_INCONCLUSIVE",
            "execution_token_consumed": True,
            "retries": 0,
            "error": repr(exc),
            "traceback": traceback.format_exc(),
            "environment_receipt_sha256": sha256(ENVIRONMENT),
            "runner_sha256": sha256(Path(__file__)),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        write_json(RESULT, error)
        print("GRI_SC3_INCONCLUSIVE")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
