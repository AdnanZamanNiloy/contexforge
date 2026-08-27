# Evaluation

ContextForge reports a confidence + coverage score per answer so that retrieval
quality is observable, not assumed.

## What it tracks

- `answer_confidence` — weighted across source relevance and grounding support.
- `source_coverage` — how evenly the answer draws on the retrieved sources
  (low focus on a single source is deliberately not over-boosted).
- `retrieved_chunks` / `sources_used` — how many candidates were fetched and how
  many survived reranking into the prompt.

## Methodology

The intent is to compare retrieval strategies on a fixed, local question set:

1. Build a small gold set of query → relevant-source pairs.
2. Measure recall@k and MRR for: dense-only, BM25-only, hybrid (RRF), and
   hybrid + cross-encoder rerank, with and without HyDE.
3. Log `answer_confidence` and `source_coverage` alongside each answer.

## Status

The pipeline already emits these metrics at runtime (see the `/query/stream`
`[LATENCY]` and `[CONFIDENCE]` events). A reproducible benchmark run with
reported numbers is still a work item — the hooks are in place, the script is
not. Avoid quoting specific accuracy figures until a full gold set is measured.
