from __future__ import annotations

import torch
from torch import nn

from .data import GraphExample, NUM_RELATIONS


class WeightTiedGraphReasoner(nn.Module):
    """Simple weight-tied recurrent graph baseline.

    The model receives asserted directed relation edges. For each ordered pair
    (j, i), it sees both j->i and i->j edge channels, but no explicit inverse
    label. Thus inverse reasoning remains learned rather than inserted by the
    data adapter.
    """

    def __init__(self, hidden_dim: int = 48, message_dim: int = 48):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.node_in = nn.Linear(3, hidden_dim)
        pair_dim = hidden_dim * 2 + NUM_RELATIONS * 2
        self.message = nn.Sequential(
            nn.Linear(pair_dim, message_dim),
            nn.Tanh(),
            nn.Linear(message_dim, hidden_dim),
        )
        self.gate = nn.Sequential(nn.Linear(hidden_dim * 2, hidden_dim), nn.Sigmoid())
        self.delta = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh(),
        )
        self.norm = nn.LayerNorm(hidden_dim)
        self.readout = nn.Sequential(
            nn.Linear(hidden_dim * 4, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, NUM_RELATIONS),
        )

    def initialize(self, example: GraphExample) -> torch.Tensor:
        return torch.tanh(self.node_in(example.node_features.to(next(self.parameters()).device)))

    def recurrent_step(self, h: torch.Tensor, edges: torch.Tensor) -> torch.Tensor:
        n, _ = h.shape
        edges = edges.to(h.device)
        # Compute exactly the graph-adjacent ordered pairs that survived the
        # original dense mask. This is an execution-only sparsification: pair
        # features and aggregation semantics are unchanged.
        adjacency = (edges.sum(dim=-1) + edges.transpose(0, 1).sum(dim=-1)) > 0
        senders, receivers = adjacency.nonzero(as_tuple=True)
        aggregated = torch.zeros_like(h)
        if senders.numel():
            pair = torch.cat([
                h[senders],
                h[receivers],
                edges[senders, receivers],
                edges[receivers, senders],
            ], dim=-1)
            messages = self.message(pair)
            aggregated.index_add_(0, receivers, messages)
        context = torch.cat([h, aggregated], dim=-1)
        gate = self.gate(context)
        delta = self.delta(context)
        return self.norm(h + gate * delta)

    def forward(self, example: GraphExample, steps: int = 4) -> torch.Tensor:
        h = self.initialize(example)
        edges = example.edges.to(h.device)
        for _ in range(steps):
            h = self.recurrent_step(h, edges)
        a = h[example.query_subject]
        b = h[example.query_object]
        features = torch.cat([a, b, a - b, a * b], dim=-1)
        return self.readout(features)
