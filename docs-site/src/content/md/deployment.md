# Deployment

ContextForge is designed to run as a long-lived process on a machine you control.
There is no container image yet, so production today means running from source.

## Running the backend

```bash
cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- **Run a single worker.** The orchestrator, FAISS index and other services are
  in-process singletons, so extra workers would each hold their own copy of the
  index.
- Run it under a process manager (systemd, supervisord) with `backend/` as the
  working directory, and restart on failure.
- **Liveness:** `GET /health` returns `{"status":"ok","service":"contextforge"}`.
- **Logging:** set `LOG_LEVEL`.

## Serving the frontend

```bash
cd frontend
VITE_API_BASE_URL=https://api.example.com npm run build   # static output in frontend/dist
```

Serve `frontend/dist` from any static host or reverse proxy, and add that origin
to `ALLOWED_ORIGINS`.

## Reverse proxy

Answers and the architecture diagram stream over SSE, so the proxy must not buffer
those responses. For nginx:

```nginx
location ~ ^/(query/stream|architecture/generate)$ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;          # let tokens through as they arrive
    proxy_read_timeout 300s;
}
```

## Authentication

ContextForge has no built-in user authentication. If it is reachable by anyone
other than you, put it behind a reverse proxy that authenticates (basic auth, or
an OIDC-aware proxy) and bind the backend to `127.0.0.1`. That is a deliberate
boundary, not an oversight.

## State and backups

All persistent state is on disk, by default under `backend/data/`:

| State | Where it comes from |
|---|---|
| Dense index | `FAISS_INDEX_PATH` |
| Keyword index | `BM25_DB_PATH` (SQLite FTS5) |
| Embedding cache | `CACHE_PATH` |
| Model registry, chains, encrypted keys | `backend/data/model_hub/model_hub.db` |
| Generated mind maps | `MINDMAP_DIR` |

To back up: stop the backend, copy the data directory, start the backend. **Store
`CREDENTIAL_ENCRYPTION_KEY` separately from the backup**; a backup that contains
both the database and the key defeats the encryption.

## Container deployment (not yet available)

`docker-compose.yml` is checked in, but **it cannot build**: it declares
`build: ./backend` and `build: ./frontend`, and neither directory contains a
`Dockerfile`. Treat the compose file as a starting point rather than a working
deployment. Run from source with `make dev-backend` and `npm run dev` in the
meantime.

## Upgrading

Back up first, then `git pull`, `make install`, and restart. Run `make lint` and
the test suites if you have local changes.
