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
from app.model_hub import factory as model_hub_factory
from app.model_hub.service import ModelHubService
from app.model_hub.storage import ModelHubStore
from app.repository_intelligence.analyzer import RepositoryAnalyzer
from app.repository_intelligence.service import RepositoryIntelligenceService
from app.repository_intelligence.storage import RepositoryStore
from app.services.ingest_service import IngestService
from app.services.query_service import QueryService
from core.chunking.code_chunker import CodeChunker
from core.chunking.text_chunker import TextChunker
from core.generation.prompt_builder import PromptBuilder
from core.ingestion.base_loader import BaseLoader
from core.ingestion.docx_loader import DocxLoader
from core.ingestion.github_loader import GitHubLoader
from core.ingestion.pdf_loader import PDFLoader
from core.ingestion.text_loader import TextLoader
from core.ingestion.web_loader import WebLoader
from core.ingestion.youtube_loader import YouTubeLoader
from core.interfaces.embedder import Embedder
from core.interfaces.llm import LLM
from core.interfaces.not_configured import NullEmbedder, NullLLM
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
    "apply_serving_configuration",
    "close_all",
    "get_ingest_service",
    "get_model_hub_service",
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
def get_embedder() -> Embedder:
    """Return the currently served embedder, or a not-configured sentinel.

    As with :func:`get_llm`, model selection is owned by the Model Hub; this
    default is replaced by :func:`apply_serving_configuration`.
    """
    return NullEmbedder()


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
# LLM — model selection is owned by the Model Hub
# ---------------------------------------------------------------------------
#
# There is deliberately NO environment-driven provider chain here.  The active
# LLM is the one selected in the Model Hub's Serving tab and installed by
# ``apply_serving_configuration``.  Until a model is served, ``get_llm`` returns
# a sentinel that fails loudly with a pointer to the Model Hub rather than
# silently calling whichever provider happens to have a key in the environment.


@lru_cache(maxsize=1)
def get_llm() -> LLM:
    """Return the currently served LLM, or a not-configured sentinel.

    This default is replaced at startup / on serving changes by
    :func:`apply_serving_configuration`.
    """
    return NullLLM()


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
# Model Hub — model registry, fallback chains, and serving selection
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_model_hub_store() -> ModelHubStore:
    return ModelHubStore()


@lru_cache(maxsize=1)
def get_model_hub_service() -> ModelHubService:
    return ModelHubService(store=get_model_hub_store())


async def apply_serving_configuration() -> None:
    """Reconcile the running pipeline with the persisted Model Hub serving config.

    This is the linchpin of the feature: changing the served model/chain in the
    UI must actually change which LLM/embedder ContextForge uses.  When a tier
    is set to a Model Hub override, the orchestrator's (and, for the LLM, HyDE's
    and Mind Map's) active component is rebuilt from the stored config.  When a
    tier is disabled, the original env-driven component is restored.

    Safe to call at startup and after every serving update.
    """
    service = get_model_hub_service()
    orchestrator = get_orchestrator()

    # --- LLM tier ---
    try:
        llm_configs = await service.resolve_llm_configs()
        active_llm = (
            model_hub_factory.build_llm_from_configs(llm_configs)
            if llm_configs
            else get_llm()
        )
        await orchestrator.swap_llm(active_llm)
        _rewire_llm_consumers(active_llm)
    except Exception as exc:
        logger.warning("Model Hub: could not apply LLM serving config (%s) — using env default.", exc)

    # --- Embedding tier ---
    try:
        embedder_config = await service.resolve_embedding_config()
        active_embedder = (
            model_hub_factory.build_embedder(embedder_config)
            if embedder_config
            else get_embedder()
        )
        await orchestrator.swap_embedder(active_embedder)
    except Exception as exc:
        logger.warning(
            "Model Hub: could not apply embedding serving config (%s) — using env default.",
            exc,
        )


def _rewire_llm_consumers(llm) -> None:
    """Point HyDE and Mind Map at the newly active LLM.

    Both hold a reference to the LLM taken at construction time; without this
    they would keep using the previous model after a serving switch.
    """
    try:
        get_hyde().swap_llm(llm)
    except Exception as exc:
        logger.warning("Model Hub: could not rewire HyDE LLM (%s).", exc)
    try:
        get_mindmap_service().swap_llm(llm)
    except Exception as exc:
        logger.warning("Model Hub: could not rewire Mind Map LLM (%s).", exc)


# ---------------------------------------------------------------------------
# Graceful shutdown: close all resources that hold connections
# Called from the lifespan context manager in main.py
# ---------------------------------------------------------------------------


async def close_all() -> None:
    """Release all resources acquired by singleton factories.

    Closes the active LLM/embedder HTTP clients and the SQLite-backed stores.
    """
    logger.info("Shutting down ContextForge — releasing resources.")

    try:
        close_llm = getattr(get_llm(), "aclose", None)
        if close_llm is not None:
            await close_llm()
        logger.debug("LLM clients closed.")
    except Exception as exc:
        logger.warning("Error closing LLM clients: %s", exc)

    try:
        close_embedder = getattr(get_embedder(), "aclose", None)
        if close_embedder is not None:
            await close_embedder()
        logger.debug("Embedder closed.")
    except Exception as exc:
        logger.warning("Error closing embedder: %s", exc)

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

    try:
        get_model_hub_store().close()
        logger.debug("ModelHubStore closed.")
    except Exception as exc:
        logger.warning("Error closing ModelHubStore: %s", exc)
