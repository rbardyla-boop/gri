from pathlib import Path

import torch

from gri_models.baseline import WeightTiedGraphReasoner
from gri_models.data import load_examples
from gri_models.geometric import SO4GeometricReasoner

ROOT = Path(__file__).resolve().parents[1]
EX = load_examples(ROOT / "artifacts/frozen/world0_v0_1/train.jsonl")[7]


def _dense_baseline_step(model, h, edges):
    n, d = h.shape
    h_j = h[:, None, :].expand(n, n, d)
    h_i = h[None, :, :].expand(n, n, d)
    pair = torch.cat([h_j, h_i, edges, edges.transpose(0, 1)], dim=-1)
    messages = model.message(pair)
    adjacency = (edges.sum(dim=-1) + edges.transpose(0, 1).sum(dim=-1)) > 0
    aggregated = (messages * adjacency.unsqueeze(-1)).sum(dim=0)
    context = torch.cat([h, aggregated], dim=-1)
    return model.norm(h + model.gate(context) * model.delta(context))


def _dense_so4_step(model, s, v, edges, frames):
    n, ds = s.shape
    c = model.channels
    u = model.connections(frames)
    transported = torch.einsum("jiab,jbc->jiac", u, v)
    s_j = s[:, None, :].expand(n, n, ds)
    s_i = s[None, :, :].expand(n, n, ds)
    v_i = v[None, :, :, :].expand(n, n, model.dg, c)
    g_ii = torch.einsum("jiac,jiad->jicd", v_i, v_i)
    g_jj = torch.einsum("jiac,jiad->jicd", transported, transported)
    g_ij = torch.einsum("jiac,jiad->jicd", v_i, transported)
    invariant = torch.cat([
        s_j, s_i, edges, edges.transpose(0, 1),
        g_ii.reshape(n, n, -1), g_jj.reshape(n, n, -1), g_ij.reshape(n, n, -1),
    ], dim=-1)
    ms = model.semantic_message(invariant)
    coeff = model.geom_coeff(invariant).reshape(n, n, 2, c, c)
    mv = torch.einsum("jiac,jicd->jiad", v_i, coeff[:, :, 0]) + torch.einsum(
        "jiac,jicd->jiad", transported, coeff[:, :, 1]
    )
    adjacency = (edges.sum(dim=-1) + edges.transpose(0, 1).sum(dim=-1)) > 0
    agg_s = (ms * adjacency.unsqueeze(-1)).sum(dim=0)
    agg_v = (mv * adjacency.unsqueeze(-1).unsqueeze(-1)).sum(dim=0)
    local_gram = torch.einsum("nac,nad->ncd", v, v).reshape(n, -1)
    node_inv = torch.cat([s, agg_s, local_gram], dim=-1)
    s_new = model.semantic_norm(s + model.semantic_gate(node_inv) * model.semantic_delta(node_inv))
    update_coeff = model.geom_update_coeff(node_inv).reshape(n, 2, c, c)
    dv = torch.einsum("nac,ncd->nad", v, update_coeff[:, 0]) + torch.einsum(
        "nac,ncd->nad", agg_v, update_coeff[:, 1]
    )
    v_new = v + model.geom_gate(node_inv).unsqueeze(1) * dv
    return s_new, v_new


def _parameter_grads(model):
    return [None if p.grad is None else p.grad.detach().clone() for p in model.parameters()]


def test_baseline_sparse_step_matches_dense_output_and_gradients():
    torch.manual_seed(17)
    sparse = WeightTiedGraphReasoner(hidden_dim=13, message_dim=11)
    dense = WeightTiedGraphReasoner(hidden_dim=13, message_dim=11)
    dense.load_state_dict(sparse.state_dict())
    h1 = sparse.initialize(EX).detach().requires_grad_(True)
    h2 = h1.detach().clone().requires_grad_(True)
    edges = EX.edges
    y1 = sparse.recurrent_step(h1, edges)
    y2 = _dense_baseline_step(dense, h2, edges)
    assert torch.allclose(y1, y2, atol=2e-6, rtol=2e-6)
    y1.square().sum().backward(); y2.square().sum().backward()
    assert torch.allclose(h1.grad, h2.grad, atol=3e-6, rtol=3e-6)
    for a, b in zip(_parameter_grads(sparse), _parameter_grads(dense)):
        if a is None or b is None:
            assert a is b
        else:
            assert torch.allclose(a, b, atol=5e-6, rtol=5e-6)


def test_so4_sparse_step_matches_dense_output_and_gradients():
    torch.manual_seed(19)
    sparse = SO4GeometricReasoner(semantic_dim=11, channels=2, message_dim=9)
    dense = SO4GeometricReasoner(semantic_dim=11, channels=2, message_dim=9)
    dense.load_state_dict(sparse.state_dict())
    s1, v1, q = sparse.initialize(EX)
    s1 = s1.detach().requires_grad_(True); v1 = v1.detach().requires_grad_(True)
    s2 = s1.detach().clone().requires_grad_(True); v2 = v1.detach().clone().requires_grad_(True)
    y1s, y1v = sparse.recurrent_step(s1, v1, EX.edges, q)
    y2s, y2v = _dense_so4_step(dense, s2, v2, EX.edges, q)
    assert torch.allclose(y1s, y2s, atol=3e-6, rtol=3e-6)
    assert torch.allclose(y1v, y2v, atol=5e-6, rtol=5e-6)
    (y1s.square().sum() + y1v.square().sum()).backward()
    (y2s.square().sum() + y2v.square().sum()).backward()
    assert torch.allclose(s1.grad, s2.grad, atol=1e-5, rtol=1e-5)
    assert torch.allclose(v1.grad, v2.grad, atol=1e-5, rtol=1e-5)
    for a, b in zip(_parameter_grads(sparse), _parameter_grads(dense)):
        if a is None or b is None:
            assert a is b
        else:
            assert torch.allclose(a, b, atol=2e-5, rtol=2e-5)
