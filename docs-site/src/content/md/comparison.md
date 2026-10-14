# How it compares

These tools overlap, but they optimise for different things. This page is here to
help you choose — including when **not** to choose ContextForge.

> **ContextForge optimises for auditable grounding for one person or a small
> team**, plus analysis of code repositories. It does not try to match enterprise
> connector breadth, multi-user administration, or layout-aware parsing of complex
> documents.

## At a glance

| | **ContextForge** | **Gemini Notebook** | **AnythingLLM** | **Open WebUI** |
|---|---|---|---|---|
| **Shape** | Source-grounded RAG workspace plus repository analyzers | Hosted research notebook | All-in-one private chat, RAG and agent app | General chat UI with built-in RAG |
| **Runs** | Your machine (from source today) | Google's cloud only | Desktop app or Docker | Self-hosted |
| **License** | MIT | Proprietary | MIT | Custom (Open WebUI License) |
| **Models** | Bring your own: nine hosted providers or any local OpenAI-compatible server | Gemini | 20+ providers | Ollama and OpenAI-compatible |
| **Retrieval stack** | BM25 (FTS5) + FAISS flat → RRF → cross-encoder; optional HyDE | Not publicly detailed | Pluggable vector database | Hybrid BM25 + vector, optional rerank |
| **Knowledge sources** | PDF, DOCX, TXT, web, YouTube, GitHub | Files, Drive, pasted text, websites, YouTube | Uploads, URLs, GitHub, GitLab, YouTube, Confluence | Uploads and knowledge bases |

## Capability matrix

| Capability | ContextForge | Gemini Notebook | AnythingLLM | Open WebUI |
|---|:-:|:-:|:-:|:-:|
| Self-hostable, data stays on your hardware | ✅ | ➖ | ✅ | ✅ |
| Not locked to one model vendor | ✅ | ➖ | ✅ | ✅ |
| Inline citations to source passages | ✅ | ✅ | ✅ | ✅ |
| Multi-user accounts and access control | ➖ | ◐ | ✅ | ✅ |
| Agents, tool use or MCP | ➖ | ➖ | ✅ | ✅ |
| Repository analysis (architecture, security, health) | ✅ | ➖ | ➖ | ➖ |
| Selection cost preview with depth presets | ✅ | ➖ | ➖ | ➖ |
| Per-answer confidence and per-stage latency | ✅ | ➖ | ➖ | ➖ |

✅ built in · ◐ partial, or depends on plan or edition · ➖ not offered, or not
documented in the public material reviewed.

The last three rows are ContextForge's design bets. A ➖ elsewhere means "not a
documented feature", not "impossible to build".

## What is distinctive by design

1. **Selection pricing before you ask.** The estimator makes no embedding,
   retrieval, rerank or generation call, so it is free to re-run on every change.
2. **Depth presets that say what they did.** A depth the selection cannot justify
   is reduced *and the response says so*; sources the depth will not read are
   named and struck through.
3. **History that stays true.** Each chat message records the exact source
   selection it was answered with.
4. **Extraction verdicts.** A source with no text, missing text layers or
   suspiciously little text is flagged instead of answering as though it had been
   read.
5. **Repository Studio.** Architecture diagrams where every code node carries its
   file path, OSV advisories, `ast-grep` findings, dependency inventory and ranked
   hotspots.
6. **Failover with defined semantics.** Rate-limited providers cool down, providers
   that fail before the first token fall through, and a mid-stream failure
   re-raises rather than switching underneath you.
7. **No ambient credentials.** Keys are entered in the UI, encrypted at rest when
   `CREDENTIAL_ENCRYPTION_KEY` is set, and never appear in a response.

## Where ContextForge is behind today

- No multi-user accounts, roles or built-in authentication.
- No SaaS connectors (Slack, Confluence, Jira and similar) and no scheduled
  re-sync of sources.
- No OCR or layout-aware parsing: scanned PDFs are detected and flagged, not read.
- No agents, workflow builder or MCP.
- No container image yet; you run from source.
- English-only default reranker; a single exact (flat) vector index sized for
  personal and small-team corpora.
- Early-stage project with a single maintainer and no published retrieval
  benchmarks yet.

## Libraries, not products

LlamaIndex, LangChain and Haystack are libraries for *building* RAG systems;
ContextForge is a finished application you run. If you need to embed retrieval
inside your own product, start with a library or an API layer. If you need a
workspace to ask questions of your sources and check the answers, start here.
