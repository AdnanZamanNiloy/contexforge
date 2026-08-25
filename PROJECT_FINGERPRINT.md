# ContextForge — Project Fingerprint

> A handoff document for a new engineer to understand, review, and improve the project without re-exploring from scratch. All claims below are labeled **[Confirmed]** (verified in code) or **[Assumption/Unknown]**. No code was modified by the authoring process.

## 1. Purpose

**Confirmed.** ContextForge is a **local, self-hosted RAG (retrieval-augmented generation) knowledge base** where users ingest documents (PDF, DOCX), web URLs, or full GitHub repositories, then ask natural-language questions against that corpus. It computes answers grounded in cited source chunks and streams them via Server-Sent Events.

**Primary users** (from `manual.md`): a single developer/individual (CPU-only laptop, Intel i5-1240P, 8GB RAM, no GPU requirement). It is explicitly **async-first** and **CPU-only compatible**.

**Core features:**
- Hybrid retrieval: dense (FAISS) + sparse (BM25 via SQLite FTS5) fused with Reciprocal Rank Fusion (RRF).
- Cross-encoder reranking (`cross-encoder/ms-marco-MiniLM-L-6-v2`).
- HyDE query expansion (gated by `settings.USE_HYDE`).
- Multi-provider LLM generation with fallback: Gemini → Groq → internal fallback LLM.
- SSE streaming with server-side confidence metrics, latency breakdown, and cited sources.
- Embedding cache (blake2b-keyed, disk-persisted) to avoid redundant Voyage API calls.
- Langfuse tracing via `@observe` on every pipeline stage.

## 2. Structure

**Confirmed.** Top-level layout:

```
contextforge/
  manual.md                 — authoritative dev/spec doc (1072 lines)
  docker-compose.yml        — [Confirmed] essentially empty (no services)
  Makefile, requirements.txt, pyproject.toml
  backend/
    app/
      main.py               — FastAPI app factory, lifespan, CORS, routers, /health
      dependencies.py       — lru_cache singletons (get_*_service, get_orchestrator)
      config/settings.py    — Settings (models, paths, HARDCODED API KEYS)
      config/settings_example.py
      auth/request.py       — bearer auth dep (declared; [Assumption] unused by routers)
      routes/
        ingest.py           — /ingest/source, /ingest/file, /ingest/source/{id}, /ingest/clear, /ingest/sources
        github.py           — /github/ingest
        query.py            — /query, /query/stream
      schemas/
        ingest.py           — IngestRequest/IngestResponse/Delete/Clear/Sources
        github.py           — GithubIngestRequest
        query.py            — QueryRequest/QueryResponse/ConfidenceMetrics/SourceSummary
      services/
        ingest_service.py   — loader resolve, chunk, embed, store
        query_service.py    — answer()/stream_answer()
    core/
      orchestrator.py       — central coordinator
      types.py              — frozen Document/Chunk (MappingProxyType metadata)
      loaders/              — base/pdf/docx/text/web/github
      chunkers/             — text (tiktoken), code (AST)
      processing/           — cleaner/deduplicator/metadata_extractor
      interfaces/           — abstraction contracts
      storage/              — bm25_index.py, faiss_store.py, embedding_cache.py
      retrieval/            — bm25_retriever, dense_retriever, hybrid_retriever, rrf_fusion, reranker, hyde
      embedding/            — voyage_embedder.py, bge_embedder.py
      generation/           — base_llm, gemini_llm, groq_llm, fallback_llm, prompt_builder
      observability/tracer.py — @observe decorator -> Langfuse
    tests/
      unit/                 — test_hyde, test_chunkers, test_storage_and_retrieval, test_embedding_cache, test_reranker
      integration/test_api.py
    .env                    — only USE_HYDE=true
  frontend/
    src/
      App.jsx, main.jsx
      services/api.js       — HTTP + SSE client
      hooks/useChat.js      — chat state, abort, confidence
      components/           — Home, ChatBox, MessageBubble, SourceViewer, RepoInput*, UploadPanel*
      (* linked below: orphaned/dead)
  docs/                     — architecture.md, evaluation.md, pipeline.md ([Confirmed] 3-line stubs)
  scripts/                  — ingest_repo.py, query_cli.py ([Confirmed] 6-line stubs)
```

## 3. Architecture

**Confirmed.** Request flow (ingest): client → router → service → orchestrator → loaders → chunkers → processing → embeddings (Voyage) → duplicate FAISS + BM25 stores.

**Confirmed.** Request flow (query): client → `POST /query` or `/query/stream` → `QueryService` (@query_service) → `Orchestrator` → `retrieve_context` → HyDE (optional) → hybrid retrieve (`asyncio.gather(return_exceptions=True)`) → RRF fusion → rerank → prompt build → LLM → returns **3-tuple** `(reranked, timings, mean_confidence)`.

**Confirmed.** `main.py` uses the modern lifespan context-manager pattern (not deprecated `@on_event`). `CLEAR_ON_START` (default `False`) wipes the KB at boot (FIX #7/#8). CORS is non-wildcard with explicit fallback origins `http://localhost:5173`/`:3000` (FIX #6).

**Confirmed.** Dependency injection via `Depends(get_*_service)` where `dependencies.py` uses `@lru_cache` singletons.

**Architectural facts:**
- `QueryService.stream_answer` yields **plain dicts**; `routes/query.py:_sse_generator` wraps them in SSE framing (`data: <token>\n\n`, `[SOURCES]`, `[LATENCY]`, `[CONFIDENCE]`, `[DONE]`) — FIX #1/#3/#7.
- `DenseRetriever`/`Bm25Retriever` run inside `hybrid_retriever.py` via `asyncio.gather(..., return_exceptions=True)` with `_unwrap` for graceful degradation (FIX #6).
- DB paths: `data/vector_store/index.faiss` (+ `index.json` sidecar), `data/bm25/bm25.db`, `data/cache/embeddings.json`, `data/uploads`.

## 4. Tech Stack

**Confirmed.**
- **Backend**: Python ≥3.14, FastAPI, Pydantic v2 (frozen models), Uvicorn.
- **Retrieval/embeddings**: `faiss-cpu` (IndexFlatIP), SQLite (FTS5 via `bm25_index.py`), Voyage AI (`voyage-3-lite`), optional BGE embedder, cross-encoder reranker (sentence-transformers).
- **Chunking**: `tiktoken` (cl100k_base) for text; Python `ast` for code.
- **LLMs**: Google Gemini (`gemini-flash-latest`), Groq (`llama-3.3-70b-versatile`), plus an internal fallback LLM.
- **Observability**: Langfuse tracing.
- **Frontend**: React 18 + Vite, plain `fetch` (no axios), AbortController + Timeout (25s), SSE via `ReadableStream` reader (no native EventSource).
- **DB**: SQLite (FTS5) + FAISS (no external DB server).
- **Auth**: `pyjwt`/`passlib` in deps; `backend/app/auth/request.py` exists. **[Assumption]** No router actually depends on auth dependency (not wired into the routers inspected).
- **Digital infrastructure**: none provisioned (empty docker-compose, no CI/CD). **[Confirmed]**

## 5. Core Workflows

### 5.1 Ingest a source (`POST /ingest/source` — `routes/ingest.py:41`)
`ingest_source` → `IngestRequest` (schema validates source format vs `source_type` via `model_validator`) → `IngestService.ingest_source`. Error mapping: `ValueError`→422, `RuntimeError`→502. Response: `IngestResponse{source_id, chunks_indexed, message}`.

### 5.2 Upload a file (`POST /ingest/file` — `routes/ingest.py:68`)
`ingest_file(source_type: Literal["pdf","docx"])` — upload hard-limited to `_MAX_UPLOAD_BYTES = 50MB`, MIME allowlist in `_ALLOWED_MIME`. Frontend `api.js` sends multipart `FormData` at `/ingest/file?source_type=...`.

### 5.3 Ingest a GitHub repo (`POST /github/ingest` — `routes/github.py:37`)
`ingest_github` → `GithubIngestRequest` → canonical URL regex `_GITHUB_URL_RE` (`https://github.com/owner/repo`, optional `.git`/`.git?`?) → clones and ingests up to `settings.MAX_GITHUB_FILES` (500), skipping binaries/lock files.

### 5.4 Ask a question (`POST /query` — `routes/query.py:23`)
`query` → `QueryRequest` (blank-question validator) → `QueryService.answer` → `QueryResponse{answer, sources:[SourceSummary], latency_ms, confidence:ConfidenceMetrics|null}`. 422 on `ValueError`, 502 on `RuntimeError`.

### 5.5 Stream an answer (`POST /query/stream` — `routes/query.py:77`)
`stream_query` → `StreamingResponse(_sse_generator(...), media_type="text/event-stream")`; no-buffering headers. Emits tokens as `data: <token>` then `[SOURCES]`/`[LATENCY]`/`[CONFIDENCE]`/`[DONE]`; mid-stream errors emit `data: [ERROR] <msg>`. Frontend `streamQuery` in `api.js` parses these markers.

### 5.6 Clear / delete
`DELETE /ingest/source/{source_id}` → `DeleteResponse`; `DELETE /ingest/clear` → `ClearResponse` (wipes FAISS + BM25 + deduplicator); `GET /ingest/sources` → `SourcesResponse`.

## 6. Data Model

**Confirmed** (`core/types.py`):
- `Document` — frozen dataclass; `document_id`, `text`, metadata; `__post_init__` validates `document_id`/`text`.
- `Chunk` — `chunk_id`, `text`, metadata; metadata is packed as `MappingProxyType` (immutable).
- `RerankedChunk` — `chunk_id`, `source_id`, `score`, `rank`; `metadata`.

**Confirmed** (schemas): `QueryRequest`, `QueryResponse`, `ConfidenceMetrics` (frozen, `answer_confidence` ∈ [0,1], `source_coverage` ∈ `{Excellent,Strong,Moderate,Low,Weak}`), `SourceSummary`, `IngestRequest`, `IngestResponse`, etc.

**Persistence flow:** chunk → embedding → FAISS (`IndexFlatIP` + `index.json` metadata sidecar, `.meta.json` fallback) AND BM25 (`bm25.db` FTS5) AND optional dedupe/embedding cache (`data/cache/embeddings.json`, blake2b-keyed).

**[Unknown]** No formal entity-relationship diagram or ORM; identity is string `source_id`/`chunk_id` (uuid4 for source). Cross-store consistency is maintained by the orchestrator, not the DB.

## 7. APIs & Integrations

**Confirmed.** Routes (prefix-rooted as shown):

| Method | Path | Handler | Response |
|---|---|---|---|
| POST | `/ingest/source` | `ingest_source` | `IngestResponse` |
| POST | `/ingest/file` | `ingest_file` | `IngestResponse` |
| DELETE | `/ingest/source/{source_id}` | `delete_source` | `DeleteResponse` |
| DELETE | `/ingest/clear` | `clear_knowledge_base` | `ClearResponse` |
| GET | `/ingest/sources` | `sources` | `SourcesResponse` |
| POST | `/github/ingest` | `ingest_github` | `IngestResponse` |
| POST | `/query` | `query` | `QueryResponse` |
| POST | `/query/stream` | `stream_query` | `StreamingResponse` (SSE) |
| GET | `/health` | `health` | `{status, service}` |

**External services:** Voyage AI (embeddings), Google Gemini (generate), Groq (generate), Langfuse (tracing). **Confirmed** these are the only external dependencies; all are called directly in their modules, not abstracted behind an interface except LLMs (`base_llm.py` abstract + fallback).

**Auth:** `auth/request.py` exists; docs mark "No authentication — any client can ingest/query" as HIGH weakness. **[Confirmed no auth enforced in the router handlers I read]**.

## 8. Business Logic / Invariants

**Confirmed.**
- `TOP_K_RETRIEVAL=20`, `TOP_K_RERANK=5`, `CHUNK_OVERLAP=50`, `CHUNK_SIZE=512`, `VOYAGE_BATCH_SIZE=128`, `MAX_GITHUB_FILES=500`, `CLEAR_ON_START=False`, `USE_HYDE=true`.
- Query request bounds: `top_k_retrieval` ∈ 1–200, `top_k_rerank` ∈ 1–20 (FIX #2).
- `QueryRequest.question` / `IngestRequest.source` reject blank/whitespace-only input.
- Github URL is canonicalized via regex + `source_type='github'` requires `https://github.com/` prefix.
- Reranker applies sigmoid calibration with `_MIN_CONFIDENCE_FLOOR=0.15`.
- Embedding cache key = blake2b hash of text/model (FIX #5).
- Retry/backoff: Gemini retries on `{429,500,502,503,504}` (max 3); Groq defines `_GROQ_URL`; fallback LLM treats `(OSError, TimeoutError, RuntimeError)` as retryable.
- **Fragile assumption [Confirmed]**: `routes/ingest.py:53` logs `getattr(request, "source_url", "?")` but `IngestRequest` fields are `source`/`source_type` → the log line **always prints `?`**. Purely cosmetic (exception-safe), not a functional failure.

## 9. Testing

**Confirmed.**
- **Test location**: `backend/tests/unit/` + `backend/tests/integration/test_api.py`. Tests **exist** (contradicting any "no tests" claim — manual's table refers to *frontend* tests).
- **Coverage**:
  - `test_hyde.py` — `HydeQueryExpander` with `FakeLLM`; asserts LLM is used.
  - `test_chunkers.py` — text chunker splits with overlap (expects 4 chunks); code chunker extracts symbols `{Example, greet, add}`.
  - `test_storage_and_retrieval.py` — BM25 index round-trip; FAISS returns best match; RRF fusion merges scores.
  - `test_embedding_cache.py` — Voyage embedder uses cache (monkeypatched `_embed_batch`).
  - `test_reranker.py` — monkeypatches `_load_model_sync`; asserts `results[0].rank == 1`.
  - `test_api.py` — `FakeIngestService`/`FakeQueryService`; `test_query_endpoint_returns_answer` and `test_stream_endpoint_yields_events`.
- **Runner state**: pytest 9.1.1 previously ran; `.pytest_cache` shows **13 collected** tests, with **2 currently last-failed**: `integration/test_api.py::test_query_endpoint_returns_answer` and `unit/test_reranker.py::test_reranker_uses_scores`.

**Missing / critical untested areas:**
- **No `test_github.py`, no loader tests, no orchestrator unit tests, no chunker edge/empty-input, no auth tests, no `bge_embedder`/fallback LLM tests.**
- **No CI/CD**, so tests never gate merges.
- **Blocker [Confirmed]**: `backend/.venv/bin/python -m pytest` → `No module named pytest` — the venv lacks pytest, so tests aren't runnable as-is.
- The 2 last-failed tests are the highest-value first candidates (they exercise real endpoint/routing and reranker rank logic).

## 10. Code Quality

**Confirmed.**
- **Strengths**: clear module separation (routes/schemas/services/core/interfaces), frozen Pydantic models, pervasive `FIX #N` annotations documenting design decisions, centralized `Settings`, explicit error-to-status mapping, SSE framing isolated in one generator.
- **Coupling**: core `orchestrator.py` is a god-object coordinating ingest/query/clear/delete — high fan-out. LLMs behind an interface, but embeddings/retrieval/loaders are concretely coupled to their implementations.
- **Duplication**: `_ALLOWED_MIME`/`_MAX_UPLOAD_BYTES` and various constants live inside route modules, overlapping with `settings.py` (moderate duplication).
- **Consistency**: `settings_example.py` vs `settings.py` drift possible; `pipeline.py` is a **deprecated alias** that should be removed.
- **Dead code [Confirmed]**: `frontend/src/components/RepoInput.jsx` + `UploadPanel.jsx` are **orphaned** — never imported by `Home.jsx`. `scripts/query_cli.py`/`ingest_repo.py` and `docs/*.md` are stubs.
- **Docs accuracy [Confirmed mismatch]**: `GEMINI_MODEL="gemini-flash-latest"` in settings vs `gemini-2.0-flash` in `manual.md`.

## 11. Risks

**Security (HIGH):**
- **Hardcoded API keys** in `app/config/settings.py` (`VOYAGE_API_KEY`, `GOOGLE_API_KEY`, `GROQ_API_KEY`) — leak risk to git history / logs. **[Confirmed]**
- **No authentication** — `POST /ingest`, `DELETE /ingest/clear` are destructive and unauthenticated.
- **No rate limiting** — `/query/stream` and embeddings/generation are abuse-prone.

**Performance (MEDIUM):**
- **FAISS IndexFlatIP** = brute-force O(n) search; won't scale past ~100K vectors (manual recommends IVF/HNSW).
- **SQLite single-writer** caps concurrent ingestion throughput.
- **CPU-only, no GPU** — cross-encoder reranking is compute-bound; offloaded via `asyncio.to_thread`.

**Scalability / Technical debt:**
- No pagination for large ingestion jobs (no progress tracking).
- Empty `docker-compose.yml`, no CI/CD, no ready probe (`/health` exists but doesn't check FAISS/SQLite connectivity — manual recommends `/ready`).

**Fragile areas / hidden dependencies:**
- **Uncommitted change** to `core/storage/bm25_index.py` (`_sanitise_query` — quotes multi-term queries or returns `""`). **This is an uncommitted diff** — flag for review.
- `Orchestrator.retrieve_context` returning a 3-tuple is an implicit contract; refactors could silently break `query_service` / tests.
- HyDE/failsafe path silently falls back to original question when `USE_HYDE` is off — behavior gated by env, easy to miss in reviews.

## 12. Improvement Plan

**Quick wins (low effort, medium/high impact):**
1. **Run the 2 last-failed tests** (install pytest in venv) — they cover real endpoints/rerank logic and likely reveal regressions.
2. **Fix the `source_url` log line** (`routes/ingest.py:53`) → use `request.source`.
3. **Remove dead code**: `RepoInput.jsx`, `UploadPanel.jsx`, deprecated `pipeline.py`, stub `docs/`, `scripts/`.
4. **Move hardcoded API keys to env-only** (require explicit `Settings` env injection; no defaults).
5. **Add `/ready`** endpoint to verify FAISS + SQLite connectivity.

**Medium-term:**
6. **Add auth** (PyJWT/passlib already in deps) — protect all ingest/delete endpoints.
7. **Add rate limiting** + request size/body validation hardening.
8. **Add frontend tests** (Vitest + React Testing Library) + Vitest config.
9. **Add CI/CD** (GitHub Actions: lint, test, build) and flesh out `docker-compose.yml`.
10. **Address the `bm25_index.py` uncommitted change**: review & commit with tests.

**Architectural (longer term):**
11. **Swap FAISS IndexFlatIP → IVF/HNSW** or move to vector DB for scale.
12. **Reduce god-object `orchestrator.py`** — split ingest vs query coordination into services, introduce interface contracts for retrieval/embeddings.
13. **Centralize constants** into `settings.py`; remove route-module duplication.
14. **Add ingest pagination/progress** (WebSocket or polling) for large jobs.

*(Prioritize by impact/effort: #1–#5 immediately; #6–#9 next; #10–#14 when scaling matters.)*

## 13. Change Impact

Before modifying major subsystems, check these:

- **Changing schema/model fields** → cascades to `core/types.py`, `schemas/*`, `prompt_builder`, LLM config, and frontend `api.js`/`useChat.js`. Keep field names aligned with the SSE markers.
- **Modifying retrieval** → preserve the `retrieve_context` **3-tuple** contract and `hybrid_retriever`'s `return_exceptions` graceful-degradation path; re-run `test_storage_and_retrieval.py` + `test_reranker.py`.
- **Modifying LLM/embedding adapter** → maintain retry/backoff semantics; update `base_llm` interface implementations; re-run `test_hyde.py` and `test_embedding_cache.py`.
- **Modifying routes/SSE** → keep `_sse_generator` marker format (`[SOURCES]`/`[LATENCY]`/`[CONFIDENCE]`/`[DONE]`) in sync with `frontend api.js:114 streamQuery`.
- **Modifying `main.py`/CORS/lifespan** → verify explicit-origin fallback and `CLEAR_ON_START` behavior; re-run integration API test.
- **Modifying `Settings`** → confirm `.env` and `settings_example.py` stay consistent; never reintroduce hardcoded keys as defaults.
- **Changing `bm25_index.py`** → review the uncommitted `_sanitise_query` change; add regression test for quoted/empty queries.

## 14. Reviewer Summary

**What is good:** Clean layering (routes → services → orchestrator → core → interfaces), immutable Pydantic models, well-documented `FIX #N` decisions, explicit error mapping, isolated SSE generator, focused unit tests that exist and cover retrieval/rerank/HyDE/cache, async-first design, CPU-only friendliness.

**What is weak:** Hardcoded secrets + no auth (HIGH), no CI/CD, no frontend tests, test venv lacks pytest (runner broken), 2 failing tests unresolved, god-object orchestrator, FAISS brute-force scaling, orphaned/stub files, settings-vs-manual doc drift (`gemini-flash-latest`), uncommitted `bm25_index.py` change.

**Improve first:** (1) get the core test suite green, (2) fix the `source_url` logging bug, (3) remove hardcoded keys / enforce env-only secrets, (4) delete dead code.

**Do not change unnecessarily:** the SSE marker protocol, the `retrieve_context` 3-tuple contract, the frozen-model immutability pattern, and the `FIX #N` documentation convention — these are load-bearing and refactoring them risks silent regressions.

---

**Disclaimer:** This fingerprint was produced via read-only inspection. Where behavior could not be confirmed (auth wiring, no ER diagram, loader/auth internals not fully read, whether pip in `backend/.venv` installs pytest), those are marked **[Assumption/Unknown]**. Recommended to re-verify auth middleware wiring and the `requires-python>=3.14` toolchain before making changes. No files were modified during fingerprint creation.
