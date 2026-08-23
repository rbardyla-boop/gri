# DMC-05A Run 2 engineering amendment

Run 1 exited before aggregation or a scientific verdict. The first
`dmc_retrieval_all_history` worker sent a 32-record candidate list through a
frozen scorer-view firewall whose legal per-call capacity is 16. The preserved
failure receipt and traceback are under
`artifacts/dmc05a/run1_engineering_failure/`.

Run 2 changes only the evaluation adapter:

1. Partition the complete-history candidate sequence into ordered chunks of at
   most 16.
2. Call the unchanged frozen DMC-04R2 scoring function on every chunk.
3. Concatenate those candidate-independent scores in original order.
4. Apply an exact transcription of the unchanged DMC-04B global
   descriptor-group tie break and temporal resolver.
5. Report every scorer call, every candidate inspected, and the complete
   all-history working set. The ablation is not reclassified as bounded.
6. Accept replay receipts written to an external temporary directory; this
   fixes a pre-run path-serialization defect found during the Run 1 audit.

The repair does not alter data, cases, checkpoints, parameters, features,
score equations, candidate order, resolution semantics, thresholds, terminal
state rules, or training. Unit tests require equivalence with the frozen
retriever at legal capacity, successful complete-history batching through the
firewall, and an external replay path.

Run 1 generated partial worker receipts, but no capability values were used to
choose this repair and no decision threshold changed. Run 2 is a justified
engineering rerun, not a post-result model or protocol adjustment.
