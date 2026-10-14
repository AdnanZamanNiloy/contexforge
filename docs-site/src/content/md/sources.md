# Sources

Ingesting your first source, per format, and reading the result.

All six formats land in the same place: chunks → embeddings → FAISS + BM25. The
differences are only in how the text is extracted.

| Format | How to add it | Extraction | Limits |
|---|---|---|---|
| **PDF** | `Add Source` → drop the file | `pypdf`, page by page | 50 MB. Scanned/image-only PDFs yield no text |
| **DOCX** | `Add Source` → drop the file | `python-docx`, paragraphs only | 50 MB. **Tables are not extracted** |
| **Web page** | `Add Source` → paste the URL | `trafilatura` (boilerplate stripping) | Public pages only |
| **YouTube** | `Add Source` → paste the watch URL | Transcript API | English (`en`) and Hindi (`hi`) tracks only |
| **GitHub repo** | `Add Source` → paste the repo URL | REST tree walk + AST chunking | 500 files max |
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
general, retrieval did not find your content.

## Source inspection by design

A source that extracted badly is indistinguishable from a healthy one until you
look: it appears, gets cited, and answers questions as though it had been read.

- `GET /ingest/source/{id}` — an **extraction verdict** (no text at all, some
  pages with no text layer, suspiciously little text), plus page counts, detected
  language, and the indexed file list for a repository.
- `GET /ingest/source/{id}/content` — the indexed chunk text retrieval would quote.

There is deliberately no original-file download. `UPLOAD_DIR` is configured but
unused: ContextForge indexes uploads without retaining the bytes, so the panel
says so rather than offering a control that cannot work.

`PATCH /ingest/source/{id}` renames a source; `DELETE` removes it.
