# ContextForge

A grounded, local-first RAG workspace for the sources you control.

ContextForge turns your own documents — PDFs, Word files, web pages, YouTube
videos, GitHub repositories and plain text — into a queryable, cited knowledge
base. Point it at a source, ask a question in natural language, and get an answer
with **inline citations**, a **confidence score**, and a **per-stage latency
breakdown** you can audit.

Most chat tools answer from a model's training data and give you no way to check.
ContextForge indexes sources *you* choose, cites the exact passage behind each
claim, and tells you when its own confidence is low and why.

> **Grounded or silent.** Answers come from the sources you selected. Selection is
> the primary control, not a hidden default.

## What you get

- **Cited, not asserted** — every answer shows the exact chunks it used, with
  scores and metadata.
- **Hybrid retrieval** — BM25 (SQLite FTS5) and dense vectors (FAISS) fused with
  Reciprocal Rank Fusion, then re-scored by a cross-encoder.
- **Honest about cost** — selecting sources prices the selection against the
  prompt budget *before* you ask, with no model call.
- **Inspectable sources** — an extraction verdict flags a scanned or half-empty
  PDF instead of letting it answer as if it had been read.
- **Repository Studio** — architecture diagrams, security and quality scans,
  dependency inventory and health hotspots for any GitHub repository.
- **Your models, your keys** — nine hosted providers or any local
  OpenAI-compatible server, chained with failover.

## How it is put together

ContextForge is a client–server system. A React 19 single-page app talks to a
FastAPI backend over REST and Server-Sent Events. The backend wraps a RAG engine
behind an *orchestrator* that coordinates loading, chunking, indexing, retrieval
and generation.

```text
ingest:  Source ──► loader ──► chunker ──► embedder ──► FAISS + BM25
                                          │
                                     on-disk cache

query:   question ──► HyDE (optional) ──► embed ──► BM25 ⊕ dense ──► RRF fusion
                                                          │
                                              cross-encoder rerank
                                                          │
                                              prompt assembly ──► LLM ──► SSE
```

The architecture is deliberately **provider-agnostic**: every external capability
(embedder, LLM, retriever) sits behind an interface in `core/interfaces/`, so
swapping the embedder or the LLM is a configuration change, not a rewrite.

## Where to go next

- **[Quickstart](/docs/quickstart)** — install, configure a model, ingest your
  first source and ask your first question.
- **[Capabilities](/docs/capabilities)** — what ContextForge can do, by input type.
- **[Sources](/docs/sources)** — how each format is extracted and how to verify it.
- **[Retrieval pipeline](/docs/pipeline)** — what each stage actually does.
- **[API reference](/docs/api)** — the live, generated spec and a curated list of
  the calls you are likely to make by hand.
