# Troubleshooting

Symptoms first, because that is how you arrive here. Each entry says what is
actually happening, not just what to change.

## Nothing answers — `NotConfiguredError`

> "No LLM model is being served."

Generation is disabled on purpose. `get_llm()` returns a sentinel rather than
falling back to a provider that happens to have a key in the environment.

**Fix:** Model Hub (`/models`) → add a model → **Serving** → select it or a chain.
Same for embeddings: nothing can be ingested without a served embedder.

## The backend will not start

It always starts. There is no credential gate, because no provider key is read
from the environment; keys live in the Model Hub. If startup genuinely fails, the
traceback names a missing file, port or import, not a missing key.

If a *query* fails with a message naming an API key, that model has no key
saved: Model Hub (`/models`) → open the model → paste the key → save. The error
names the model precisely so you know which one.

## First ingest appears to hang

Almost always the **Voyage free tier**: embeddings are throttled to one request
per 21 seconds (3 RPM) and batched to stay under 10k tokens per request. A large
PDF can take minutes.

It is not stuck. Results are cached on disk in `backend/data/cache/embeddings.json`,
so identical text is not re-embedded.

**To go faster:** use a paid Voyage tier, or register a local embedding model in
the Model Hub (`runtime: local`, BAAI/bge-base-en-v1.5) — no API calls at all.
Note this is an opt-in choice, not an automatic fallback.

## A source ingests but answers come back generic

The source is indexed and retrieval is simply not finding it. Check in this
order:

1. **Did extraction actually get text?** Open the source detail panel and read
   the extraction verdict. A scanned PDF reports pages with no text layer.
2. **Look at the chunk text.** `GET /ingest/source/{id}/content` returns exactly
   what retrieval would quote. If it is thin or nonsense, the problem is upstream.
3. **Raise the depth.** The meter shows selected tokens against the budget; at
   `focused` only the top 5 reranked chunks reach the prompt.
4. **Ask something specific.** Questions with rare, distinctive terms retrieve
   far better than broad ones — this is BM25 plus dense retrieval doing its job.

## A scanned PDF returns nothing

An image-only PDF has no text layer, so there is nothing to chunk. `pypdf` will
not OCR it.

**Fix:** run OCR first (OCRmyPDF, `ocrmypdf` in place), or supply a text export
instead. The panel will say "no text at all" rather than silently indexing nothing.

## DOCX tables are missing

Documented behaviour, not a bug: `python-docx` reads paragraphs only. Tables,
headers and footers are not extracted.

**Fix:** convert to PDF or plain text before ingesting.

## A GitHub repository is missing files

- **500-file cap.** `MAX_GITHUB_FILES` stops very large monorepos.
- Lock files, binaries and vendored directories are skipped by design.
- Private repositories need no setup and will not work — the loader is
  unauthenticated. Use a public URL, or clone locally and ingest the text.

Check the **file listing** in the source detail panel to see what was actually
indexed.

## A web page came back nearly empty

`trafilatura` strips boilerplate, which also removes content that *looks* like
chrome. JavaScript-rendered SPAs (most modern web apps) often return almost
nothing because the HTML has no content until a script runs.

**Fix:** use the page's print/plain view, or paste the text directly via the
plain-text option.

## A YouTube video has no transcript

Only `en` and `hi` tracks are requested. Auto-generated captions count, but the
video must actually have them — private, members-only and some region-locked
videos do not.

## The answer streams, then errors partway

Mid-stream the provider is **not** switched. Falling over to another provider
after tokens have been emitted would splice two different answers together, so
the error is re-raised instead. Failover happens only when a provider fails
*before* its first token.

Retry. If it persists, test the chain in the Model Hub — it reports which member
answered and how long each took.

## Every request is slow, and providers look rate-limited

A provider returning `429` is put in cooldown (honouring `Retry-After`), capped
at five minutes, and skipped on the next query. If every provider is cooling
down, the one that frees up soonest is tried anyway.

**Check** Serving is a chain rather than a single model, and **test** it in the
Model Hub. Two failures worth knowing:

- `429` is deliberately **not** retried internally. Quotas do not recover inside
  one request, so retrying only adds delay.
- If the **last** configured member is in cooldown and an earlier one fails, the
  chain can raise instead of falling back further. Known sharp edge in
  `fallback_llm.py`.

## A provider key was stored, then stops working

Model Hub keys are Fernet-encrypted when `CREDENTIAL_ENCRYPTION_KEY` is set.
Ciphertexts are self-describing (`enc:v1:`), so a database holding a mix of
plaintext and encrypted rows still reads correctly.

If the encryption key is lost or changed, affected keys report
`has_api_key: false` and the UI asks for them again — deliberately, because
handing undecryptable ciphertext to a provider would fail in a far more
confusing way.

**Without** `CREDENTIAL_ENCRYPTION_KEY`, keys are stored in plaintext in
`backend/data/model_hub/model_hub.db` and a warning is logged once.

## A source will not upload

- **50 MB hard cap** per file.
- MIME type must match: `application/pdf` for PDF, or the Word
  `openxmlformats` / `msword` types for DOCX. Renaming a `.txt` to `.pdf` is
  rejected — this is why plain text has its own option.

## Everything looks stale after a restart

State is on disk under `backend/data/`: FAISS index, BM25 index, and the SQLite
stores (projects, chat, notes, mind maps, model hub). It survives restarts by
design. With Docker Compose, that directory is a named volume — deleting the
volume deletes your knowledge base.

## Running checks locally

```bash
make lint          # ruff, prettier/eslint, and the README-vs-spec check
make test          # pytest + vitest
python backend/scripts/check_readme_api.py   # README API list vs the OpenAPI spec
```

## Still stuck

`GET /health` confirms the process is up. `backend/data/` holds every store, and
the backend logs the reason for most failures above at `WARNING` or `ERROR`.
