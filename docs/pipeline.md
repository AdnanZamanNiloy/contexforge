# Ingestion & retrieval pipeline

## Ingestion

1. **Load** — a per-type loader turns a source into one or more plain-text
   `Document`s. Supported: PDF (`pypdf`), Word (`python-docx`), web
   (`trafilatura`), GitHub (REST + AST chunking), YouTube transcripts, and raw
   text.
2. **Chunk** — `text_chunker.py` splits on token boundaries; `code_chunker.py`
   is AST-aware so whole symbols stay together.
3. **Embed** — Voyage AI (`voyage-3-lite`) with an on-disk embedding cache and a
   local BGE fallback.
4. **Index** — dense vectors into a FAISS `IndexFlatIP` store, sparse tokens into
   SQLite FTS5, and metadata into the sources store.

## Retrieval

1. **HyDE (optional)** — if a query looks generic (`tell me about`, short), a
   hypothetical answer passage is generated to improve recall.
2. **Hybrid search** — BM25 (FTS5) and dense (FAISS, inner-product) run in
   parallel.
3. **RRF fusion** — reciprocal-rank fusion merges the two ranked lists and
   normalises scores.
4. **Rerank** — a `cross-encoder/ms-marco-MiniLM-L-6-v2` model rescored the top
   candidates; a source-aware diversification step keeps the answer grounded
   across multiple sources rather than one dominant source.
5. **Generation** — reranked chunks are packed into a groundable prompt and
   streamed to the client with per-stage latency and confidence metadata.

Every query response carries `answer_confidence`, `source_coverage`,
`sources_used`, `retrieved_chunks`, and a latency breakdown so answers are
auditable.
