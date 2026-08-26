# ContextForge

**Grounded AI workspace for Retrieval-Augmented Generation.**  
Ingest documents, web pages, and GitHub repositories — then ask questions against your knowledge base with cited evidence, confidence metrics, and streaming answers.

> **Status:** Active development. The core RAG pipeline, Repository Intelligence, and Mind Map features are implemented and tested; see the [Roadmap](#roadmap) for what's next.

---

## Why ContextForge

Most LLM chat tools are disconnected from your actual data. ContextForge is built around a single idea: answers should be **grounded in sources you control**, not just the model's training data.

- **You own your data** — everything runs locally on your hardware. No data leaves your machine except for embedding and LLM API calls.
- **Hybrid retrieval** — BM25 keyword search and dense vector search fused via Reciprocal Rank Fusion, then reranked with a cross-encoder for precision.
- **Multi-provider resilience** — primary LLM (Gemini) with automatic failover to Groq, OpenRouter, Cerebras, or NVIDIA NIM. If one provider is down, the pipeline keeps working.
- **Transparent answers** — every response includes source citations, a per-stage latency breakdown, and server-side confidence metrics so you know *why* the model answered the way it did.

---

## Features

### Source Ingestion

| Type | Format | Loader |
|---|---|---|
| PDF | `.pdf` | `pypdf` |
| Word | `.docx` | `python-docx` |
| Web | URL | `trafilatura` |
| GitHub | Repository URL | GitHub REST API + AST-aware code chunking |
| YouTube | Video URL | Transcript extraction via `youtube-transcript-api` |
| Plain text | `.txt` | Raw text loader |

### Retrieval Pipeline

1. **HyDE expansion** (optional) — generates a hypothetical answer passage to improve retrieval recall
2. **Hybrid search** — BM25 (SQLite FTS5) and dense vector search (FAISS `IndexFlatIP`) run in parallel
3. **Reciprocal Rank Fusion** — merges sparse and dense results into a single ranked list
4. **Cross-encoder reranking** — `cross-encoder/ms-marco-MiniLM-L-6-v2` scores the top candidates for answer relevance
5. **LLM generation** — reranked chunks are fed as context to the LLM, which produces a grounded answer

### Answer Delivery

- **Server-Sent Events (SSE)** — tokens stream to the frontend as they are generated
- **Source citations** — each answer shows which ingested chunks were used, with scores and metadata
- **Confidence metrics** — server-side `answer_confidence`, `source_coverage`, `sources_used`, `retrieved_chunks`
- **Latency breakdown** — per-stage timing (retrieval, rerank, generation)

### Repository Intelligence

For GitHub repositories, ContextForge runs a multi-phase analysis that produces:

- **Architecture graph** — hierarchical decomposition (repo → area → directory → module → file)
- **Dependency graph** — module-level dependency subgraphs with configurable depth
- **Data-flow analysis** — execution and data-flow paths across the repository
- **Git history** — churn, branches, commits, and contributor activity
- **Ownership analysis** — contributor distribution and bus-factor estimation
- **Health scoring** — quantitative dimensions (fanout, churn, complexity, coverage, ownership)
- **Risk assessment** — explainable, weighted risk levels for each module
- **Change impact / blast radius** — impact analysis of a change to a given file or module
- **Interactive Q&A** — ask questions about the repository's architecture and codebase

The ingestion layer indexes a repository from the GitHub API; Repository Intelligence additionally clones the repo for deeper static analysis.

### Mind Map

Generate a visual mind map from any ingested source. The mind map is rendered as an interactive SVG graph with zoom, pan, search, and fullscreen mode.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (React 19 + Vite 8)                │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Chat UI  │  │ Source    │  │ Mind Map     │  │ Repository    │  │
│  │ (SSE)     │  │ Explorer  │  │ Viewer       │  │ Intelligence  │  │
│  └─────┬─────┘  └─────┬─────┘  └──────┬───────┘  └───────┬───────┘  │
└────────┼───────────────┼───────────────┼──────────────────┼──────────┘
         │               │               │                  │
         │     REST / SSE (JSON/event-stream)               │
         │               │               │                  │
┌────────┼───────────────┼───────────────┼──────────────────┼──────────┐
│  FastAPI (Python 3.14+) — Backend API                       │         │
│  ┌──────────────────────────────────────────────────────────┐ │       │
│  │                    Orchestrator                           │ │       │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐  │ │       │
│  │  │ Ingestion│  │ Retrieval│  │ Reranker │  │  LLM    │  │ │       │
│  │  │ Pipeline │  │ Pipeline │  │          │  │ Routing │  │ │       │
│  │  └──────────┘  └──────────┘  └──────────┘  └─────────┘  │ │       │
│  └──────────────────────────────────────────────────────────┘ │       │
│                                                                │     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │     │
│  │  FAISS       │  │  SQLite FTS5 │  │  Embedding Cache     │  │     │
│  │  (dense)     │  │  (BM25)      │  │  (blake2b-keyed)     │  │     │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │     │
│                                                                │     │
│  ┌──────────────────────────────────────────────────────────┐  │     │
│  │  Repository Intelligence Analyzer                         │  │     │
│  │  (git clone → AST parse → graph build → risk scoring)    │  │     │
│  └──────────────────────────────────────────────────────────┘  │     │
│                                                                │     │
│  ┌──────────────────────────────────────────────────────────┐  │     │
│  │  Mind Map Generator                                       │  │     │
│  │  (chunk retrieval → LLM summarization → markdown output)  │  │     │
│  └──────────────────────────────────────────────────────────┘  │     │
└─────────────────────────────────────────────────────────────────────┘

         │               │               │                  │
    ┌────┴────┐    ┌─────┴─────┐    ┌────┴────┐     ┌──────┴──────┐
    │ Voyage  │    │  Google   │    │  Groq   │     │ Langfuse    │
    │  AI     │    │  Gemini   │    │ / Others│     │ (tracing)   │
    │(embed)  │    │  (LLM)    │    │(fallback)│    │             │
    └─────────┘    └───────────┘    └─────────┘     └─────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.14+
- Node.js 22+
- A Voyage AI API key (`VOYAGE_API_KEY`)
- A Google Gemini API key (`GOOGLE_API_KEY`) — primary LLM
- (Optional) Groq API key (`GROQ_API_KEY`) — fallback LLM

### Backend

```bash
git clone https://github.com/AdnanZamanNiloy/ContexForge.git
cd contextforge

python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# Set API keys as environment variables (never commit them):
export VOYAGE_API_KEY="..."
export GOOGLE_API_KEY="..."

uvicorn backend.app.main:app --reload --port 8000
```

> All settings load via `pydantic-settings` from environment variables or a `.env`
> file placed in the `backend/` directory. Secrets are env-only — the defaults in
> `settings.py` are intentionally empty and the app fails loudly when a required
> key is absent.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env    # defaults to http://localhost:8000
npm run dev             # starts on http://localhost:5173
```

### Verify

```bash
curl http://localhost:8000/health
# → {"status":"ok","service":"contextforge"}
```

Open `http://localhost:5173` in your browser.

---

## Configuration

All configuration lives in `backend/app/config/settings.py` (via `pydantic-settings`). Set values via environment variables or a `.env` file in the `backend/` directory.

### Required

| Variable | Description |
|---|---|
| `VOYAGE_API_KEY` | Embedding API key |
| `GOOGLE_API_KEY` | Primary LLM (Gemini) API key |

### Optional

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | — | Fallback LLM provider |
| `OPENROUTER_API_KEY` | — | Fallback aggregator |
| `CEREBRAS_API_KEY` | — | Fallback provider |
| `NVIDIA_API_KEY` | — | Fallback provider |
| `LANGFUSE_PUBLIC_KEY` | — | Langfuse tracing (public key) |
| `LANGFUSE_SECRET_KEY` | — | Langfuse tracing (secret key) |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse host |
| `GEMINI_MODEL` | `gemini-flash-latest` | Gemini model ID |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Groq model ID |
| `VOYAGE_MODEL` | `voyage-3-lite` | Voyage embedding model |
| `CHUNK_SIZE` | `512` | Text chunk size (tokens) |
| `CHUNK_OVERLAP` | `50` | Chunk overlap (tokens) |
| `TOP_K_RETRIEVAL` | `20` | Chunks retrieved per query |
| `TOP_K_RERANK` | `5` | Chunks passed to the LLM |
| `USE_HYDE` | `false` | Enable HyDE query expansion |
| `FAISS_INDEX_PATH` | `data/vector_store/index.faiss` | FAISS index path |
| `ALLOWED_ORIGINS` | `["http://localhost:5173"]` | CORS allowed origins |
| `REPO_MAX_FILES` | `800` | Max files for repo analysis |
| `LOG_LEVEL` | `INFO` | Logging level |

### Frontend

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend API URL |

---

## Project Structure

```
contextforge/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI entry point, lifespan, CORS, routers
│   │   ├── dependencies.py          # Singleton services (orchestrator, ingest, query)
│   │   ├── config/
│   │   │   ├── settings.py          # All app configuration (pydantic-settings)
│   │   │   └── settings_example.py  # Empty template (use env vars instead)
│   │   ├── routes/                  # API route handlers
│   │   │   ├── ingest.py            # POST /ingest/source, /ingest/file, DELETE, GET /ingest/sources
│   │   │   ├── github.py            # POST /github/ingest
│   │   │   └── query.py             # POST /query, POST /query/stream
│   │   ├── schemas/                 # Pydantic request/response models
│   │   ├── services/
│   │   │   ├── ingest_service.py    # Ingestion orchestration
│   │   │   └── query_service.py     # Query + SSE streaming
│   │   ├── mindmap/                 # Mind map generation (routes, service, storage)
│   │   └── repository_intelligence/ # Repo analysis (graph, risk, git, dependencies, etc.)
│   ├── core/
│   │   ├── orchestrator.py          # Central coordinator for the RAG pipeline
│   │   ├── ingestion/               # Loaders: base, pdf, docx, text, web, github, youtube
│   │   ├── chunking/                # Text chunker (tiktoken) + code chunker (AST)
│   │   ├── embedding/               # Voyage embedder + BGE fallback embedder
│   │   ├── retrieval/               # BM25, dense, hybrid, RRF fusion, HyDE, reranker
│   │   ├── generation/              # LLM abstraction + providers (Gemini, Groq, etc.)
│   │   ├── storage/                 # FAISS store, BM25 index, embedding cache
│   │   ├── processing/              # Cleaner, deduplicator, metadata extractor
│   │   └── interfaces/              # Abstract contracts (embedder, LLM, retriever)
│   ├── observability/tracer.py      # Langfuse tracing decorator
│   └── tests/                       # Unit + integration tests
│       ├── unit/                    # Test modules for each pipeline stage
│       └── integration/             # API-level integration tests
├── frontend/
│   ├── src/
│   │   ├── App.jsx                  # Routes (/ , /sources/:id, /mindmap/:id, /repository)
│   │   ├── pages/                   # Page components (Home, SourceExplore, MindMap, Repository)
│   │   ├── components/              # Reusable UI (ChatBox, MindMapCanvas, SourceHeader, etc.)
│   │   ├── hooks/                   # useChat, useSources, useRepository
│   │   ├── services/api.js          # API client (REST + SSE streaming)
│   │   ├── lib/sources.jsx          # Source helper utilities
│   │   └── styles/main.css          # Tailwind CSS v4 + custom styles
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── docs/                            # Architecture and pipeline notes
├── pyproject.toml
└── README.md
```

---

## Technology Stack

### Backend

| Component | Technology |
|---|---|
| Framework | FastAPI |
| Runtime | Python 3.14+ |
| Vector store | FAISS (CPU, `IndexFlatIP`) |
| Sparse index | SQLite FTS5 |
| Embeddings | Voyage AI (`voyage-3-lite`) |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| LLM (primary) | Google Gemini (`gemini-flash-latest`) |
| LLM (fallback) | Groq, OpenRouter, Cerebras, NVIDIA NIM |
| Tracing | Langfuse (optional) |

### Frontend

| Component | Technology |
|---|---|
| Framework | React 19 |
| Build tool | Vite 8 |
| Styling | Tailwind CSS v4 |
| Routing | React Router 7 |
| Animation | Framer Motion |
| Mind map | `@xiangfa/mindmap` |
| Markdown | `react-markdown` + `remark-gfm` |

---

## Development

### Running tests

The suite uses `pytest` (install it in the backend venv with `pip install pytest`).

```bash
# Backend unit tests
cd backend && python -m pytest tests/unit -v

# Integration tests
cd backend && python -m pytest tests/integration -v

# All tests
cd backend && python -m pytest tests/ -v
```

### Building the frontend

```bash
cd frontend
npm run build     # production build into frontend/dist
npm run preview   # preview the production build
```

---

## API Overview

### Health

```
GET /health → {"status": "ok", "service": "contextforge"}
```

### Ingestion

```
POST /ingest/source          — Ingest a URL or GitHub repo
POST /ingest/file            — Upload a PDF or DOCX file
DELETE /ingest/source/{id}   — Remove a source and its chunks
GET  /ingest/sources         — List all ingested sources
DELETE /ingest/clear         — Wipe the entire knowledge base
```

### Query

```
POST /query          — Answer a question (returns JSON with sources + confidence)
POST /query/stream   — Stream answer tokens via SSE
```

### Repository Intelligence

```
POST   /repository/analyze?repo_url=...        — Start an analysis (background)
GET    /repository/latest?repo_url=...         — Latest completed analysis for a URL
GET    /repository/{id}                        — Full analysis bundle
GET    /repository/{id}/status                 — Poll analysis status
GET    /repository/{id}/architecture           — Architecture graph
GET    /repository/{id}/dependencies?selected=&depth= — Dependency subgraph
GET    /repository/{id}/data-flow              — Data flow graph
GET    /repository/{id}/git-history?range=     — Git churn and commits
GET    /repository/{id}/ownership              — Contributor and bus-factor analysis
GET    /repository/{id}/health                 — Health scores
GET    /repository/{id}/repository             — Repository header metadata
GET    /repository/{id}/risk-explanations      — Risk level descriptions
GET    /repository/{id}/change-impact?path=    — Blast radius of a change
GET    /repository/{id}/node?path=             — Node / module inspector
POST   /repository/{id}/ask                    — Interactive Q&A about the repo
POST   /repository/{id}/reanalyze              — Re-run analysis
```

### Mind Map

```
POST /mindmap/generate   — Generate or fetch cached mind map for a source
GET  /mindmap/{source_id} — Fetch a previously generated mind map
```

---

## Configuration Reference

All settings are defined in `backend/app/config/settings.py`. Key categories:

- **API keys** — `VOYAGE_API_KEY`, `GOOGLE_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `CEREBRAS_API_KEY`, `NVIDIA_API_KEY`
- **Model selection** — `GEMINI_MODEL`, `GROQ_MODEL`, `VOYAGE_MODEL`, `RERANK_MODEL`
- **Pipeline tuning** — `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K_RETRIEVAL`, `TOP_K_RERANK`, `USE_HYDE`
- **Repository analysis** — `REPO_MAX_FILES`, `REPO_CLONE_TIMEOUT`, `REPO_GIT_HISTORY_DAYS`
- **Risk scoring weights** — `RISK_FANOUT_WEIGHT`, `RISK_CHURN_WEIGHT`, `RISK_COMPLEXITY_WEIGHT`, `RISK_COVERAGE_WEIGHT`, `RISK_OWNERSHIP_WEIGHT`
- **Paths** — `FAISS_INDEX_PATH`, `BM25_DB_PATH`, `CACHE_PATH`, `UPLOAD_DIR`, `REPO_ANALYSIS_DIR`, `MINDMAP_DIR`

---

## Roadmap

- [ ] Docker Compose deployment with backend + frontend services
- [ ] User authentication and multi-user workspaces
- [ ] Document-level metadata search and filtering
- [ ] Batch ingestion for large document sets
- [ ] Export and share mind maps
- [ ] REST API client SDK for programmatic access
- [ ] CI/CD pipeline with GitHub Actions

---

## Contributing

Contributions are welcome. Please open an issue first to discuss the change you'd like to make.

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Make your changes
4. Run the tests
5. Commit and push
6. Open a pull request

---

## License

A license has not yet been selected for this project. Until a `LICENSE` file is added, all rights are reserved. Maintainers should choose and add an open-source license before public distribution.

---

## Acknowledgments

- [Langfuse](https://langfuse.com) for open-source observability
- [FAISS](https://github.com/facebookresearch/faiss) by Meta Research for vector search
- [Voyage AI](https://www.voyageai.com) for embedding models
- [Trafilatura](https://github.com/adbar/trafilatura) for web content extraction