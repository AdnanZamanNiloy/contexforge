# FAQ

## Does my data leave my machine?

Only what you configure. ContextForge is local-first, not offline-only. With a
local embedder, a local chat server, and tracing off, the only outbound traffic is
whatever you ask it to fetch. See [Security & privacy](/docs/security).

## Do I need API keys in the environment?

No. No provider credential is read from the environment at all. Keys are entered
in the **Model Hub UI** and stored in SQLite, encrypted at rest when
`CREDENTIAL_ENCRYPTION_KEY` is set.

## Why does nothing answer until I configure a model?

Generation is disabled on purpose. `get_llm()` returns a not-configured sentinel
rather than falling back to a provider that happens to have a key in the
environment. A model with no saved key fails with a named error pointing at Model
Hub.

## Can I run it fully offline?

Yes for models. Register local embedding and chat models pointing at a local
OpenAI-compatible server (llama.cpp, Ollama, vLLM, LM Studio). Remote *sources*
(web pages, YouTube transcripts, GitHub repositories) still need network access to
fetch.

## Which models are supported?

Nine hosted providers — OpenAI, Google Gemini, Groq, OpenRouter, Cerebras, NVIDIA
NIM, Together, Mistral, DeepSeek — plus any local OpenAI-compatible server. Chain
them and the pipeline fails over down the chain. See
[Model Hub](/docs/model-hub).

## Why is my first ingest slow?

The Voyage free tier throttles embeddings to one request per 21 seconds. A large
PDF can take minutes on first ingest; the text is cached afterwards. See
[Troubleshooting](/docs/troubleshooting).

## Does it support multi-user accounts?

No. There are no user accounts, roles or built-in authentication. If ContextForge
is reachable by anyone other than you, put it behind an authenticating reverse
proxy and bind the backend to `127.0.0.1`.

## Is there a Docker image?

Not yet. `docker-compose.yml` is checked in but cannot build — no `Dockerfile`
exists in either half. Run from source.

## How do I cite an answer?

Every answer shows which ingested chunks were used, with scores and metadata, plus
per-stage latency and server-side confidence. Use the **Sources** panel to read the
exact passages that answered.

## Where is state stored?

On disk under `backend/data/`: the FAISS index, the SQLite FTS5 index, the
embedding cache, and the SQLite stores for projects, chat, notes, mind maps and
the model hub. See [Deployment](/docs/deployment) for backups.
