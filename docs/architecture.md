# Architecture

ContextForge is a local-first, retrieval-augmented generation (RAG) workspace. It
splits into a FastAPI backend and a React 19 frontend that talk over REST and
Server-Sent Events (SSE).

## Backend layers

- **`app/`** — the FastAPI application: `main.py` (app + lifespan + CORS), route
  handlers, Pydantic schemas, and singleton service wiring in `dependencies.py`.
  Feature modules (`mindmap/`, `repository_intelligence/`) are self-contained
  packages.
- **`core/`** — the engine. Every RAG stage is a small, testable module:
  ingestion loaders, chunkers (text + AST code), embedders, storage (FAISS dense,
  SQLite FTS5 BM25), retrieval (hybrid, RRF fusion, HyDE, cross-encoder rerank),
  generation (multi-provider LLM routing), and processing (clean, dedupe,
  metadata).
- **`core/interfaces/`** — abstract contracts (embedder, LLM, retriever) that let
  providers be swapped without touching the pipeline.
- **`observability/`** — a Langfuse tracing decorator used by the orchestrator.

## Data flow

```
Source ──► loader ──► chunker ──► embedder ──► FAISS + BM25
                                    │             │
                                 cache        hybrid search
                                    │             │
                                      RRF fusion ──► HyDE (optional)
                                            │
                                     cross-encoder rerank
                                            │
                                    LLM generation ──► SSE stream
```

## Frontend layers

- **`pages/`** — routes (Home, Source Explore, Mind Map, Repository
  Intelligence); the repository page owns several tabbed sub-views.
- **`components/`** — reusable UI (chat, source header, mind-map canvas, repo
  CTA).
- **`hooks/`** — data hooks (`useChat`, `useSources`, `useRepository`).
- **`services/api.js`** — REST client + SSE stream parser; **`lib/sources.jsx`**
  — shared source model and formatters.

The frontend is stateless with respect to the index; all state lives in the
backend (FAISS/BM25/DB). Chat history persists to `localStorage` keyed per
source.
