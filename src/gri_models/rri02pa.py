from __future__ import annotations

import torch

from .baseline import WeightTiedGraphReasoner
from .data import GraphExample


class ImmutableRelationAnchorReasoner(WeightTiedGraphReasoner):
    """RRI-02P-A's parameter-neutral immutable relation-anchor candidate.

    The module topology is inherited unchanged from the surviving baseline.
    The only architectural change is in the recurrent computation: the
    current state and a write-protected copy of the example's initial state
    are averaged before message-conditioned gating and updating.  The
    mutable state alone is passed to the inherited relation readout.
    """

    def recurrent_step(
        self,
        h: torch.Tensor,
        edges: torch.Tensor,
        anchor: torch.Tensor,
    ) -> torch.Tensor:
        if h.shape != anchor.shape:
            raise ValueError("anchor and mutable state must have identical shapes")
        edges = edges.to(h.device)
        adjacency = (edges.sum(dim=-1) + edges.transpose(0, 1).sum(dim=-1)) > 0
        senders, receivers = adjacency.nonzero(as_tuple=True)
        aggregated = torch.zeros_like(h)
        if senders.numel():
            pair = torch.cat(
                [
                    h[senders],
                    h[receivers],
                    edges[senders, receivers],
                    edges[receivers, senders],
                ],
                dim=-1,
            )
            messages = self.message(pair)
            aggregated.index_add_(0, receivers, messages)
        h_anchor = (h + anchor) / 2.0
        context = torch.cat([h_anchor, aggregated], dim=-1)
        gate = self.gate(context)
        delta = self.delta(context)
        return self.norm(h + gate * delta)

    @staticmethod
    def make_anchor(h0: torch.Tensor) -> torch.Tensor:
        """Create the write-protected per-example anchor without aliasing h0."""
        return h0.clone()

    def readout_hidden(
        self,
        h: torch.Tensor,
        query_subject: int,
        query_object: int,
    ) -> torch.Tensor:
        """Read only the mutable reasoning state; the anchor is not an input."""
        a = h[query_subject]
        b = h[query_object]
        features = torch.cat([a, b, a - b, a * b], dim=-1)
        return self.readout(features)

    def forward_with_anchor_trace(
        self,
        example: GraphExample,
        steps: int = 4,
    ) -> tuple[torch.Tensor, list[torch.Tensor], list[torch.Tensor]]:
        h = self.initialize(example)
        anchor = self.make_anchor(h)
        edges = example.edges.to(h.device)
        states = [h.clone()]
        anchors = [anchor.clone()]
        for _ in range(steps):
            h = self.recurrent_step(h, edges, anchor)
            states.append(h.clone())
            anchors.append(anchor.clone())
        logits = self.readout_hidden(h, example.query_subject, example.query_object)
        return logits, states, anchors

    def forward(self, example: GraphExample, steps: int = 4) -> torch.Tensor:
        logits, _, _ = self.forward_with_anchor_trace(example, steps=steps)
        return logits
