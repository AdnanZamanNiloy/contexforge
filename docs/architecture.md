# Architecture

ContextForge is a local-first, retrieval-augmented generation (RAG) workspace. It
splits into a FastAPI backend and a React 19 frontend that talk over REST and
Server-Sent Events (SSE).

## Backend layers

- **`app/`** — the FastAPI application: `main.py` (app + lifespan + CORS), route
  handlers, Pydantic schemas, and singleton service wiring in `dependencies.py`.
  Feature modules (`mindmap/`, `model_hub/`, `projects/`, `notes/`, `chat/`,
  `architecture/`, `security/`, `techstack/`, `health/`, `context/`, `sources/`)
  are self-contained packages.
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
ingest:  Source ──► loader ──► chunker ──► embedder ──► FAISS + BM25
                                          │
                                     on-disk cache

query:   question ──► HyDE (optional) ──► embed ──► BM25 ⊕ dense ──► RRF fusion
                                                          │
                                              cross-encoder rerank
                                                          │
                                              prompt assembly ──► LLM ──► SSE
```

HyDE runs **first**, before retrieval: it rewrites the query into a hypothetical
answer passage so the retrievers have something to match on. Fusion happens inside
the hybrid retriever, so it reports a single `retrieve_ms`. The timings returned to
the client are `hyde_ms`, `embed_ms`, `retrieve_ms`, `rerank_ms`, `generate_ms`.

## Feature packages

| Package | Responsibility | Cache |
|---|---|---|
| `mindmap/` | Generate a nested outline from a selection of sources | keyed by selection |
| `notes/` | Write a Markdown note from the same selection | keyed by selection |
| `projects/` | Project library, source membership, tool source | SQLite |
| `chat/` | Per-project sessions; each message stores its own source selection | SQLite |
| `model_hub/` | Provider registry, fallback chains, serving selection, encrypted keys | SQLite |
| `architecture/` `security/` `techstack/` `health/` | Repository analyzers | keyed by content fingerprint |
| `context/` | Token-cost estimator for a selection | none (stateless) |

Mind Map and Note deliberately **share** one notion of a selection — a lone source
keys by its own id, several by a sorted composite key — so both features cache side
by side over the same sources and the client cannot derive the key one way and the
server another.

## Serving model

There is no environment-driven provider chain. `dependencies.get_llm()` returns a
not-configured sentinel until the Model Hub is configured; `apply_serving_configuration()`
then rebuilds the live pipeline and rewires every consumer that captured an LLM at
construction time (HyDE, Mind Map, Note, Architecture).

## Frontend layers

- **`pages/`** — routes (Landing, Projects, Model Hub); the project workspace
  owns the Chat, Mind Map and Note views plus the Studio rail.
- **`components/`** — reusable UI (chat, source header, mind-map canvas, note
  panel, context meter).
- **`hooks/`** — data hooks (`useChat`, `useSources`, `useProjects`, `useChatSessions`).
- **`services/api.js`** — REST client + SSE stream parser; **`lib/sources.jsx`**
  — shared source model, canonical source glyphs and formatters; **`lib/projects.js`**
  — library helpers (sorting, selection filtering, cover assignment).

The frontend is stateless with respect to the index; all index state lives in the
backend (FAISS/BM25/DB). Chat history persists to **SQLite** (`backend/data/chat/chat.db`)
per project, not to `localStorage`.
