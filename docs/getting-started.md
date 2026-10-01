# Getting started

A walkthrough of ingesting your first source, per format, and reading the result.
Assumes the backend is on `:8000` and the frontend on `:5173`.

## Before anything else

Nothing goes in `backend/.env`. The app starts and every screen loads with no
configuration at all; only the actions that need a provider fail, and each one
names the model that is missing its key.

Two things must be true before you can ask a question, and both live in the UI:

1. **An embedding model with a key.** Model Hub (`/models`) → add a model, paste
   its key, save. Ingestion cannot embed anything until this exists.
2. **A chat model in service.** Same page, then put it under **Serving**. Until
   you do, every generation raises `NotConfiguredError`.

There is no environment fallback by design. A key deleted in the app is gone; the
app will not quietly reuse an old one.

> **First ingest on the Voyage free tier is slow.** Embeddings are throttled to one
> request per 21 seconds to stay under 3 requests/minute, and each request is
> sized to stay under 10k tokens. A large PDF can take a few minutes on first
> ingest. The text is cached on disk afterwards, so re-ingesting the same content
> is fast. This is the single most common "is it stuck?" moment.

## The shape of every ingest

All six formats land in the same place: chunks → embeddings → FAISS + BM25. The
differences are only in how the text is extracted.

| Format | How to add it | Extraction | Limits |
|---|---|---|---|
| **PDF** | `Add Source` → drop the file | `pypdf`, page by page | 50 MB. Scanned/image-only PDFs yield no text — see [troubleshooting](troubleshooting.md) |
| **DOCX** | `Add Source` → drop the file | `python-docx`, paragraphs only | 50 MB. **Tables are not extracted** — convert to PDF or plain text first |
| **Web page** | `Add Source` → paste the URL | `trafilatura` (boilerplate stripping) | Public pages only. Paywalls and JS-rendered SPAs often come back nearly empty |
| **YouTube** | `Add Source` → paste the watch URL | Transcript API | English (`en`) and Hindi (`hi`) tracks only. Needs captions present |
| **GitHub repo** | `Add Source` → paste the repo URL | REST tree walk + AST chunking | 500 files max. Lock files, binaries and vendored dirs are skipped |
| **Plain text** | `Add Source` → paste into the box | Raw decode | Cheapest way to sanity-check the pipeline |

## Confirming it worked

Ingestion returns success even when extraction found almost nothing — a scanned
PDF and a healthy one are indistinguishable in the source list. **Check the
extraction verdict** before trusting an answer:

- In the sidebar, open the source's detail panel. It reports text length, page
  counts, whether pages had no text layer, detected language, and the indexed
  file list for a repo.
- `GET /ingest/source/{id}/content` returns the actual chunk text that retrieval
  would quote. If this is thin, the answer will be too.

Then ask something answerable **only** from that source. If the answer comes back
general, retrieval did not find your content — see
[troubleshooting](troubleshooting.md).

## Narrowing a large source

Retrieval never reads everything. The sidebar meter shows selected tokens against
the prompt budget, and three depths map to real limits:

| Depth | Max sources | Retrieved | Reranked to |
|---|---|---|---|
| `focused` | 2 | 20 | 5 |
| `balanced` | 6 | 40 | 12 |
| `broad` | 25 | 80 | 25 |

A depth the selection cannot justify is reduced, and the meter says so rather
than reporting a width you did not get. Start at `focused` for one large document;
go `broad` when the answer needs to span several.

## Turning a selection into something reusable

Ask a question and you get an answer. Select the same sources again and you can
get something you keep:

- **Note** (`POST /note/generate`) — a structured Markdown note, cached per
  selection, downloadable as a file.
- **Mind map** (`POST /mindmap/generate`) — the same selection drawn as a diagram.

Both key their cache on the selection, so a single source reuses its own id and
several share a sorted composite key. Change the selection and it regenerates.

## Keeping the answer honest

- **Confidence** is server-side and reflects grounding, not fluency.
- **The Sources panel** shows which passages actually answered. Read it.
- ContextForge can still be wrong. It cites what it found; it does not verify it.
