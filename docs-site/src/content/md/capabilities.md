# Capabilities

Browse what ContextForge can do, by starting point. Each links to the guide that
covers it.

## A research question

- **Literature and evidence** — ingest papers and extract passages with citations.
- **Multi-source answers** — select several sources and get an answer grounded
  across all of them, with source-aware diversification.

## A dataset or document set

- **Tables and text** — chunked by token count and cleaned before embedding.
- **Code** — AST-aware chunking keeps whole symbols together.

## Scientific and technical files

- **PDF and DOCX** — page-by-page text extraction with an extraction verdict.
- **GitHub repositories** — REST tree walk plus code-aware chunking, capped at
  500 files.

## A result to communicate

- **Notes** — a structured Markdown note written from a selection.
- **Mind maps** — the same selection drawn as an interactive SVG diagram.
- **Studio** — architecture diagrams, security scans, dependency inventory and
  health hotspots for a repository.

## A larger investigation

- **Projects** — a private workspace with its own sources and chat history.
- **Chat history that stays true** — each message records the exact source
  selection it was answered with.

## An integration

- **SDK and local API** — everything is reachable over REST and SSE, with a live
  OpenAPI spec at `/docs`.
- **Bring your own providers** — nine hosted providers or any local
  OpenAI-compatible server, chained with failover.
