"""
dependencies.py — FastAPI dependency wiring for ContextForge.

All singleton factories use @lru_cache so each component is constructed
exactly once per process.  Shutdown cleanup is handled by the lifespan
context manager in main.py via close_all().
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config.settings import Settings
from app.mindmap.service import MindMapService
from app.mindmap.storage import MindMapStore
from app.repository_intelligence.analyzer import RepositoryAnalyzer
from app.repository_intelligence.service import RepositoryIntelligenceService
from app.repository_intelligence.storage import RepositoryStore
from app.services.ingest_service import IngestService
from app.services.query_service import QueryService
from core.chunking.code_chunker import CodeChunker
from core.chunking.text_chunker import TextChunker
from core.embedding.voyage_embedder import VoyageEmbedder
from core.generation.cerebras_llm import CerebrasLLM
from core.generation.fallback_llm import FallbackLLM
from core.generation.gemini_llm import GeminiLLM
from core.generation.groq_llm import GroqLLM
from core.generation.nvidia_nim_llm import NvidiaNimLLM
from core.generation.openrouter_llm import OpenRouterLLM
from core.generation.prompt_builder import PromptBuilder
from core.ingestion.base_loader import BaseLoader
from core.ingestion.docx_loader import DocxLoader
from core.ingestion.github_loader import GitHubLoader
from core.ingestion.pdf_loader import PDFLoader
from core.ingestion.text_loader import TextLoader
from core.ingestion.web_loader import WebLoader
from core.ingestion.youtube_loader import YouTubeLoader
from core.orchestrator import Orchestrator
from core.processing.deduplicator import Deduplicator
from core.retrieval.bm25_retriever import BM25Retriever
from core.retrieval.dense_retriever import DenseRetriever
from core.retrieval.hybrid_retriever import HybridRetriever
from core.retrieval.hyde import HydeQueryExpander
from core.retrieval.reranker import Reranker
from core.storage.bm25_index import BM25Index
from core.storage.faiss_store import FaissStore

__all__ = [
    "close_all",
    "get_ingest_service",
    "get_query_service",
    "get_settings",
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
    # Use get_settings() everywhere instead of constructing Settings()
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


# Chunkers cached so they're not rebuilt on every orchestrator access
@lru_cache(maxsize=1)
def get_text_chunker() -> TextChunker:
    return TextChunker()


@lru_cache(maxsize=1)
def get_code_chunker() -> CodeChunker:
    return CodeChunker()


@lru_cache(maxsize=1)
def get_deduplicator() -> Deduplicator:
    return Deduplicator()


# ---------------------------------------------------------------------------
# LLM — FIX #2: model strings sourced from settings, not hardcoded defaults
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_llm() -> FallbackLLM:
    settings = get_settings()
    # Ordered fallback chain — try each in turn, falling through on failure.
    # Gemini and Groq keys are in place; the free aggregators (OpenRouter, NIM,
    # Cerebras) are added only when their API key is configured in .env.
    providers = [
        GroqLLM(model=settings.GROQ_MODEL),
        GeminiLLM(model=settings.GEMINI_MODEL),
    ]
    if settings.OPENROUTER_API_KEY:
        providers.append(OpenRouterLLM(model=settings.OPENROUTER_MODEL))
    if settings.NVIDIA_API_KEY:
        providers.append(NvidiaNimLLM(model=settings.NVIDIA_MODEL))
    if settings.CEREBRAS_API_KEY:
        providers.append(CerebrasLLM(model=settings.CEREBRAS_MODEL))
    return FallbackLLM(providers=providers)


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
        # Cached instances, not inline constructors
        text_chunker=get_text_chunker(),
        code_chunker=get_code_chunker(),
        deduplicator=get_deduplicator(),
    )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_loaders() -> dict[str, BaseLoader]:
    settings = get_settings()
    # Typed as Dict[str, BaseLoader] for safety
    return {
        "pdf": PDFLoader(),
        "docx": DocxLoader(),
        "web": WebLoader(),
        "github": GitHubLoader(),
        "text": TextLoader(),
        "youtube": YouTubeLoader(proxy_url=settings.YOUTUBE_PROXY or None),
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
# Repository Intelligence — route -> service -> analyzer -> storage
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_repository_store() -> RepositoryStore:
    return RepositoryStore()


@lru_cache(maxsize=1)
def get_repository_analyzer() -> RepositoryAnalyzer:
    return RepositoryAnalyzer()


@lru_cache(maxsize=1)
def get_repository_intelligence_service() -> RepositoryIntelligenceService:
    return RepositoryIntelligenceService(
        store=get_repository_store(),
        analyzer=get_repository_analyzer(),
    )


# ---------------------------------------------------------------------------
# Mind Map — generated from a source's chunks via the existing LLM chain
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_mindmap_store() -> MindMapStore:
    return MindMapStore()


@lru_cache(maxsize=1)
def get_mindmap_service() -> MindMapService:
    return MindMapService(
        store=get_mindmap_store(),
        faiss=get_faiss_store(),
        llm=get_llm(),
        prompt_builder=get_prompt_builder(),
    )


# ---------------------------------------------------------------------------
# Graceful shutdown: close all resources that hold connections
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
        await get_llm().aclose()
        logger.debug("LLM clients closed.")
    except Exception as exc:
        logger.warning("Error closing LLM clients: %s", exc)

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

    try:
        get_repository_store().close()
        logger.debug("RepositoryStore closed.")
    except Exception as exc:
        logger.warning("Error closing RepositoryStore: %s", exc)

    try:
        get_mindmap_store().close()
        logger.debug("MindMapStore closed.")
    except Exception as exc:
        logger.warning("Error closing MindMapStore: %s", exc)
