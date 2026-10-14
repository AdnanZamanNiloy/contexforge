# Configuration

All configuration lives in `backend/app/config/settings.py` via
`pydantic-settings`. Set values through environment variables or a `.env` file in
`backend/`. A documented template ships as `backend/.env.example`.

## Required

None. `.env` carries paths, chunking sizes, optional tracing, and the Fernet key
used to encrypt Model Hub credentials.

## Recommended

| Variable | Description |
|---|---|
| `CREDENTIAL_ENCRYPTION_KEY` | Fernet key protecting provider keys stored in the Model Hub. Without it those keys are written to `backend/data/model_hub/model_hub.db` **in plaintext** and the app warns once. |

Generate a key once and keep it somewhere safe:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Losing the key does not corrupt anything: affected models report
`has_api_key: false` and ask for their key again.

## Provider credentials are not environment variables

Every provider key, embedding included, is entered in the **Model Hub UI** and
stored in SQLite. `settings.py` reads no provider credential at all.

A model with no key raises a named error pointing at Model Hub.
`dependencies.get_llm()` returns a not-configured sentinel until the Model Hub
serves something.

## Optional

| Variable | Default | Description |
|---|---|---|
| `LANGFUSE_PUBLIC_KEY` | — | Langfuse tracing (public key) |
| `LANGFUSE_SECRET_KEY` | — | Langfuse tracing (secret key) |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse host |
| `VOYAGE_MODEL` | `voyage-3-lite` | Voyage embedding model |
| `GEMINI_MODEL` | `gemini-flash-latest` | Default model ID for a Gemini entry |
| `RERANK_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Cross-encoder used for reranking |
| `CHUNK_SIZE` | `512` | Text chunk size (tokens) |
| `CHUNK_OVERLAP` | `50` | Chunk overlap (tokens) |
| `TOP_K_RETRIEVAL` | `20` | Chunks retrieved per query |
| `TOP_K_RERANK` | `5` | Chunks passed to the LLM |
| `USE_HYDE` | `false` | Enable HyDE query expansion |
| `FAISS_INDEX_PATH` | `data/vector_store/index.faiss` | FAISS index path |
| `ALLOWED_ORIGINS` | `["http://localhost:5173"]` | CORS allowed origins (JSON list) |
| `LOG_LEVEL` | `INFO` | Logging level |

## Frontend

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend API URL. Vite reads it at **build time**, so rebuild after changing it |
