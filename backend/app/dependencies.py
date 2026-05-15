"""
dependencies.py — FastAPI dependency wiring for ContextForge.

All singleton factories use @lru_cache so each component is constructed
exactly once per process.  Shutdown cleanup is handled by the lifespan
context manager in main.py via close_all().
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Dict

from app.config.settings import Settings
from app.services.ingest_service import IngestService
from app.services.query_service import QueryService
from core.chunking.code_chunker import CodeChunker
from core.chunking.text_chunker import TextChunker
from core.embedding.voyage_embedder import VoyageEmbedder
from core.generation.fallback_llm import FallbackLLM
from core.generation.gemini_llm import GeminiLLM
from core.generation.groq_llm import GroqLLM
from core.generation.prompt_builder import PromptBuilder
from core.ingestion.base_loader import BaseLoader
from core.ingestion.docx_loader import DocxLoader
from core.ingestion.github_loader import GitHubLoader
from core.ingestion.pdf_loader import PDFLoader
from core.ingestion.text_loader import TextLoader
from core.ingestion.web_loader import WebLoader
from core.orchestrator import Orchestrator
from core.retrieval.bm25_retriever import BM25Retriever
from core.retrieval.dense_retriever import DenseRetriever
from core.retrieval.hybrid_retriever import HybridRetriever
from core.retrieval.hyde import HydeQueryExpander
from core.retrieval.reranker import Reranker
from core.storage.bm25_index import BM25Index
from core.storage.faiss_store import FaissStore

__all__ = [
    "get_settings",
    "get_ingest_service",
    "get_query_service",
    "close_all",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Settings — single source of truth for all factories
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings (loaded from .env once)."""
    return Settings()


# ---------------------------------------------------------------------------
# Infrastructure singletons
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_embedder() -> VoyageEmbedder:
    # FIX #5 — use get_settings() everywhere instead of constructing Settings()
    settings = get_settings()
    return VoyageEmbedder(cache_path=settings.CACHE_PATH)


@lru_cache(maxsize=1)
def get_faiss_store() -> FaissStore:
    return FaissStore(index_path=get_settings().FAISS_INDEX_PATH)


@lru_cache(maxsize=1)
def get_bm25_index() -> BM25Index:
    return BM25Index(db_path=get_settings().BM25_DB_PATH)


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    return Reranker()


@lru_cache(maxsize=1)
def get_prompt_builder() -> PromptBuilder:
    return PromptBuilder()


# FIX #3 — chunkers cached so they're not rebuilt on every orchestrator access
@lru_cache(maxsize=1)
def get_text_chunker() -> TextChunker:
    return TextChunker()


@lru_cache(maxsize=1)
def get_code_chunker() -> CodeChunker:
    return CodeChunker()


# ---------------------------------------------------------------------------
# LLM — FIX #2: model strings sourced from settings, not hardcoded defaults
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_llm() -> FallbackLLM:
    settings = get_settings()
    primary = GeminiLLM(model=settings.GEMINI_MODEL)
    fallback = GroqLLM(model=settings.GROQ_MODEL)
    return FallbackLLM(primary=primary, fallback=fallback)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_hyde() -> HydeQueryExpander:
    return HydeQueryExpander(llm=get_llm())


@lru_cache(maxsize=1)
def get_hybrid_retriever() -> HybridRetriever:
    return HybridRetriever(
        bm25=BM25Retriever(get_bm25_index()),
        dense=DenseRetriever(get_faiss_store()),
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_orchestrator() -> Orchestrator:
    return Orchestrator(
        embedder=get_embedder(),
        llm=get_llm(),
        bm25=get_bm25_index(),
        faiss=get_faiss_store(),
        hybrid=get_hybrid_retriever(),
        reranker=get_reranker(),
        prompt_builder=get_prompt_builder(),
        hyde=get_hyde(),
        # FIX #3 — cached instances, not inline constructors
        text_chunker=get_text_chunker(),
        code_chunker=get_code_chunker(),
    )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_loaders() -> Dict[str, BaseLoader]:
    # FIX #1 — typed as Dict[str, BaseLoader] for safety
    return {
        "pdf":    PDFLoader(),
        "docx":   DocxLoader(),
        "web":    WebLoader(),
        "github": GitHubLoader(),
        "text":   TextLoader(),
    }


# ---------------------------------------------------------------------------
# Application services (injected into routes via FastAPI Depends)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_ingest_service() -> IngestService:
    return IngestService(
        orchestrator=get_orchestrator(),
        loaders=get_loaders(),
    )


@lru_cache(maxsize=1)
def get_query_service() -> QueryService:
    return QueryService(orchestrator=get_orchestrator())


# ---------------------------------------------------------------------------
# FIX #4 — graceful shutdown: close all resources that hold connections
# Called from the lifespan context manager in main.py
# ---------------------------------------------------------------------------

async def close_all() -> None:
    """Release all resources acquired by singleton factories.

    Closes:
    - VoyageEmbedder  (httpx.AsyncClient)
    - BM25Index       (sqlite3.Connection)
    """
    logger.info("Shutting down ContextForge — releasing resources.")
    try:
        await get_embedder().aclose()
        logger.debug("VoyageEmbedder closed.")
    except Exception as exc:
        logger.warning("Error closing VoyageEmbedder: %s", exc)

    try:
        get_bm25_index().close()
        logger.debug("BM25Index closed.")
    except Exception as exc:
        logger.warning("Error closing BM25Index: %s", exc)