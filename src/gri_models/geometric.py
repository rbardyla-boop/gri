from __future__ import annotations

import torch
from torch import nn

from .data import GraphExample, NUM_RELATIONS


class SO4GeometricReasoner(nn.Module):
    """Weight-tied recurrent graph model with exact local SO(4) covariance.

    Geometric channels transform under independently chosen node frames. The
    scored readout uses invariant quantities only. The implementation accepts
    explicit frames so frame invariance is directly testable.
    """

    def __init__(self, semantic_dim: int = 40, channels: int = 2, message_dim: int = 48):
        super().__init__()
        self.dg = 4
        self.channels = channels
        self.semantic_dim = semantic_dim
        self.semantic_in = nn.Linear(3, semantic_dim)
        self.canonical_geom = nn.Linear(3, self.dg * channels, bias=False)

        gram_size = channels * channels
        invariant_pair_dim = semantic_dim * 2 + NUM_RELATIONS * 2 + gram_size * 3
        self.semantic_message = nn.Sequential(
            nn.Linear(invariant_pair_dim, message_dim), nn.Tanh(), nn.Linear(message_dim, semantic_dim)
        )
        self.geom_coeff = nn.Sequential(
            nn.Linear(invariant_pair_dim, message_dim), nn.Tanh(), nn.Linear(message_dim, 2 * channels * channels)
        )

        node_inv_dim = semantic_dim * 2 + gram_size
        self.semantic_gate = nn.Sequential(nn.Linear(node_inv_dim, semantic_dim), nn.Sigmoid())
        self.semantic_delta = nn.Sequential(
            nn.Linear(node_inv_dim, semantic_dim), nn.Tanh(), nn.Linear(semantic_dim, semantic_dim), nn.Tanh()
        )
        self.geom_update_coeff = nn.Sequential(
            nn.Linear(node_inv_dim, message_dim), nn.Tanh(), nn.Linear(message_dim, 2 * channels * channels)
        )
        self.geom_gate = nn.Sequential(nn.Linear(node_inv_dim, channels), nn.Sigmoid())
        self.semantic_norm = nn.LayerNorm(semantic_dim)

        readout_dim = semantic_dim * 4 + gram_size * 3
        self.readout = nn.Sequential(
            nn.Linear(readout_dim, semantic_dim), nn.Tanh(), nn.Linear(semantic_dim, NUM_RELATIONS)
        )

    @staticmethod
    def identity_frames(n: int, *, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
        return torch.eye(4, device=device, dtype=dtype).expand(n, 4, 4).clone()

    def initialize(self, example: GraphExample, frames: torch.Tensor | None = None):
        device = next(self.parameters()).device
        x = example.node_features.to(device)
        s = torch.tanh(self.semantic_in(x))
        z = self.canonical_geom(x).reshape(x.shape[0], self.dg, self.channels)
        if frames is None:
            frames = self.identity_frames(x.shape[0], device=device, dtype=x.dtype)
        else:
            frames = frames.to(device=device, dtype=x.dtype)
        v = torch.einsum("nij,njc->nic", frames, z)
        return s, v, frames

    @staticmethod
    def connections(frames: torch.Tensor) -> torch.Tensor:
        # U[j,i] transports from j's frame to i's frame: Q_i Q_j^T.
        # Output shape [j, i, 4, 4].
        qi = frames[None, :, :, :]
        qjt = frames[:, None, :, :].transpose(-1, -2)
        return torch.matmul(qi, qjt)

    def recurrent_step(self, s: torch.Tensor, v: torch.Tensor, edges: torch.Tensor, frames: torch.Tensor):
        n, ds = s.shape
        c = self.channels
        edges = edges.to(s.device)
        u = self.connections(frames)
        # transported[j,i] = U[j,i] @ V[j]
        transported = torch.einsum("jiab,jbc->jiac", u, v)

        s_j = s[:, None, :].expand(n, n, ds)
        s_i = s[None, :, :].expand(n, n, ds)
        v_i = v[None, :, :, :].expand(n, n, self.dg, c)

        g_ii = torch.einsum("jiac,jiad->jicd", v_i, v_i)
        g_jj = torch.einsum("jiac,jiad->jicd", transported, transported)
        g_ij = torch.einsum("jiac,jiad->jicd", v_i, transported)
        invariant = torch.cat([
            s_j,
            s_i,
            edges,
            edges.transpose(0, 1),
            g_ii.reshape(n, n, -1),
            g_jj.reshape(n, n, -1),
            g_ij.reshape(n, n, -1),
        ], dim=-1)

        ms = self.semantic_message(invariant)
        coeff = self.geom_coeff(invariant).reshape(n, n, 2, c, c)
        a = coeff[:, :, 0]
        b = coeff[:, :, 1]
        mv = torch.einsum("jiac,jicd->jiad", v_i, a) + torch.einsum("jiac,jicd->jiad", transported, b)

        adjacency = (edges.sum(dim=-1) + edges.transpose(0, 1).sum(dim=-1)) > 0
        mask = adjacency.unsqueeze(-1)
        agg_s = (ms * mask).sum(dim=0)
        agg_v = (mv * mask.unsqueeze(-1)).sum(dim=0)

        local_gram = torch.einsum("nac,nad->ncd", v, v).reshape(n, -1)
        node_inv = torch.cat([s, agg_s, local_gram], dim=-1)
        s_new = self.semantic_norm(s + self.semantic_gate(node_inv) * self.semantic_delta(node_inv))

        update_coeff = self.geom_update_coeff(node_inv).reshape(n, 2, c, c)
        c_self, c_msg = update_coeff[:, 0], update_coeff[:, 1]
        dv = torch.einsum("nac,ncd->nad", v, c_self) + torch.einsum("nac,ncd->nad", agg_v, c_msg)
        g = self.geom_gate(node_inv).unsqueeze(1)
        v_new = v + g * dv
        return s_new, v_new

    def forward(self, example: GraphExample, steps: int = 4, frames: torch.Tensor | None = None) -> torch.Tensor:
        s, v, frames = self.initialize(example, frames)
        edges = example.edges.to(s.device)
        for _ in range(steps):
            s, v = self.recurrent_step(s, v, edges, frames)
        i, j = example.query_subject, example.query_object
        si, sj = s[i], s[j]
        gi = v[i].transpose(0, 1) @ v[i]
        gj = v[j].transpose(0, 1) @ v[j]
        # Transport j into i frame before cross Gram invariant.
        u_ji = frames[i] @ frames[j].T
        vj_i = u_ji @ v[j]
        gij = v[i].T @ vj_i
        features = torch.cat([si, sj, si - sj, si * sj, gi.flatten(), gj.flatten(), gij.flatten()])
        return self.readout(features)
