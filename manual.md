# ContextForge — Complete Developer Documentation

> **Version:** 0.1.0 | **Status:** Active Development | **Target Hardware:** Intel i5-1240P, 8 GB RAM, CPU-only

---

## Table of Contents

1. [Project Purpose and Objectives](#1-project-purpose-and-objectives)
2. [System Architecture](#2-system-architecture)
3. [Architecture Diagram](#3-architecture-diagram)
4. [System Workflow Diagram](#4-system-workflow-diagram)
5. [Folder Structure](#5-folder-structure)
6. [Technology Stack](#6-technology-stack)
7. [AI/ML Models and Inference Pipeline](#7-aiml-models-and-inference-pipeline)
8. [API Endpoints](#8-api-endpoints)
9. [Database Schema and Storage](#9-database-schema-and-storage)
10. [Authentication, Authorization, and Security](#10-authentication-authorization-and-security)
11. [Core Business Logic](#11-core-business-logic)
12. [Request/Data Flow](#12-requestdata-flow)
13. [External Services and Libraries](#13-external-services-and-libraries)
14. [Environment Configuration](#14-environment-configuration)
15. [Deployment and Scalability](#15-deployment-and-scalability)
16. [Design Patterns and Optimizations](#16-design-patterns-and-optimizations)
17. [Testing Strategy](#17-testing-strategy)
18. [Strengths, Weaknesses, and Improvements](#18-strengths-weaknesses-and-improvements)

---

## 1. Project Purpose and Objectives

ContextForge is a **grounded AI workspace for Retrieval-Augmented Generation (RAG)**. It enables users to:

- **Upload documents** (PDF, DOCX) into a searchable knowledge base
- **Ingest web pages** by pasting URLs, extracting content via trafilatura/Playwright
- **Connect GitHub repositories** by ingesting source code with AST-aware chunking
- **Chat with an AI assistant** that answers questions grounded in the ingested sources, providing cited evidence and server-side confidence metrics

### Core Objectives

| Objective | How It's Achieved |
|---|---|
| Grounded answers | Hybrid retrieval (BM25 + dense vectors) with cross-encoder reranking |
| Multi-source ingestion | Pluggable loader architecture (PDF, DOCX, web, GitHub, text) |
| Production readiness | Graceful degradation, fallback LLMs, streaming SSE, health checks |
| Modest hardware | CPU-only FAISS, lazy-loaded models, disk-based caching |
| Transparency | Server-side confidence metrics, evidence panel, latency breakdown |

---

## 2. System Architecture

ContextForge follows a **two-tier client-server architecture**:

| Layer | Technology | Responsibility |
|---|---|---|
| **Frontend** | React 19 + Vite 8 + Tailwind CSS v4 | UI rendering, SSE streaming, source management |
| **Backend** | FastAPI (Python 3.14+) | REST API, RAG pipeline, document processing |
| **Vector Store** | FAISS (IndexFlatIP) | Dense semantic search on L2-normalized embeddings |
| **Sparse Index** | SQLite FTS5 | Full-text keyword search (BM25) |
| **Embedding API** | Voyage AI (`voyage-3-lite`) | Text-to-vector conversion with disk cache |
| **Primary LLM** | Google Gemini (`gemini-2.0-flash`) | Answer generation and HyDE expansion |
| **Fallback LLM** | Groq (`llama-3.3-70b-versatile`) | Failover when Gemini is unavailable |
| **Reranker** | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Cross-encoder scoring for precision retrieval |
| **Observability** | Langfuse (optional) | Distributed tracing across pipeline stages |

### How Components Interact

1. The **frontend** sends user queries and file uploads to the **backend** via REST/SSE
2. The **backend** loads documents through source-specific **loaders**, preprocesses them (clean, deduplicate, extract metadata), and **chunks** them
3. Chunks are **embedded** via Voyage AI API (with disk caching) and stored in both **FAISS** (dense) and **SQLite FTS5** (sparse)
4. On query, the backend performs **HyDE expansion**, embeds the query, runs **hybrid retrieval** (BM25 + dense in parallel), **fuses** results via Reciprocal Rank Fusion, and **reranks** with a cross-encoder
5. The reranked chunks are fed to the **LLM** (Gemini primary, Groq fallback) which generates a grounded answer
6. Results stream back to the frontend via **SSE** (Server-Sent Events) with sources, latency, and confidence metadata

---

## 3. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React 19)                        │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │ Sidebar   │  │  ChatBox     │  │ SourceViewer │  │  Modal    │  │
│  │ (Sources) │  │  (Messages)  │  │ (Evidence)   │  │ (Upload)  │  │
│  └─────┬────┘  └──────┬───────┘  └──────┬───────┘  └─────┬─────┘  │
│        │              │                  │                │         │
│        └──────────────┴──────────────────┴────────────────┘         │
│                              │                                      │
│                    api.js (HTTP/SSE)                                │
└──────────────────────────────┼──────────────────────────────────────┘
                               │  REST + SSE
┌──────────────────────────────┼──────────────────────────────────────┐
│                         BACKEND (FastAPI)                           │
│                              │                                      │
│  ┌───────────────────────────┴──────────────────────────────────┐   │
│  │                    Route Layer                                │   │
│  │  /ingest/source  /ingest/file  /github/ingest  /query        │   │
│  │  /query/stream   /health                                      │   │
│  └───────────────────────────┬──────────────────────────────────┘   │
│                              │                                      │
│  ┌───────────────────────────┴──────────────────────────────────┐   │
│  │                  Service Layer                                │   │
│  │  IngestService          QueryService                          │   │
│  └───────────┬───────────────────────────┬──────────────────────┘   │
│              │                           │                          │
│  ┌───────────┴───────────┐  ┌────────────┴──────────────────────┐   │
│  │  INGESTION PIPELINE   │  │     QUERY PIPELINE                │   │
│  │                       │  │                                    │   │
│  │  Loader → Clean →     │  │  HyDE → Embed → Hybrid Retrieve → │   │
│  │  Metadata → Dedup →   │  │  RRF Fusion → Rerank → LLM        │   │
│  │  Chunk → Embed →      │  │                                    │   │
│  │  Index (FAISS+FTS5)   │  │                                    │   │
│  └───────────┬───────────┘  └────────────┬──────────────────────┘   │
│              │                           │                          │
│  ┌───────────┴───────────────────────────┴──────────────────────┐   │
│  │                    Storage Layer                              │   │
│  │  FaissStore (IndexFlatIP)    BM25Index (SQLite FTS5)         │   │
│  │  EmbeddingCache (JSON disk)                                   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              External API Integrations                       │   │
│  │  Voyage AI (embeddings)  Gemini (LLM)  Groq (fallback LLM)  │   │
│  │  GitHub API (repo ingest)  Langfuse (tracing)               │   │
│  └─────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

---

## 4. System Workflow Diagram

### Ingestion Workflow

```
User Action (upload PDF / paste URL / add GitHub repo)
        │
        ▼
┌──────────────────┐
│  POST /ingest/   │  Route validates request via Pydantic schema
│  source | file   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  IngestService   │  Selects loader by source_type
│  .ingest()       │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Loader.load()   │  Source-specific extraction:
│                  │  - PDFLoader: pypdf
│                  │  - DocxLoader: python-docx
│                  │  - WebLoader: httpx + trafilatura (+Playwright)
│                  │  - GitHubLoader: GitHub REST API + raw fetch
│                  │  - TextLoader: direct string
└────────┬─────────┘
         │  List[Document]
         ▼
┌──────────────────┐
│  TextCleaner     │  NFC normalization, URL/email removal,
│  .clean()        │  boilerplate detection, separator cleanup
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ MetadataExtractor│  spaCy NER + keyword extraction + title detection
│  .extract()      │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Deduplicator    │  blake2b fingerprinting, thread-safe seen-set
│  .deduplicate()  │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Chunker         │  TextChunker: RecursiveCharacterTextSplitter (tiktoken)
│  .chunk_documents│  CodeChunker: AST-based Python symbol extraction
└────────┬─────────┘
         │  List[Chunk]
         ▼
┌──────────────────┐
│ VoyageEmbedder   │  Batch embed via Voyage AI API (with disk cache)
│ .embed_texts()   │  VOYAGE_BATCH_SIZE=128, retry with backoff
└────────┬─────────┘
         │  List[np.ndarray]
         ▼
┌──────────────────┐  ┌──────────────────┐
│   FaissStore     │  │   BM25Index      │
│   .add()         │  │   .add()         │
│  IndexFlatIP +   │  │  SQLite FTS5 +   │
│  metadata JSON   │  │  porter tokenizer│
└──────────────────┘  └──────────────────┘
         │
         ▼
   IngestResponse { source_id, chunks_indexed }
```

### Query Workflow

```
User sends question
        │
        ▼
┌──────────────────┐
│  POST /query     │  or POST /query/stream (SSE)
│  or /query/stream│
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  QueryService    │
│  .query()        │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────────┐
│ Orchestrator.retrieve_context()           │
│                                          │
│  1. HyDE Expansion (optional)            │
│     LLM generates hypothetical passage   │
│                                          │
│  2. Embed Query                          │
│     VoyageEmbedder.embed_single()        │
│                                          │
│  3. Hybrid Retrieve (parallel)           │
│     BM25 Retriever → SQLite FTS5         │
│     Dense Retriever → FAISS              │
│     RRFFusion.fuse() (k=60)             │
│                                          │
│  4. Reranker                             │
│     Cross-encoder scoring                │
│     Sigmoid normalization                │
│     Returns (chunks, mean_confidence)    │
│                                          │
│  5. ConfidenceMetrics                    │
│     Coverage: Excellent/Strong/          │
│       Moderate/Low/Weak                  │
└──────────────────┬───────────────────────┘
                   │
                   ▼
┌──────────────────┐
│ PromptBuilder    │  Builds system + user prompt with chunk context
│ .build()         │  ANSWER_SYSTEM_PROMPT (9 strict rules)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ FallbackLLM      │  Primary: Gemini → Fallback: Groq
│ .generate()/.stream()
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ SSE Stream Events│
│ [token]          │  Individual answer tokens
│ [SOURCES]        │  Retrieved source chunks
│ [LATENCY]        │  Per-stage timing breakdown
│ [CONFIDENCE]     │  Server-side confidence metrics
│ [DONE]           │  Stream terminator
└──────────────────┘
```

---

## 5. Folder Structure

```
contextforge/
├── backend/                          # Python backend (FastAPI)
│   ├── __init__.py
│   ├── .env                          # Runtime config (API keys, feature flags)
│   ├── requirements.txt              # Python dependencies
│   ├── README.md                     # Backend description
│   │
│   ├── app/                          # Application layer (FastAPI)
│   │   ├── __init__.py
│   │   ├── main.py                   # App factory, lifespan, CORS, health endpoint
│   │   ├── dependencies.py           # DI wiring: lru_cache singletons
│   │   │
│   │   ├── config/
│   │   │   ├── __init__.py
│   │   │   └── settings.py           # Pydantic Settings: all config in one class
│   │   │
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── github.py             # GithubIngestRequest
│   │   │   ├── ingest.py             # IngestRequest, IngestResponse
│   │   │   └── query.py              # QueryRequest, QueryResponse, SourceSummary,
│   │   │                             #   ConfidenceMetrics
│   │   │
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── ingest.py             # POST /ingest/source, POST /ingest/file
│   │   │   ├── github.py             # POST /github/ingest
│   │   │   └── query.py             # POST /query, POST /query/stream
│   │   │
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── ingest_service.py     # Orchestrates loader + pipeline
│   │       └── query_service.py      # Orchestrates retrieval + generation + streaming
│   │
│   ├── core/                         # Domain/pipeline layer (framework-agnostic)
│   │   ├── __init__.py
│   │   ├── types.py                  # Frozen dataclasses: Document, Chunk, etc.
│   │   ├── orchestrator.py           # Central coordinator for ingest + retrieve + generate
│   │   ├── pipeline.py               # Deprecated alias → Orchestrator
│   │   │
│   │   ├── interfaces/
│   │   │   ├── __init__.py
│   │   │   ├── embedder.py           # ABC Embedder
│   │   │   ├── llm.py                # ABC LLM
│   │   │   └── retriever.py          # ABC Retriever
│   │   │
│   │   ├── ingestion/
│   │   │   ├── __init__.py
│   │   │   ├── base_loader.py        # ABC BaseLoader
│   │   │   ├── text_loader.py        # Raw text ingestion
│   │   │   ├── pdf_loader.py         # PDF extraction (pypdf)
│   │   │   ├── docx_loader.py        # DOCX extraction (python-docx)
│   │   │   ├── web_loader.py         # Web page extraction (httpx + trafilatura + Playwright)
│   │   │   └── github_loader.py      # GitHub repo traversal (GitHub REST API)
│   │   │
│   │   ├── chunking/
│   │   │   ├── __init__.py
│   │   │   ├── text_chunker.py       # RecursiveCharacterTextSplitter + tiktoken
│   │   │   └── code_chunker.py       # AST-based Python symbol extraction
│   │   │
│   │   ├── embedding/
│   │   │   ├── __init__.py
│   │   │   ├── voyage_embedder.py    # Voyage AI API + disk cache
│   │   │   └── bge_embedder.py       # Local BAAI/bge-base-en-v1.5 (alternative)
│   │   │
│   │   ├── retrieval/
│   │   │   ├── __init__.py
│   │   │   ├── dense_retriever.py    # FAISS cosine similarity search
│   │   │   ├── bm25_retriever.py     # SQLite FTS5 full-text search
│   │   │   ├── hybrid_retriever.py   # Parallel BM25 + Dense with graceful degradation
│   │   │   ├── rrf_fusion.py         # Reciprocal Rank Fusion (k=60)
│   │   │   ├── reranker.py           # Cross-encoder reranking (ms-marco-MiniLM)
│   │   │   └── hyde.py               # HyDE query expansion via LLM
│   │   │
│   │   ├── generation/
│   │   │   ├── __init__.py
│   │   │   ├── base_llm.py           # Abstract base with validation + logging
│   │   │   ├── gemini_llm.py         # Google Gemini REST API (gemini-2.0-flash)
│   │   │   ├── groq_llm.py           # Groq OpenAI-compatible API
│   │   │   ├── fallback_llm.py       # Primary → Fallback with mid-stream safety
│   │   │   └── prompt_builder.py     # Builds answer/general prompts
│   │   │
│   │   ├── processing/
│   │   │   ├── __init__.py
│   │   │   ├── cleaner.py            # Text normalization, URL/email removal
│   │   │   ├── deduplicator.py       # blake2b fingerprint dedup
│   │   │   └── metadata_extractor.py # spaCy NER + keywords + title detection
│   │   │
│   │   └── storage/
│   │       ├── __init__.py
│   │       ├── faiss_store.py        # FAISS IndexFlatIP + metadata persistence
│   │       └── bm25_index.py         # SQLite FTS5 with WAL mode
│   │
│   ├── observability/
│   │   ├── __init__.py
│   │   └── tracer.py                 # @observe decorator (Langfuse or no-op)
│   │
│   ├── data/                         # Runtime data (auto-created)
│   │   ├── bm25/bm25.db              # SQLite FTS5 database
│   │   ├── cache/embeddings.json     # Voyage embedding cache
│   │   ├── vector_store/index.faiss  # FAISS index file
│   │   ├── uploads/                  # File upload staging
│   │   └── fixtures/                 # Test fixtures (sample.md, sample.py, sample.txt)
│   │
│   └── tests/
│       ├── __init__.py
│       ├── unit/
│       │   ├── __init__.py
│       │   ├── test_chunkers.py
│       │   ├── test_hyde.py
│       │   ├── test_reranker.py
│       │   ├── test_embedding_cache.py
│       │   └── test_storage_and_retrieval.py
│       └── integration/
│           ├── __init__.py
│           └── test_api.py
│
├── frontend/                         # React frontend
│   ├── index.html                    # Entry point (Google Fonts, root div)
│   ├── package.json                  # Dependencies and scripts
│   ├── package-lock.json
│   ├── vite.config.js                # Vite + React + Tailwind plugins
│   ├── .env.example                  # VITE_API_BASE_URL=http://localhost:8000
│   │
│   ├── public/
│   │   ├── logos/project_logo.png
│   │   ├── favicon-*.png
│   │   ├── apple-touch-icon.png
│   │   └── favicon.ico
│   │
│   └── src/
│       ├── main.jsx                  # React 19 root mount
│       ├── App.jsx                   # Thin wrapper → Home
│       ├── styles/main.css           # Global CSS (1192 lines, design tokens)
│       │
│       ├── pages/
│       │   └── Home.jsx              # Main orchestrator (3-column layout, modal)
│       │
│       ├── components/
│       │   ├── ChatBox.jsx           # Chat interface (messages, input, chips)
│       │   ├── MessageBubble.jsx     # Individual message renderer
│       │   ├── SourceViewer.jsx      # Evidence/retrieval panel with confidence chart
│       │   ├── RepoInput.jsx         # GitHub repo input (orphaned/unused)
│       │   └── UploadPanel.jsx       # File upload panel (orphaned/unused)
│       │
│       ├── hooks/
│       │   └── useChat.js            # Chat lifecycle hook (streaming, abort, retry)
│       │
│       └── services/
│           └── api.js                # HTTP/SSE client layer
│
├── scripts/
│   ├── query_cli.py                  # CLI query stub (not implemented)
│   └── ingest_repo.py                # CLI repo ingest stub (not implemented)
│
├── docs/
│   ├── architecture.md               # Placeholder
│   ├── pipeline.md                   # Placeholder
│   └── evaluation.md                 # Placeholder (mentions HyDE)
│
├── docker-compose.yml                # Empty scaffold
├── Makefile                          # Minimal (help target only)
├── pyproject.toml                    # Python 3.14+, setuptools build
├── README.md                         # Project overview
└── .gitignore
```

---

## 6. Technology Stack

### Backend

| Technology | Version | Why Chosen |
|---|---|---|
| **Python** | 3.14+ | Modern async/await, typing support, mature ML ecosystem |
| **FastAPI** | >=0.115 | High-performance async web framework with automatic OpenAPI docs |
| **Uvicorn** | >=0.30 | ASGI server optimized for FastAPI |
| **Pydantic** | >=2.8 | Data validation, settings management, schema generation |
| **Pydantic Settings** | >=2.4 | `.env` file loading, typed configuration |
| **FAISS** | >=1.8 (cpu) | Facebook's vector similarity search, optimized for CPU-only |
| **SQLite FTS5** | built-in | Zero-dependency full-text search with BM25 ranking |
| **Voyage AI** | REST API | High-quality embeddings with generous free tier (`voyage-3-lite`) |
| **Google Gemini** | REST API | Fast, capable LLM for answer generation (`gemini-2.0-flash`) |
| **Groq** | REST API | Ultra-low-latency inference as fallback (`llama-3.3-70b-versatile`) |
| **sentence-transformers** | >=3.1 | Cross-encoder reranker (`ms-marco-MiniLM-L-6-v2`) |
| **LangChain Text Splitters** | >=0.3 | `RecursiveCharacterTextSplitter` with tiktoken tokenizer |
| **tiktoken** | >=0.7 | OpenAI's fast BPE tokenizer for accurate chunk sizing |
| **pypdf** | >=4.3 | PDF text extraction |
| **python-docx** | >=1.1 | DOCX text extraction |
| **trafilatura** | >=1.12 | Web page content extraction (main content, no boilerplate) |
| **httpx** | >=0.27 | Async HTTP client for API calls |
| **Langfuse** | >=2.36 | LLM observability and tracing (optional, degrades to no-op) |
| **spaCy** | (transitive) | NER and keyword extraction for metadata |
| **NumPy** | >=1.26 | Vector operations for FAISS |

### Frontend

| Technology | Version | Why Chosen |
|---|---|---|
| **React** | 19.x | Component-based UI, concurrent features, wide ecosystem |
| **Vite** | 8.x | Fast HMR, ESM-native dev server, optimized builds |
| **Tailwind CSS** | 4.x | Utility-first CSS, rapid styling, CSS-first config in v4 |
| **Framer Motion** | 12.x | Smooth animations for messages, modals, chips |
| **Google Fonts** | - | Space Grotesk (UI) + Space Mono (monospace counts/badges) |

---

## 7. AI/ML Models and Inference Pipeline

### Models Used

| Model | Type | Purpose | Location |
|---|---|---|---|
| `voyage-3-lite` | Embedding | Text-to-vector (1024-dim) | `core/embedding/voyage_embedder.py` |
| `gemini-2.0-flash` | Generative LLM | Primary answer generation + HyDE expansion | `core/generation/gemini_llm.py` |
| `llama-3.3-70b-versatile` | Generative LLM | Fallback answer generation | `core/generation/groq_llm.py` |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | Reranker | Cross-encoder relevance scoring | `core/retrieval/reranker.py` |
| `en_core_web_sm` | NER | Named entity extraction for metadata | `core/processing/metadata_extractor.py` |
| `BAAI/bge-base-en-v1.5` | Embedding (alt) | Local alternative to Voyage (optional) | `core/embedding/bge_embedder.py` |

### Preprocessing Pipeline

All preprocessing is handled by `core/processing/`:

1. **TextCleaner** (`cleaner.py`):
   - NFKC Unicode normalization
   - URL and email removal
   - Page number removal
   - Separator/boilerplate detection (lines repeated 2+ times)
   - Punctuation cluster cleanup
   - Blank line normalization

2. **MetadataExtractor** (`metadata_extractor.py`):
   - Title detection (first `#` heading or first line)
   - Top-N keyword extraction (stopword-filtered frequency analysis)
   - Named entity recognition via spaCy `en_core_web_sm` (with regex fallback)
   - Character count

3. **Deduplicator** (`deduplicator.py`):
   - blake2b fingerprint of NFC-normalized text
   - Thread-safe `seen` set with `reset()` support
   - Exact-match deduplication

### Chunking

| Chunker | File | Strategy |
|---|---|---|
| `TextChunker` | `core/chunking/text_chunker.py` | `RecursiveCharacterTextSplitter` with tiktoken `cl100k_base`, `chunk_size=512`, `chunk_overlap=50` |
| `CodeChunker` | `core/chunking/code_chunker.py` | Python AST parsing: extracts `FunctionDef`, `AsyncFunctionDef`, `ClassDef` as individual chunks; falls back to `TextChunker` for non-Python or parse failures |

### Embedding

**VoyageEmbedder** (`core/embedding/voyage_embedder.py`):
- API: `https://api.voyageai.com/v1/embeddings`
- Model: `voyage-3-lite`
- Batch size: 128 (`VOYAGE_BATCH_SIZE`)
- Caching: Disk-based JSON with blake2b keys, async lock, dirty-flag lazy save
- Retry: Exponential backoff (4 attempts, retryable on 429, 500, 502, 503, 504)

### Retrieval

1. **HyDE Query Expansion** (`core/retrieval/hyde.py`):
   - Calls LLM to generate a hypothetical document passage that would answer the question
   - Uses the hypothetical passage as the query embedding instead of the raw question
   - Controlled by `USE_HYDE=true` setting

2. **Hybrid Retrieval** (`core/retrieval/hybrid_retriever.py`):
   - Runs BM25 and Dense retrieval **in parallel** via `asyncio.gather(return_exceptions=True)`
   - Graceful degradation: if one leg fails, the other continues

3. **BM25 Retrieval** (`core/retrieval/bm25_retriever.py` -> `core/storage/bm25_index.py`):
   - SQLite FTS5 with `porter unicode61` tokenizer
   - WAL mode, 128MB mmap
   - Top-k candidates from FTS5 query

4. **Dense Retrieval** (`core/retrieval/dense_retriever.py` -> `core/storage/faiss_store.py`):
   - FAISS `IndexFlatIP` (inner product on L2-normalized vectors = cosine similarity)
   - Top-k nearest neighbors

5. **Reciprocal Rank Fusion** (`core/retrieval/rrf_fusion.py`):
   - Merges BM25 and Dense results
   - Formula: `score = sum(1/(k + rank))` where `k=60`

6. **Reranking** (`core/retrieval/reranker.py`):
   - `CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")` (lazy-loaded)
   - Sigmoid normalization of raw logits
   - Returns top-k chunks with mean confidence score (floored at 0.35)

### Generation

**FallbackLLM** (`core/generation/fallback_llm.py`):
- Primary: `GeminiLLM` (Google Gemini `gemini-2.0-flash`)
- Fallback: `GroqLLM` (Groq `llama-3.3-70b-versatile`)
- Falls back on: `OSError`, `TimeoutError`, `RuntimeError`
- Streaming safety: only falls back if failure occurs **before** first token is yielded

**PromptBuilder** (`core/generation/prompt_builder.py`):
- Two templates:
  - `_ANSWER_TEMPLATE`: Context + question (when chunks are found)
  - `_GENERAL_TEMPLATE`: Question-only (when no chunks found)
- Deduplicates chunks, caps at `MAX_CHUNKS=20`
- System prompts: `ANSWER_SYSTEM_PROMPT` (9 strict rules) and `GENERAL_SYSTEM_PROMPT`

---

## 8. API Endpoints

### Base URL: `http://localhost:8000`

| Method | Path | Request | Response | Purpose |
|---|---|---|---|---|
| `GET` | `/health` | - | `{"status": "ok", "service": "contextforge"}` | Liveness probe |
| `POST` | `/ingest/source` | `IngestRequest` (JSON) | `IngestResponse` | Ingest URL or raw text |
| `POST` | `/ingest/file` | `source_type` (query) + `UploadFile` | `IngestResponse` | Upload PDF/DOCX (50 MB limit) |
| `POST` | `/github/ingest` | `GithubIngestRequest` (JSON) | `IngestResponse` | Ingest GitHub repo |
| `POST` | `/query` | `QueryRequest` (JSON) | `QueryResponse` | Non-streaming RAG answer |
| `POST` | `/query/stream` | `QueryRequest` (JSON) | `StreamingResponse` (SSE) | Streaming RAG answer |

### Request/Response Schemas

**IngestRequest** (`app/schemas/ingest.py`):
```python
source_type: Literal["pdf", "docx", "web", "github", "text"]
source: str  # URL, repo URL, or raw text
metadata: dict[str, Any] | None
```

**GithubIngestRequest** (`app/schemas/github.py`):
```python
repo_url: str  # Must match https://github.com/owner/repo
branch: str | None
```

**QueryRequest** (`app/schemas/query.py`):
```python
question: str  # Non-blank
top_k_retrieval: int | None  # 1-200
top_k_rerank: int | None     # 1-20
use_hyde: bool | None
```

**QueryResponse** (`app/schemas/query.py`):
```python
answer: str
sources: list[SourceSummary]
latency_ms: dict[str, float]
confidence: ConfidenceMetrics | None
```

**ConfidenceMetrics** (`app/schemas/query.py`):
```python
answer_confidence: float  # [0.0, 1.0]
source_coverage: Literal["Excellent", "Strong", "Moderate", "Low", "Weak"]
sources_used: int
retrieved_chunks: int
```

### SSE Stream Event Format

```
data: <token>\n\n                          # Individual answer tokens
data: [SOURCES] <json-array>\n\n           # Retrieved source chunks
data: [LATENCY] <json-object>\n\n         # Per-stage timing (ms)
data: [CONFIDENCE] <json-object>\n\n      # Server-side confidence
data: [DONE]\n\n                           # Stream terminator
data: [ERROR] <message>\n\n               # Error event
```

---

## 9. Database Schema and Storage

### FAISS Index (`data/vector_store/index.faiss`)

- **Type:** `IndexFlatIP` (inner product / cosine similarity on L2-normalized vectors)
- **Dimensions:** 1024 (matching `voyage-3-lite` output)
- **Metadata:** Stored alongside in `data/vector_store/chunk_metadata.json`
- **Persistence:** Auto-saved on add, lazy-loaded on startup
- **Thread safety:** Async lock for concurrent access

### SQLite FTS5 (`data/bm25/bm25.db`)

- **Engine:** FTS5 with `porter unicode61` tokenizer
- **WAL mode:** Write-ahead logging for concurrent reads
- **mmap_size:** 128MB for performance
- **Schema:** FTS5 virtual table storing chunk text with source metadata
- **Duplicate detection:** On insert, checks for existing chunk IDs
- **Query sanitization:** FTS5 special characters escaped before search

### Embedding Cache (`data/cache/embeddings.json`)

- **Format:** JSON with blake2b keys mapping to embedding vectors
- **Thread safety:** Async lock
- **Lazy save:** Dirty-flag pattern, only writes to disk when modified
- **Purpose:** Avoids redundant API calls for previously embedded texts

### Data Directory Layout

```
data/
├── bm25/
│   └── bm25.db                  # SQLite FTS5 database
├── cache/
│   └── embeddings.json          # Voyage embedding cache
├── vector_store/
│   ├── index.faiss              # FAISS index
│   └── chunk_metadata.json      # Chunk metadata (auto-generated)
├── uploads/                     # Temporary file upload staging
└── fixtures/                    # Test fixtures
    ├── sample.md
    ├── sample.py
    └── sample.txt
```

---

## 10. Authentication, Authorization, and Security

### Current State

ContextForge currently has **no active authentication or authorization**. The `requirements.txt` includes `PyJWT` and `passlib[bcrypt]` but these are not yet integrated into any route or middleware.

### Security Measures Currently in Place

| Measure | Implementation | File |
|---|---|---|
| **CORS** | Explicit origin whitelist (no wildcard), restricted methods (GET, POST), restricted headers (Authorization, Content-Type) | `app/main.py:81-87` |
| **File upload limit** | 50 MB max via `UploadFile` | `app/routes/ingest.py` |
| **Input validation** | Pydantic schemas with validators for all request types | `app/schemas/` |
| **FTS5 query sanitization** | Special characters escaped before SQLite FTS5 queries | `core/storage/bm25_index.py` |
| **Environment-based secrets** | API keys loaded from `.env` via Pydantic Settings | `app/config/settings.py` |
| **.gitignore** | `.env`, `backend/data/`, `backend/app/config/settings.py` excluded from git | `.gitignore` |

### Security Concerns

| Issue | Severity | Notes |
|---|---|---|
| **Hardcoded API keys in settings.py** | HIGH | `settings.py` has default API key values. This file is in `.gitignore` but should never have real keys as defaults. |
| **No authentication** | MEDIUM | Any client can ingest data or query the knowledge base |
| **No rate limiting** | MEDIUM | No protection against abuse or excessive API calls |
| **No input sanitization for queries** | LOW | User questions are passed directly to LLM prompts |
| **CORS credentials with localhost** | LOW | `allow_credentials=True` with localhost origins is acceptable for development |

---

## 11. Core Business Logic

### Ingestion Service (`app/services/ingest_service.py`)

The `IngestService` orchestrates the full ingestion pipeline:

1. Selects the appropriate **loader** based on `source_type`
2. Calls `loader.load()` to extract raw `Document` objects
3. Passes documents to `Orchestrator.ingest()` which runs:
   - Preprocessing (clean, metadata, dedup)
   - Chunking (text or code)
   - Embedding (Voyage AI API)
   - Indexing (FAISS + SQLite FTS5)
4. Returns `IngestResponse` with `source_id` and `chunks_indexed`

### Query Service (`app/services/query_service.py`)

The `QueryService` handles both streaming and non-streaming queries:

**Non-streaming (`query()`):**
1. Calls `Orchestrator.answer()` which runs the full pipeline
2. Returns `QueryResponse` with answer, sources, latency, and confidence

**Streaming (`stream_query()`):**
1. Calls `Orchestrator.retrieve_context()` to get reranked chunks
2. Yields `[SOURCES]` event with source metadata
3. Calls `Orchestrator.stream_answer()` to get token-by-token generation
4. Yields each token as a plain `data:` event
5. Yields `[LATENCY]` and `[CONFIDENCE]` events
6. Yields `[DONE]` terminator

### Dependency Injection (`app/dependencies.py`)

All components are wired as **singletons** via `@lru_cache(maxsize=1)`:

```
get_settings()          -> Settings
get_embedder()          -> VoyageEmbedder
get_faiss_store()       -> FaissStore
get_bm25_index()        -> BM25Index
get_reranker()          -> Reranker
get_prompt_builder()    -> PromptBuilder
get_text_chunker()      -> TextChunker
get_code_chunker()      -> CodeChunker
get_llm()               -> FallbackLLM (Gemini primary, Groq fallback)
get_hyde()              -> HydeQueryExpander
get_hybrid_retriever()  -> HybridRetriever
get_orchestrator()      -> Orchestrator (composes all above)
get_loaders()           -> Dict[str, BaseLoader]
get_ingest_service()    -> IngestService
get_query_service()     -> QueryService
```

Shutdown: `close_all()` closes the Voyage AI HTTP client and SQLite connection.

### Confidence Metrics Calculation

Server-side confidence is derived in `Orchestrator._build_confidence()`:

```python
coverage = (
    "Excellent" if mean_confidence > 0.85
    else "Strong" if mean_confidence > 0.65
    else "Moderate" if mean_confidence > 0.45
    else "Low" if mean_confidence > 0.25
    else "Weak"
)
```

- `mean_confidence`: sigmoid-normalized average of cross-encoder scores
- Floored at 0.35 so the frontend never shows zero confidence
- On reranker failure, degrades to 0.0 with un-reranked chunks

---

## 12. Request/Data Flow

### Complete Ingestion Flow (PDF Upload Example)

```
1. User clicks "Add Source" -> selects PDF -> drags file into drop zone
2. Frontend: api.js.ingestFile({ source_type: "pdf", file })
   -> POST /ingest/file?source_type=pdf (FormData with file)
3. Backend: app/routes/ingest.py.ingest_file()
   -> Validates file size (50MB limit), saves to data/uploads/
4. Backend: app/services/ingest_service.py.ingest()
   -> Selects PDFLoader
5. Backend: core/ingestion/pdf_loader.py.load()
   -> pypdf.PdfReader extracts text from each page
   -> Returns List[Document] with page-level metadata
6. Backend: core/orchestrator.py.ingest()
   -> TextCleaner.clean(): NFKC normalize, strip URLs
   -> MetadataExtractor.extract(): title, keywords, entities
   -> Deduplicator.deduplicate(): blake2b fingerprint
   -> TextChunker.chunk_documents(): 512-token chunks with 50-token overlap
   -> VoyageEmbedder.embed_texts(): batch API calls with caching
   -> FaissStore.add(): normalized vectors to IndexFlatIP
   -> BM25Index.add(): text to SQLite FTS5
7. Backend: Returns IngestResponse { source_id: UUID, chunks_indexed: 42 }
8. Frontend: Home.jsx updates sources list, shows notification toast
```

### Complete Query Flow

```
1. User types question in ChatBox, presses Enter
2. Frontend: useChat.js.sendMessage(question)
   -> Creates user message + placeholder assistant message
   -> Calls api.js.streamQuery({ question }, handlers)
3. Frontend: api.js reads SSE stream from POST /query/stream
4. Backend: app/routes/query.py.stream_query()
   -> QueryService.stream_query()
5. Backend: core/orchestrator.py.retrieve_context()
   -> HydeQueryExpander.expand(): LLM generates hypothetical passage
   -> VoyageEmbedder.embed_single(): embed expanded query
   -> HybridRetriever.retrieve(): parallel BM25 + Dense
     -> BM25Retriever -> BM25Index.search() (SQLite FTS5)
     -> DenseRetriever -> FaissStore.search() (cosine similarity)
     -> RRFFusion.fuse(): reciprocal rank fusion
   -> Reranker.rerank(): cross-encoder scoring
6. Backend: Yields [SOURCES] event with chunk metadata
7. Backend: core/orchestrator.py.stream_answer()
   -> PromptBuilder.build(): formats context + question
   -> FallbackLLM.stream(): Gemini token generation
8. Backend: Yields each token as data: event
9. Backend: Yields [LATENCY] with timing breakdown
10. Backend: Yields [CONFIDENCE] with metrics
11. Backend: Yields [DONE]
12. Frontend: useChat.js updates assistant message incrementally
13. Frontend: SourceViewer displays evidence panel with confidence chart
```

---

## 13. External Services and Libraries

### External APIs

| Service | Purpose | Authentication | Endpoint |
|---|---|---|---|
| **Voyage AI** | Text embeddings | API key (`x-api-key` header) | `https://api.voyageai.com/v1/embeddings` |
| **Google Gemini** | LLM generation | API key (`x-goog-api-key` header) | `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` |
| **Groq** | LLM generation (fallback) | API key (`Authorization: Bearer` header) | `https://api.groq.com/openai/v1/chat/completions` |
| **GitHub REST API** | Repository ingestion | Token (optional, for private repos) | `https://api.github.com/repos/{owner}/{repo}` |
| **Langfuse** | Observability tracing | Public + secret keys | `https://cloud.langfuse.com` (configurable) |

### Key Libraries

| Library | Purpose | Used In |
|---|---|---|
| `httpx` | Async HTTP client for all API calls | `voyage_embedder.py`, `gemini_llm.py`, `groq_llm.py`, `github_loader.py`, `web_loader.py` |
| `trafilatura` | Web page content extraction | `web_loader.py` |
| `pypdf` | PDF text extraction | `pdf_loader.py` |
| `python-docx` | DOCX text extraction | `docx_loader.py` |
| `faiss-cpu` | Vector similarity search | `faiss_store.py` |
| `sentence-transformers` | Cross-encoder reranker | `reranker.py` |
| `langchain-text-splitters` | Text chunking | `text_chunker.py` |
| `tiktoken` | BPE tokenizer | `text_chunker.py` |
| `spaCy` (`en_core_web_sm`) | NER for metadata | `metadata_extractor.py` |
| `langfuse` | Distributed tracing | `tracer.py` (all `@observe` decorators) |

---

## 14. Environment Configuration

### Backend Configuration (`backend/.env`)

```env
# API Keys (loaded via Pydantic Settings)
VOYAGE_API_KEY=pa-...
GOOGLE_API_KEY=AIza...
GROQ_API_KEY=gsk_...

# Langfuse (optional observability)
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com

# Feature flags
USE_HYDE=true

# Logging
LOG_LEVEL=INFO
```

### Frontend Configuration (`frontend/.env`)

```env
VITE_API_BASE_URL=http://localhost:8000
```

### Key Settings (`backend/app/config/settings.py`)

| Setting | Default | Purpose |
|---|---|---|
| `VOYAGE_API_KEY` | (hardcoded) | Voyage AI authentication |
| `GOOGLE_API_KEY` | (hardcoded) | Google Gemini authentication |
| `GROQ_API_KEY` | (hardcoded) | Groq authentication |
| `FAISS_INDEX_PATH` | `data/vector_store/index.faiss` | FAISS index file location |
| `BM25_DB_PATH` | `data/bm25/bm25.db` | SQLite FTS5 database location |
| `CACHE_PATH` | `data/cache/embeddings.json` | Embedding cache location |
| `UPLOAD_DIR` | `data/uploads` | File upload staging directory |
| `MAX_GITHUB_FILES` | 500 | Max files to fetch from GitHub repos |
| `CHUNK_SIZE` | 512 | Token-level chunk size |
| `CHUNK_OVERLAP` | 50 | Token-level overlap |
| `TOP_K_RETRIEVAL` | 20 | Candidates per retrieval leg |
| `TOP_K_RERANK` | 5 | Final chunks after reranking |
| `USE_HYDE` | true | HyDE query expansion toggle |
| `VOYAGE_MODEL` | `voyage-3-lite` | Embedding model name |
| `VOYAGE_BATCH_SIZE` | 128 | Embedding batch size |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Primary LLM model |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Fallback LLM model |
| `RERANK_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Reranker model |
| `ALLOWED_ORIGINS` | `[]` (defaults to localhost) | CORS allowed origins |
| `LOG_LEVEL` | `INFO` | Python logging level |

---

## 15. Deployment and Scalability

### Current Deployment

The project is designed for **local development** with:

- **Backend:** Run via `uvicorn` (implied by `requirements.txt`)
- **Frontend:** Run via `vite dev` (HMR development server)
- **No Docker services defined yet** (`docker-compose.yml` is an empty scaffold)

### Production Deployment Considerations

| Aspect | Current State | Recommended for Production |
|---|---|---|
| **Container** | No Dockerfile | Add multi-stage Dockerfile for backend + frontend |
| **Orchestration** | Empty `docker-compose.yml` | Define backend, frontend, and data volume services |
| **Reverse Proxy** | None | Add nginx or Caddy in front of both services |
| **Database** | SQLite FTS5 (file-based) | Suitable for single-node; for multi-node, consider PostgreSQL with pgvector |
| **Vector Store** | FAISS (file-based) | Single-node only; for distributed, consider Qdrant, Weaviate, or Pinecone |
| **File Storage** | Local filesystem | For multi-replica, use S3-compatible object storage |
| **Secrets** | `.env` file | Use Vault, AWS Secrets Manager, or Kubernetes secrets |
| **Logging** | Python `logging` + Langfuse | Add structured logging (JSON) + log aggregation |

### Scalability Limitations

1. **FAISS IndexFlatIP:** Brute-force search, O(n) per query. For millions of vectors, use `IndexIVFFlat` or `IndexHNSWFlat`.
2. **SQLite FTS5:** Single-writer. For concurrent writes, migrate to PostgreSQL FTS or Elasticsearch.
3. **Embedding cache:** JSON file on disk. For multi-process, use Redis.
4. **Single-process Python:** CPU-bound operations (reranking, chunking) are run via `asyncio.to_thread()`. For high throughput, use multiple workers.

---

## 16. Design Patterns and Optimizations

### Design Patterns

| Pattern | Implementation | Location |
|---|---|---|
| **Singleton DI** | `@lru_cache(maxsize=1)` for all components | `app/dependencies.py` |
| **Frozen Dataclasses** | Immutable domain objects with `MappingProxyType` | `core/types.py` |
| **ABC Interfaces** | Clean contracts for `Embedder`, `LLM`, `Retriever`, `BaseLoader` | `core/interfaces/` |
| **Strategy Pattern** | Pluggable loaders, chunkers, embedders, LLMs | `core/ingestion/`, `core/chunking/`, `core/embedding/`, `core/generation/` |
| **Facade** | `Orchestrator` composes all pipeline stages | `core/orchestrator.py` |
| **Decorator** | `@observe(name=...)` for Langfuse tracing | `observability/tracer.py` |
| **Graceful Degradation** | FallbackLLM, HybridRetriever (one leg fails), reranker failure fallback | Multiple locations |
| **Builder** | `PromptBuilder` constructs prompts from templates | `core/generation/prompt_builder.py` |

### Performance Optimizations

| Optimization | Description | Location |
|---|---|---|
| **Embedding cache** | Disk-based JSON with blake2b keys avoids redundant API calls | `core/embedding/voyage_embedder.py` |
| **Lazy model loading** | Reranker loaded only on first use | `core/retrieval/reranker.py` |
| **Parallel retrieval** | BM25 + Dense run concurrently via `asyncio.gather` | `core/retrieval/hybrid_retriever.py` |
| **FAISS IndexFlatIP** | L2-normalized vectors enable inner product = cosine similarity | `core/storage/faiss_store.py` |
| **SQLite WAL mode** | Write-ahead logging for concurrent reads during writes | `core/storage/bm25_index.py` |
| **Batch embedding** | `VOYAGE_BATCH_SIZE=128` reduces API round trips | `core/embedding/voyage_embedder.py` |
| **SSE streaming** | Token-by-token delivery reduces perceived latency | `app/routes/query.py`, `frontend/src/services/api.js` |
| **Dirty-flag cache saves** | Embedding cache only writes to disk when modified | `core/embedding/voyage_embedder.py` |
| **tiktoken tokenizer** | Fast BPE tokenizer for accurate token-level chunking | `core/chunking/text_chunker.py` |
| **AST-based code chunking** | Preserves Python function/class boundaries | `core/chunking/code_chunker.py` |

---

## 17. Testing Strategy

### Unit Tests (`backend/tests/unit/`)

| Test File | What It Tests |
|---|---|
| `test_chunkers.py` | `TextChunker` overlap behavior; `CodeChunker` Python AST symbol extraction |
| `test_hyde.py` | `HydeQueryExpander.expand()` delegates to LLM (FakeLLM) |
| `test_reranker.py` | `Reranker.rerank()` ordering with FakeModel |
| `test_embedding_cache.py` | `VoyageEmbedder` disk cache hit (second call skips API) |
| `test_storage_and_retrieval.py` | `BM25Index` add/search round-trip; `FaissStore` best-match; `RRFFusion` merging |

### Integration Tests (`backend/tests/integration/`)

| Test File | What It Tests |
|---|---|
| `test_api.py` | `POST /query` returns answer; `POST /query/stream` returns SSE; `POST /ingest/source` returns source_id (all with fake service overrides) |

### Testing Approach

- **Unit tests** use fake/stub implementations (FakeLLM, FakeModel, monkeypatched embedder) to avoid external API dependencies
- **Integration tests** override FastAPI dependencies via `app.dependency_overrides` to inject fake services
- **No frontend tests** exist currently
- **No CI/CD pipeline** is configured

---

## 18. Strengths, Weaknesses, and Improvements

### Strengths

| Strength | Evidence |
|---|---|
| **Well-architected pipeline** | Clean separation: interfaces, services, core logic, storage. Each component is independently testable. |
| **Hybrid retrieval** | BM25 + dense with RRF fusion captures both keyword and semantic relevance |
| **Graceful degradation** | FallbackLLM, HybridRetriever failure handling, reranker fallback to un-reranked results |
| **Production-grade streaming** | SSE with structured events (SOURCES, LATENCY, CONFIDENCE, DONE) |
| **Server-side confidence** | Never trusts frontend; backend computes and sends confidence metrics |
| **Code-aware chunking** | AST-based Python chunker preserves function/class boundaries |
| **Embedding caching** | Avoids redundant Voyage API calls with disk-based blake2b cache |
| **Comprehensive observability** | Every pipeline stage decorated with `@observe` for Langfuse tracing |
| **Async-first design** | All I/O operations are async; CPU-bound work offloaded via `asyncio.to_thread` |
| **CPU-only compatible** | Designed for Intel i5-1240P, 8GB RAM without GPU requirements |

### Weaknesses

| Weakness | Impact | Severity |
|---|---|---|
| **No authentication** | Any client can ingest/query the knowledge base | HIGH |
| **Hardcoded API keys** | Default values in `settings.py` could leak to git history | HIGH |
| **No frontend tests** | No automated UI verification | MEDIUM |
| **No CI/CD** | No automated testing or deployment pipeline | MEDIUM |
| **FAISS IndexFlatIP** | Brute-force O(n) search; won't scale to millions of vectors | MEDIUM |
| **SQLite single-writer** | Limits concurrent ingestion throughput | MEDIUM |
| **No rate limiting** | Vulnerable to abuse | MEDIUM |
| **Orphaned components** | `RepoInput.jsx` and `UploadPanel.jsx` are unused dead code | LOW |
| **Empty docker-compose** | No containerized deployment ready | LOW |
| **Stub scripts** | `query_cli.py` and `ingest_repo.py` are unimplemented | LOW |
| **No pagination** | Large ingestion jobs have no progress tracking | LOW |

### Recommended Improvements

1. **Add JWT authentication** (PyJWT + passlib already in dependencies)
2. **Add rate limiting** (slowapi or custom middleware)
3. **Implement Docker Compose** with backend, frontend, and volume mounts
4. **Add CI/CD** (GitHub Actions for linting, testing, Docker builds)
5. **Add frontend tests** (Vitest + React Testing Library)
6. **Clean up orphaned components** (`RepoInput.jsx`, `UploadPanel.jsx`)
7. **Remove hardcoded API key defaults** from `settings.py`
8. **Implement progress tracking** for long ingestion jobs (WebSocket or polling)
9. **Add `/ready` endpoint** that checks FAISS/SQLite connectivity (currently only `/health`)
10. **Consider FAISS IVF/HNSW index** for scaling beyond 100K vectors
