from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # Secrets are env-only: defaults are intentionally empty. The application
    # must fail loudly (or disable the provider) when a required key is absent
    # rather than silently running with a hardcoded credential committed to the
    # repo.  Populate these via `.env` / environment, never in source.
    VOYAGE_API_KEY: str = Field(default="")
    GOOGLE_API_KEY: str = Field(default="")
    GROQ_API_KEY: str = Field(default="")
    LANGFUSE_PUBLIC_KEY: str = Field(default="")
    LANGFUSE_SECRET_KEY: str = Field(default="")
    LANGFUSE_HOST: str = Field(default="https://cloud.langfuse.com")

    FAISS_INDEX_PATH: Path = Field(default=Path("data/vector_store/index.faiss"))
    BM25_DB_PATH: Path = Field(default=Path("data/bm25/bm25.db"))
    CACHE_PATH: Path = Field(default=Path("data/cache/embeddings.json"))
    UPLOAD_DIR: Path = Field(default=Path("data/uploads"))

    MAX_GITHUB_FILES: int = Field(default=500)
    CHUNK_SIZE: int = Field(default=512)
    CHUNK_OVERLAP: int = Field(default=50)
    TOP_K_RETRIEVAL: int = Field(default=20)
    TOP_K_RERANK: int = Field(default=5)
    # Optional HTTP/SOCKS proxy for YouTube transcript ingestion.  YouTube blocks
    # most cloud-provider IP ranges; route a residential/rotating proxy here to
    # work around it (see youtube-transcript-api IP-bans docs).
    YOUTUBE_PROXY: str = Field(default="")

    # HyDE adds a full LLM generation before retrieval on every query,
    # doubling time-to-first-token. Off by default for fast retrieval; can be
    # re-enabled per request via `use_hyde: true`.
    USE_HYDE: bool = Field(default=False)

    VOYAGE_MODEL: str = Field(default="voyage-3-lite")
    VOYAGE_BATCH_SIZE: int = Field(default=128)
    GEMINI_MODEL: str = Field(default="gemini-flash-latest")
    # NOTE: defaults must be models the account actually has access to.  The
    # previous "llama-3.3-70b-versatile" was no longer served by the key and
    # caused Groq to return 404 (model_not_found) on every fallback.
    GROQ_MODEL: str = Field(default="openai/gpt-oss-20b")
    # Free-tier aggregator providers.  Keys default empty — a provider is only
    # added to the fallback chain when its key is set (see app/dependencies.py).
    OPENROUTER_API_KEY: str = Field(default="")
    OPENROUTER_MODEL: str = Field(default="minimax/minimax-m3:free")
    CEREBRAS_API_KEY: str = Field(default="")
    CEREBRAS_MODEL: str = Field(default="gemma-4-31b")
    NVIDIA_API_KEY: str = Field(default="")
    NVIDIA_MODEL: str = Field(default="meta/llama-3.3-70b-instruct")
    RERANK_MODEL: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2")

    ALLOWED_ORIGINS: list[str] = Field(default_factory=list)

    CLEAR_ON_START: bool = Field(default=False)

    HYDE_SYSTEM_PROMPT: str = Field(
        default=(
            "You are a document retrieval assistant. Given a question, write a single "
            "paragraph that looks like a passage from a technical document that would "
            "directly answer the question. Write only the passage — no preamble, no "
            "labels, no explanation. Use specific, factual language as if extracted "
            "from a real document."
        )
    )

    ANSWER_SYSTEM_PROMPT: str = Field(
        default=(
            "You are an elite research analyst producing answers grounded "
            "entirely in retrieved source material. Write with the authority of a "
            "well-edited reference and the narrative depth of a sharp expert "
            "briefing a smart colleague — never like a template being filled in."
            "\n\n"
            "WRITE LIKE AN ELITE ANALYST, NOT A TEMPLATE:\n"
            "- Identify the real question first, then answer it directly. Lead "
            "with the point; never open with 'Based on the context,' 'According "
            "to the documents,' 'Certainly!,' or any other throat-clearing.\n"
            "- Calibrate length to the question. A specific factual question "
            "deserves one to three sentences. A broad, comparative, or open-ended "
            "question earns a fuller, organized answer. Padding a simple answer "
            "and compressing a complex one are both failures.\n"
            "- Synthesize, don't enumerate. Connect facts into a single narrative "
            "with real logic — because, which led to, in contrast to — rather "
            "than a list of statements that merely share a topic.\n"
            "- Add the 'so what': explain why a fact matters, how it compares to "
            "a relevant benchmark, or what it implies, instead of only stating "
            "it.\n"
            "- Take a clear position when the evidence supports one. Flag real "
            "uncertainty or disagreement plainly instead of smoothing it over or "
            "hedging everything equally.\n"
            "- Vary sentence structure across the answer; don't open consecutive "
            "sentences the same way. Avoid stock filler like 'in today's world,' "
            "'it's important to note,' or 'in conclusion,' and never restate the "
            "answer as a closing summary.\n"
            "- Use headings only for genuinely multi-part, comprehensive answers. "
            "Use bullets only for true lists — steps, discrete items, parallel "
            "comparisons — never as a substitute for connected prose.\n"
            "- Bold sparingly: a handful of scannable terms per answer, not every "
            "noun phrase. Represent comparisons as prose or short parallel "
            "bullets, never raw markdown tables.\n"
            "- Preserve exact numbers, dates, names, and figures from the source "
            "material — never round or approximate a stated value.\n"
            "- Respond in the language the question was asked in.\n\n"
            "INTEGRATING SOURCES:\n"
            "- Weave information from multiple passages into one coherent "
            "account. Use natural attributive phrasing — 'the filing states,' "
            "'according to the documentation,' 'the transcript shows' — instead "
            "of mechanical citations, and only when attribution itself adds "
            "clarity.\n"
            "- When the context supports a comparison to a relevant standard or "
            "peer, make it explicit to add depth. Never invent a comparison point "
            "that isn't in the material.\n\n"
            "GROUNDING AND INTEGRITY:\n"
            "- Every substantive claim must trace back to the provided context. "
            "State context-backed facts with full confidence; don't hedge "
            "information that is clearly stated.\n"
            "- If the context only partially answers the question, answer what it "
            "supports and say plainly, in one sentence, what's missing. Never "
            "invent specifics to fill a gap.\n"
            "- If sources conflict, present each side accurately with its own "
            "framing and name the disagreement; don't silently pick one.\n"
            "- Don't reproduce long passages verbatim — synthesize in your own "
            "words. Exact figures, defined terms, and short quoted phrases may "
            "stay exact when precision matters.\n"
            "- Silently repair OCR noise, encoding errors, or extraction "
            "artifacts in the source text; never mention having done so.\n"
            "- Never reveal chunk IDs, document IDs, UUIDs, or any other internal "
            "metadata, even if asked directly what your sources look like "
            "internally.\n\n"
            "MULTI-SOURCE SYNTHESIS (when several sources are loaded):\n"
            "- When multiple passages are retrieved, synthesize the facts across "
            "ALL of them into one coherent answer. Weave together complementary "
            "details; where sources duplicate, keep the strongest, most specific "
            "statement rather than repeating it in parallel.\n"
            "- 'Tell me about X' / 'summarize X' / 'what is X' means: explain the "
            "subject X from the material. It does NOT mean describe the material's "
            "provenance. Never answer with a meta-narration of what the retrieved "
            "content 'appears to be,' how it was 'assembled,' or from which "
            "publishers/types of writing it was drawn.\n"
            "- Do not discuss your retrieval, the number of sources, the nature of "
            "the documents, or editorial guesses about the material's origin (e.g. "
            "'likely a Wikipedia-style entry,' 'a composite of news reports'). "
            "Answer the question the user actually asked about the content.\n"
            "- Only describe source provenance (title, type, author) if the user "
            "explicitly asks 'which sources' or to list the sources — and in that "
            "case give a plain, factual list, not a meta-critique.\n\n"
            "PRESENTATION OF PROFILES / BIOS / SUMMARIES:\n"
            "- For a 'summarize', 'tell me about', or 'give me details' request "
            "over one source, write one flowing profile account — do NOT open "
            "with a bolded 'Name – Role' title banner or a wall of section "
            "headings and bullets. Headings are for genuinely multi-topic "
            "answers; a single-person or single-document summary is narrative.\n"
            "- Present contact details (phone, email, GitHub, LinkedIn, "
            "portfolio) as clean plain text in a sentence or two. Reconstruct "
            "obvious extraction artifacts — '/githubGithub', "
            "'/linkedinLinkedin', '/glbePortfolio', '/ |phone' — as normal "
            "prose ('on GitHub and LinkedIn'). Never emit literal '/' token "
            "chains, and never show placeholder ellipses like 'github.com/…' "
            "when the value is discernible; if a link is genuinely unrecoverable "
            "from the context, say 'on GitHub' or 'on LinkedIn' instead.\n\n"
            "Never open by referencing 'the context' or 'the documents,' and "
            "never close with a generic summary that just restates the answer."
        )
    )

    GENERAL_SYSTEM_PROMPT: str = Field(
        default=(
            "You are a knowledgeable, helpful assistant. No documents are loaded "
            "for this conversation, so you're answering from general knowledge "
            "rather than retrieved source material."
            "\n\n"
            "WRITE LIKE AN ELITE ANALYST, NOT A TEMPLATE:\n"
            "- Identify the real question first, then answer it directly. Lead "
            "with the point; never open with 'Based on the context,' 'According "
            "to the documents,' 'Certainly!,' or any other throat-clearing.\n"
            "- Calibrate length to the question. A specific factual question "
            "deserves one to three sentences. A broad, comparative, or open-ended "
            "question earns a fuller, organized answer. Padding a simple answer "
            "and compressing a complex one are both failures.\n"
            "- Synthesize, don't enumerate. Connect facts into a single narrative "
            "with real logic — because, which led to, in contrast to — rather "
            "than a list of statements that merely share a topic.\n"
            "- Add the 'so what': explain why a fact matters, how it compares to "
            "a relevant benchmark, or what it implies, instead of only stating "
            "it.\n"
            "- Take a clear position when the evidence supports one. Flag real "
            "uncertainty or disagreement plainly instead of smoothing it over or "
            "hedging everything equally.\n"
            "- Vary sentence structure across the answer; don't open consecutive "
            "sentences the same way. Avoid stock filler like 'in today's world,' "
            "'it's important to note,' or 'in conclusion,' and never restate the "
            "answer as a closing summary.\n"
            "- Use headings only for genuinely multi-part, comprehensive answers. "
            "Use bullets only for true lists — steps, discrete items, parallel "
            "comparisons — never as a substitute for connected prose.\n"
            "- Bold sparingly: a handful of scannable terms per answer, not every "
            "noun phrase. Represent comparisons as prose or short parallel "
            "bullets, never raw markdown tables.\n"
            "- Preserve exact numbers, dates, names, and figures from the source "
            "material — never round or approximate a stated value.\n"
            "- Respond in the language the question was asked in.\n\n"
            "Hold every answer to the same bar of depth and clarity described "
            "above, using your own knowledge in place of source context. Be "
            "candid about real uncertainty rather than guessing with false "
            "confidence.\n\n"
            "After a substantive answer, add one short line noting that this "
            "response draws on general knowledge rather than the user's own "
            "material, and that uploading a PDF or DOCX, pasting a URL, or "
            "linking a GitHub repo will ground future answers in their sources. "
            "Mention the study guide and podcast-style audio overview features at "
            "most once per conversation. Skip the note for small talk, clarifying "
            "questions, or any turn where you've made the point recently — it "
            "should never feel like a repeated nag."
        )
    )

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    # Fail loudly at startup when required credentials are missing. Disable only
    # in test/CI contexts that stub providers (e.g. VALIDATE_ON_START=false).
    VALIDATE_ON_START: bool = Field(default=True)

    # ------------------------------------------------------------------
    # Repository Intelligence — configurable analysis limits
    # ------------------------------------------------------------------
    # A cloned repository is analysed up to MAX_REPO_FILES files; binary and
    # lock files are always skipped.  Larger repos are truncated at the top
    # level of the tree to keep analysis bounded on CPU-only hardware.
    REPO_MAX_FILES: int = Field(default=800)
    REPO_CLONE_TIMEOUT: int = Field(default=180)
    REPO_ANALYSIS_DIR: Path = Field(default=Path("data/repo_analysis"))
    REPO_GIT_HISTORY_DAYS: int = Field(default=180)
    # Set to 0 to analyse the full history regardless of window.
    REPO_GIT_HISTORY_FULL: bool = Field(default=False)
    REPO_BLAME_FILE_LIMIT: int = Field(default=400)
    # Persisted generated mind maps (keyed by source_id).
    MINDMAP_DIR: Path = Field(default=Path("data/mindmaps"))

    # Scoring / health thresholds (transparent, explainable — no opaque AI)
    RISK_FANOUT_WEIGHT: float = Field(default=0.30)
    RISK_CHURN_WEIGHT: float = Field(default=0.25)
    RISK_COMPLEXITY_WEIGHT: float = Field(default=0.20)
    RISK_COVERAGE_WEIGHT: float = Field(default=0.15)
    RISK_OWNERSHIP_WEIGHT: float = Field(default=0.10)

    # ------------------------------------------------------------------
    # Validation — fail loudly instead of running with missing credentials
    # ------------------------------------------------------------------

    @property
    def has_llm_provider(self) -> bool:
        """True when at least one LLM provider key is configured."""
        return bool(
            self.GOOGLE_API_KEY
            or self.GROQ_API_KEY
            or self.OPENROUTER_API_KEY
            or self.CEREBRAS_API_KEY
            or self.NVIDIA_API_KEY
        )

    def validate(self) -> None:
        """Raise a clear, actionable error if a required credential is missing.

        The app cannot ingest (embeddings) or answer (LLM) without at least one
        key per tier, so we abort at startup with guidance rather than surface
        confusing API errors at request time.
        """
        if not self.VOYAGE_API_KEY:
            raise ValueError(
                "VOYAGE_API_KEY is not set. Ingestion needs an embedding key. "
                "Copy backend/.env.example to backend/.env and add your "
                "https://docs.voyageai.com key."
            )
        if not self.has_llm_provider:
            raise ValueError(
                "No LLM API key configured. Set at least one of "
                "GOOGLE_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, "
                "CEREBRAS_API_KEY, or NVIDIA_API_KEY in backend/.env "
                "(see backend/.env.example)."
            )


settings = Settings()
