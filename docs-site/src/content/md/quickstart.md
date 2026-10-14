# Quickstart

Install ContextForge, choose model access, ingest a source and produce your first
cited answer.

## Prerequisites

- **Python 3.14+**
- **Node.js 22+**
- At least one **embedding model** and one **chat model**, each with an API key —
  or a local server that needs none.

> **No API key goes in the environment.** Add them in the app instead. Keys are
> stored encrypted and handed to the provider at call time.

The app starts and every screen loads with nothing configured. Only the actions
that need a provider fail, and they name the model that needs a key.

## 1 · Backend

```bash
git clone https://github.com/AdnanZamanNiloy/contexforge.git
cd contexforge

make install                          # venv + deps for both halves
cp backend/.env.example backend/.env  # no API keys needed here
make dev-backend                      # FastAPI on :8000
```

> **Why not `uvicorn backend.app.main:app`?** Every module inside `backend/app/`
> imports `from app.…`, so `app` has to be the package and `backend/` the working
> directory. `make dev-backend` runs `cd backend && uvicorn app.main:app`.

## 2 · Frontend

```bash
make dev-frontend                     # Vite on :5173
```

## 3 · Verify

```bash
curl http://localhost:8000/health
# → {"status":"ok","service":"contextforge"}
```

Then open **http://localhost:5173** and open **Model Hub** to add a model.

## 4 · Your first five minutes

1. **Model Hub → add an embedding model** and paste its key (or point it at a
   local server). Use **test** to run a real call; an embedding probe also
   detects and saves the vector dimension.
2. **Model Hub → add a chat model**, then select it under **Serving**. For
   failover, create a chain of two or more models and serve the chain instead.
3. **Create a project** and **add a source**: upload a PDF or DOCX, or paste a
   web, YouTube or GitHub URL.
4. **Open the source panel** and read the extraction verdict. A source that
   extracted badly should be fixed or removed *before* you trust answers from it.
5. **Select sources, pick a depth**, and watch the cost estimate update. Then ask
   a question and read the citations, confidence and latency that come back with
   the answer.

## 5 · Fully local setup

Nothing about ContextForge requires a hosted API. To keep all model traffic on
your machine:

1. Run a local OpenAI-compatible server (llama.cpp, Ollama, vLLM or LM Studio).
2. In **Model Hub**, add a **local embedding model** and a **local chat model**
   pointing at that server's base URL.
3. Serve them. Reranking already runs locally.

Remote *sources* (web pages, YouTube transcripts, GitHub repositories) still need
network access to fetch.

## The first "is it stuck?" moment

On the Voyage free tier, embeddings are throttled to one request per 21 seconds
to stay under 3 requests/minute, and each request is sized to stay under 10k
tokens. A large PDF can take a few minutes on first ingest. The text is cached on
disk afterwards, so re-ingesting the same content is fast. See
[Troubleshooting](/docs/troubleshooting).
