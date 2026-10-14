# Performance

- **Exact search.** `IndexFlatIP` is brute-force: results are exact with no
  approximate-recall trade-off, and query cost grows linearly with the number of
  chunks. It is well suited to personal and small-team corpora. A different index
  would sit behind the same interfaces.
- **Parallel retrieval.** BM25 and dense search run concurrently, then fuse.
- **Cheap re-ingest.** The embedding cache means re-ingesting unchanged content
  does not pay for embeddings twice.
- **Cached analyses.** Notes and mind maps are keyed by the selection; Studio
  results are keyed by a content fingerprint of the repository. Unchanged inputs
  are not recomputed.
- **Measure, don't guess.** Every answer carries a per-stage latency breakdown, so
  you can see whether retrieval, reranking or generation dominates *on your
  hardware with your models*.
- **No published benchmarks yet.** Retrieval-quality and throughput numbers are
  not published. Until then, treat any figure you have not measured yourself as
  unverified.
